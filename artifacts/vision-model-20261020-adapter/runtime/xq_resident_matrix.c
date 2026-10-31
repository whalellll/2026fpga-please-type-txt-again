#define _POSIX_C_SOURCE 200809L
/* Per-fd snapshots; one physical 1 MiB aperture is serialized/restored by the
 * driver. No global pointer cache, physical MMIO access or CPU fallback. */
#include "xq_resident_matrix.h"
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#ifdef XQ_NATIVE_TIMING
#include <errno.h>
#include <time.h>
static xqn_resident_profile measured;
static uint64_t profile_now_ns(void)
{
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t)){++measured.clock_failures;return 0;}
    return (uint64_t)t.tv_sec*1000000000u+(unsigned)t.tv_nsec;
}
#endif
void xqn_resident_profile_reset(void)
{
#ifdef XQ_NATIVE_TIMING
    memset(&measured,0,sizeof(measured));measured.enabled=1;
#endif
}
void xqn_resident_profile_read(xqn_resident_profile *out)
{
    if(!out)return;
#ifdef XQ_NATIVE_TIMING
    *out=measured;out->enabled=1;
#else
    memset(out,0,sizeof(*out));
#endif
}
static int resident_ioctl(int fd,unsigned long request,void *arg)
{
#ifdef XQ_NATIVE_TIMING
    uint64_t begin=profile_now_ns();int rc=ioctl(fd,request,arg),saved=errno;
    uint64_t end=profile_now_ns();
    if(end>=begin)measured.ioctl_ns+=end-begin;else ++measured.clock_failures;
    ++measured.calls;
    if(rc)++measured.errors;
    else if(request==PANGO_MAC_IOC_REGISTER_MODEL)++measured.registrations;
    else {
        const struct pango_mac_job *j=arg;
        if((j->status&2u) && !(j->status&4u) && !j->error_code) {
            ++measured.runs;measured.cycles+=j->cycles;
        } else ++measured.errors;
    }
    errno=saved;return rc;
#else
    return ioctl(fd,request,arg);
#endif
}
#define INPUT 0u
#define OUTPUT 8192u
#define WEIGHT 32768u
typedef struct {const int8_t *weight;unsigned k,n,co_step,kchunks;unsigned *offsets;} layer_entry;
typedef struct {unsigned count,pinned;layer_entry *entries;} cache_state;
static unsigned min_u(unsigned a,unsigned b){return a<b?a:b;}
static void release(void *opaque)
{
    cache_state *s=opaque;if(!s)return;
    for(unsigned i=0;i<s->count;i++)free(s->entries[i].offsets);
    free(s->entries);free(s);
}
static xqm_linux *owner(const xqm_transport *t)
{
    if(!t || !t->context || !t->shadow || t->bytes!=0x100000)return NULL;
    xqm_linux *c=t->context;return t==&c->io && c->fd>=0?c:NULL;
}
static int prepare(const xqm_transport *t,const xqn_resident_layer *layers,unsigned count,unsigned pinned)
{
    xqm_linux *c=owner(t);unsigned offset=WEIGHT;
    if(!c || !layers || !count || count>80)return 0;
    cache_state *s=calloc(1,sizeof(*s));if(!s)return 0;
    s->entries=calloc(count,sizeof(*s->entries));s->count=count;s->pinned=pinned;
    if(!s->entries){free(s);return 0;}
    /* Size all layers before changing shadow or the existing registration. */
    for(unsigned i=0;i<count;i++) {
        layer_entry *e=&s->entries[i];e->weight=layers[i].weight;e->k=layers[i].k;e->n=layers[i].n;
        if(!e->weight || !e->k || e->k>65535 || !e->n || e->n>1024)goto fail;
        e->co_step=min_u(256,32*(64/((min_u(e->k,256)+3)/4)));e->kchunks=(e->k+255)/256;
        unsigned entries=e->kchunks*((e->n+e->co_step-1)/e->co_step);
        if(entries>1024 || !(e->offsets=calloc(entries,sizeof(unsigned))))goto fail;
        for(unsigned co=0,oi=0;co<e->n;co+=e->co_step,oi++)for(unsigned ci=0,ki=0;ci<e->k;ci+=256,ki++) {
            unsigned nt=min_u(e->n-co,e->co_step),kt=min_u(e->k-ci,256),bytes=((nt+31)/32)*((kt+3)/4)*128;
            if(bytes>t->bytes-offset)goto fail;
            e->offsets[oi*e->kchunks+ki]=offset;offset+=bytes;
        }
    }
    memset(t->shadow+WEIGHT,0,offset-WEIGHT);
    for(unsigned i=0;i<count;i++) {
        layer_entry *e=&s->entries[i];
        for(unsigned co=0,oi=0;co<e->n;co+=e->co_step,oi++)for(unsigned ci=0,ki=0;ci<e->k;ci+=256,ki++) {
            unsigned nt=min_u(e->n-co,e->co_step),kt=min_u(e->k-ci,256),tiles=(kt+3)/4,base=e->offsets[oi*e->kchunks+ki];
            for(unsigned channel=0;channel<nt;channel++)for(unsigned q=0;q<kt;q++) {
                unsigned at=base+(channel/32*tiles+q/4)*128+(channel%32/2*4+q%4)*2+channel%2;
                t->shadow[at]=(uint8_t)e->weight[(size_t)(co+channel)*e->k+ci+q];
            }
        }
    }
    struct pango_mac_model model={0};model.abi_version=PANGO_MAC_MODEL_ABI_VERSION;model.offset=WEIGHT;model.bytes=offset-WEIGHT;
    if(resident_ioctl(c->fd,PANGO_MAC_IOC_REGISTER_MODEL,&model))goto fail;
    if(c->resident_free)c->resident_free(c->resident_cache);
    c->resident_cache=s;c->resident_free=release;return 1;
fail:release(s);return 0;
}
int xqn_resident_prepare(const xqm_transport *t,const xqn_resident_layer *layers,unsigned count)
{return prepare(t,layers,count,1);}
static int matrix(const xqm_transport *t,const int8_t *a,size_t ab,const int8_t *b,size_t bb,
               const int32_t *bias,size_t biases,unsigned m,unsigned k,unsigned n,
               int32_t *out,size_t values,xqm_stats *stats,unsigned plane,unsigned first)
{
    int64_t sums[16*256];xqm_linux *c=owner(t);layer_entry *entry=NULL;
    xqm_stats st={0};if(stats)memset(stats,0,sizeof(*stats));
    if(!c || !a || !b || !out || !m || m>16 || !k || k>65535 || !n || n>1024 ||
       (size_t)m*k>ab || (size_t)n*k>bb || (size_t)m*n>values || (bias && biases<n))return 0;
    if(plane && (plane>640u*640u || first>300u*plane-m || ((uint64_t)(first+m-1)/plane+1)*k*plane>ab))return 0;
    cache_state *cache=c->resident_cache;
    if(cache)for(unsigned i=0;i<cache->count;i++) {
        layer_entry *e=&cache->entries[i];if(e->weight==b && e->k==k && e->n==n){entry=e;break;}
    }
    if(!entry) {
        if(cache && cache->pinned)return 0;
        xqn_resident_layer layer={b,k,n};if(!prepare(t,&layer,1,0))return 0;
        cache=c->resident_cache;entry=&cache->entries[0];
    }
    for(unsigned co=0,oi=0;co<n;co+=entry->co_step,oi++) {
        unsigned nt=min_u(n-co,entry->co_step);memset(sums,0,(size_t)m*nt*sizeof(*sums));
        for(unsigned ci=0,ki=0;ci<k;ci+=256,ki++) {
            unsigned kt=min_u(k-ci,256),tiles=(kt+3)/4;struct pango_mac_job job={0};
            if(t->cancelled && t->cancelled(t->context))return 0;
            for(unsigned p=0;p<m;p++) {
                uint32_t *destination=(uint32_t *)(void *)(t->shadow+INPUT+(size_t)p*tiles*8);
                unsigned pos=first+p,step=plane?plane:1;
                const int8_t *source=plane?a+((size_t)(pos/plane)*k+ci)*plane+pos%plane:a+(size_t)p*k+ci;
                for(unsigned q=0;q<kt;q+=4) {
                    uint32_t v0=(uint8_t)source[q*step],v1=q+1<kt?(uint8_t)source[(q+1)*step]:0;
                    uint32_t v2=q+2<kt?(uint8_t)source[(q+2)*step]:0,v3=q+3<kt?(uint8_t)source[(q+3)*step]:0;
                    *destination++=v0|(v1<<16);*destination++=v2|(v3<<16);
                }
            }
            job.abi_version=1;job.pixels=(uint16_t)m;job.cin=(uint16_t)kt;job.cout=(uint16_t)nt;
            job.compute_mode=1;job.output_format=3;job.zero_bias=1;job.input_offset=INPUT;
            job.weight_offset=entry->offsets[oi*entry->kchunks+ki];job.output_offset=OUTPUT;job.timeout_us=1000000;
            if(resident_ioctl(c->fd,PANGO_MAC_IOC_RUN_RESIDENT,&job) || !(job.status&2) || (job.status&4) || job.error_code)return 0;
            st.jobs++;st.cycles+=job.cycles;
            for(unsigned p=0;p<m;p++)for(unsigned channel=0;channel<nt;channel++) {
                int32_t v;memcpy(&v,t->shadow+OUTPUT+(p*nt+channel)*4,4);sums[p*nt+channel]+=v;
            }
        }
        for(unsigned p=0;p<m;p++)for(unsigned channel=0;channel<nt;channel++) {
            int64_t v=sums[p*nt+channel]+(bias?bias[co+channel]:0);if(v<INT32_MIN || v>INT32_MAX)return 0;
            out[(size_t)p*n+co+channel]=(int32_t)v;
        }
    }
    if(stats)*stats=st;
    return 1;
}
int xqm_matrix(const xqm_transport *t,const int8_t *a,size_t ab,const int8_t *b,size_t bb,
               const int32_t *bias,size_t biases,unsigned m,unsigned k,unsigned n,
               int32_t *out,size_t values,xqm_stats *stats)
{return matrix(t,a,ab,b,bb,bias,biases,m,k,n,out,values,stats,0,0);}
int xqn_resident_pointwise(const xqm_transport *t,const int8_t *a,size_t ab,const int8_t *b,size_t bb,
               const int32_t *bias,size_t biases,unsigned m,unsigned k,unsigned n,unsigned plane,unsigned first,
               int32_t *out,size_t values,xqm_stats *stats)
{return plane?matrix(t,a,ab,b,bb,bias,biases,m,k,n,out,values,stats,plane,first):0;}
