#define _POSIX_C_SOURCE 200809L
#include "xq_mac.h"
#include "graph_profile.h"
#include "xq_resident_matrix.h"
#include <fcntl.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#ifdef XQ_NATIVE_TIMING
#include <time.h>
#endif

/* Reuse the worker's compact counter schema without linking legacy dense
 * residency. These counters measure V321 ioctl wall time, not hardware time. */
static xqn_resident_profile profile;
void xqn_resident_profile_reset(void)
{
    memset(&profile,0,sizeof(profile));
#ifdef XQ_NATIVE_TIMING
    profile.enabled=1;
#endif
}
void xqn_resident_profile_read(xqn_resident_profile *out)
{
    if(out)*out=profile;
}
#ifdef XQ_NATIVE_TIMING
static uint64_t clock_ns(void)
{
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t)){profile.clock_failures++;return 0;}
    return (uint64_t)t.tv_sec*1000000000u+(unsigned)t.tv_nsec;
}
#endif

int xqm_linux_open(xqm_linux *c)
{
    struct pango_mac_info info={0};
    const unsigned required=PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED|PANGO_MAC_FEATURE_VISION32;
    if(!c)return 0;
    memset(c,0,sizeof(*c));c->fd=-1;
    c->fd=open("/dev/pango-mac0",O_RDWR|O_CLOEXEC);if(c->fd<0)return 0;
    if(ioctl(c->fd,PANGO_MAC_IOC_GET_INFO,&info) || info.abi_version!=1 ||
       !pango_mac_device_valid(info.device_id,info.device_version) ||
       info.scratch_bytes!=0x100000 || info.max_timeout_us<1000000 ||
       (info.features&required)!=required)goto fail;
    c->io.shadow=mmap(NULL,info.scratch_bytes,PROT_READ|PROT_WRITE,MAP_SHARED,c->fd,0);
    if(c->io.shadow==MAP_FAILED){c->io.shadow=NULL;goto fail;}
    c->features=info.features; /* ABI3 gray dispatch stays off. */
    c->io.bytes=info.scratch_bytes;c->io.context=c;return 1;
fail:
    xqm_linux_close(c);return 0;
}
void xqm_linux_close(xqm_linux *c)
{
    if(!c)return;
    if(c->io.shadow)munmap(c->io.shadow,c->io.bytes);
    if(c->fd>=0)close(c->fd);
    memset(c,0,sizeof(*c));c->fd=-1;
}
void xqv_parameters_begin(const xqm_transport *t,struct pango_vision32_job *j)
{
    xqm_linux *c=t?(xqm_linux *)t->context:NULL;
    if(!j)return;
    j->model_generation=0;j->reserved[0]=0;
    if(c && t==&c->io && (c->features&PANGO_MAC_FEATURE_VISION32_REUSE) &&
       c->parameter_sequence!=UINT32_MAX){
        j->model_generation=++c->parameter_sequence;
        j->reserved[0]=PANGO_VISION32_REUSE_PARAMS;
    }
}
int xqv_exact_available(const xqm_transport *t)
{
    if(!t || !t->context)return 0;
    const xqm_linux *c=t->context;
    return t==&c->io && c->fd>=0 &&
           (c->features&PANGO_MAC_FEATURE_VISION32_EXACT)!=0;
}
int xqv_run(const xqm_transport *t,struct pango_vision32_job *j)
{
    xqm_linux *c;
    unsigned sizes[5];
    if(!t || !t->context || !t->shadow || t->bytes!=0x100000 ||
       !pango_vision32_sizes(j,(uint32_t)t->bytes,sizes))return 0;
    c=t->context;if(t!=&c->io || c->fd<0 || (t->cancelled && t->cancelled(c)))return 0;
    if((j->flags&4u) && !(c->features&PANGO_MAC_FEATURE_VISION32_EXACT))return 0;
    if(j->reserved[0]==PANGO_VISION32_REUSE_PARAMS)j->frame_id=0;
#ifdef XQ_NATIVE_TIMING
    uint64_t start=clock_ns();
#endif
    xqg_mark submit_start=xqg_begin();
    int okay=ioctl(c->fd,PANGO_MAC_IOC_RUN_VISION32,j)==0 &&
        (j->status&3u)==2u && !(j->status&4u) && !j->error;
    xqg_end(XQG_SUBMIT,submit_start,1);
#ifdef XQ_NATIVE_TIMING
    uint64_t end=clock_ns();
    if(end<start)profile.clock_failures++;
    else profile.ioctl_ns+=end-start;
    profile.calls++;
    if(okay){profile.runs++;profile.cycles+=j->cycles;}
    else profile.errors++;
#endif
    if(okay){
        uint64_t bytes=(uint64_t)sizes[1]+sizes[3]+sizes[4];
        if(j->reserved[0]==PANGO_VISION32_REUSE_PARAMS && j->frame_id==1)
            c->parameter_saved_bytes+=bytes;
        else c->parameter_upload_bytes+=bytes;
    }
    return okay;
}
/* General linear/deep/dilated layers retain exact CPU window assembly.
 * ALL dot products still execute in V321. An ioctl error never selects CPU. */
int xqm_matrix(const xqm_transport *t,const int8_t *a,size_t ab,const int8_t *b,size_t bb,
    const int32_t *bias,size_t biases,unsigned m,unsigned k,unsigned n,
    int32_t *out,size_t values,xqm_stats *stats)
{
    int64_t sums[16*256];
    xqm_stats total={0};
    if(stats)memset(stats,0,sizeof(*stats));
    if(!t || !t->shadow || t->bytes!=0x100000 || !a || !b || !out || !m || m>16 || !k || k>65535 || !n || n>1024 ||
       (size_t)m*k>ab || (size_t)n*k>bb || (size_t)m*n>values || (bias && biases<n))return 0;
    for(unsigned co=0;co<n;co+=256){
        unsigned nt=n-co<256?n-co:256;
        memset(sums,0,(size_t)m*nt*sizeof(*sums));
        for(unsigned ci=0;ci<k;ci+=512){
            unsigned kt=k-ci<512?k-ci:512,ci4=(kt+3)&~3u,groups=(nt+7)/8;
            struct pango_vision32_job j={0};
            j.abi_version=PANGO_VISION32_ABI;j.input=0;j.weights=0x10000;
            j.output=0x8000;j.params=0x4000;j.lut=0;j.width=m;j.height=1;
            j.cin=kt;j.cout=nt;j.kernel=j.stride=1;j.flags=2;
            j.timeout_cycles=49500000;j.timeout_us=1000000;
            memset(t->shadow,0,(size_t)m*ci4);
            for(unsigned p=0;p<m;p++)memcpy(t->shadow+p*ci4,a+(size_t)p*k+ci,kt);
            memset(t->shadow+j.params,0,groups*8*12);
            memset(t->shadow+j.weights,0,(size_t)groups*kt*8);
            for(unsigned o=0;o<nt;o++)for(unsigned q=0;q<kt;q++)
                t->shadow[j.weights+((o/8)*kt+q)*8+o%8]=(uint8_t)b[(size_t)(co+o)*k+ci+q];
            if(!xqv_run(t,&j))return 0;
            total.jobs++;total.cycles+=j.cycles;
            for(unsigned p=0;p<m;p++)for(unsigned o=0;o<nt;o++){
                int32_t v;memcpy(&v,t->shadow+j.output+4*(p*nt+o),4);sums[p*nt+o]+=v;
            }
        }
        for(unsigned p=0;p<m;p++)for(unsigned o=0;o<nt;o++){
            int64_t v=sums[p*nt+o]+(bias?bias[co+o]:0);
            if(v<INT32_MIN || v>INT32_MAX)return 0;
            out[(size_t)p*n+co+o]=(int32_t)v;
        }
    }
    if(stats)*stats=total;
    return 1;
}
