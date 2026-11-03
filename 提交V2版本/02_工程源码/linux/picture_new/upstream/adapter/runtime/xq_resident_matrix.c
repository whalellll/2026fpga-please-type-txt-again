/* Native worker only: prepack one complete immutable layer into this fd's
 * resident DDR snapshot. Every job still DMA-loads its own 64-line bank;
 * resident avoids repeated CPU packing/copies. The shared driver owns all
 * physical transactions and restores this snapshot after another client.
 * No RTL/ABI change, MMIO bypass, or error-triggered CPU fallback. */
#include "xq_mac.h"
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#define INPUT 0u
#define OUTPUT 8192u
#define WEIGHT 32768u
typedef struct {
    const xqm_transport *transport;
    const int8_t *weight;
    unsigned k,n,co_step,kchunks,cochunks;
    unsigned offsets[1024];
} cache_state;
static cache_state cache;
static unsigned min_u(unsigned a,unsigned b){return a<b?a:b;}
int xqm_matrix(const xqm_transport *t,const int8_t *a,size_t ab,const int8_t *b,size_t bb,
               const int32_t *bias,size_t biases,unsigned m,unsigned k,unsigned n,
               int32_t *out,size_t values,xqm_stats *stats)
{
    int64_t sums[16*256];xqm_linux *c;
    unsigned co_step,kchunks,cochunks;
    xqm_stats st={0};
    if(stats)memset(stats,0,sizeof(*stats));
    if(!t || !t->context || !t->shadow || t->bytes!=0x100000 || !a || !b || !out ||
       !m || m>16 || !k || k>65535 || !n || n>1024 || (size_t)m*k>ab || (size_t)n*k>bb ||
       (size_t)m*n>values || (bias && biases<n))return 0;
    c=t->context;if(t!=&c->io || c->fd<0)return 0;
    co_step=min_u(256,32*(64/((min_u(k,256)+3)/4)));
    kchunks=(k+255)/256;cochunks=(n+co_step-1)/co_step;
    if((size_t)kchunks*cochunks>1024)return 0;
    if(cache.transport!=t || cache.weight!=b || cache.k!=k || cache.n!=n) {
        unsigned offset=WEIGHT;
        memset(&cache,0,sizeof(cache));
        for(unsigned co=0,oi=0;co<n;co+=co_step,oi++)for(unsigned ci=0,ki=0;ci<k;ci+=256,ki++) {
            unsigned nt=min_u(n-co,co_step),kt=min_u(k-ci,256),tiles=(kt+3)/4;
            unsigned bytes=((nt+31)/32)*tiles*128;
            if(offset>t->bytes || bytes>t->bytes-offset)return 0;
            cache.offsets[oi*kchunks+ki]=offset;memset(t->shadow+offset,0,bytes);
            for(unsigned channel=0;channel<nt;channel++)for(unsigned q=0;q<kt;q++) {
                unsigned at=offset+(channel/32*tiles+q/4)*128+(channel%32/2*4+q%4)*2+channel%2;
                t->shadow[at]=(uint8_t)b[(size_t)(co+channel)*k+ci+q];
            }
            offset+=bytes;
        }
        struct pango_mac_model model={0};model.abi_version=PANGO_MAC_MODEL_ABI_VERSION;
        model.offset=WEIGHT;model.bytes=offset-WEIGHT;
        if(ioctl(c->fd,PANGO_MAC_IOC_REGISTER_MODEL,&model))return 0;
        cache.transport=t;cache.weight=b;cache.k=k;cache.n=n;cache.co_step=co_step;
        cache.kchunks=kchunks;cache.cochunks=cochunks;
    }
    for(unsigned co=0,oi=0;co<n;co+=co_step,oi++) {
        unsigned nt=min_u(n-co,co_step);memset(sums,0,(size_t)m*nt*sizeof(*sums));
        for(unsigned ci=0,ki=0;ci<k;ci+=256,ki++) {
            unsigned kt=min_u(k-ci,256),tiles=(kt+3)/4;
            struct pango_mac_job job={0};
            if(t->cancelled && t->cancelled(t->context))return 0;
            for(unsigned p=0;p<m;p++) {
                uint32_t *destination=(uint32_t *)(void *)(t->shadow+INPUT+(size_t)p*tiles*8);
                const int8_t *source=a+(size_t)p*k+ci;
                for(unsigned q=0;q<kt;q+=4) {
                    uint32_t v0=(uint8_t)source[q];
                    uint32_t v1=q+1<kt?(uint8_t)source[q+1]:0;
                    uint32_t v2=q+2<kt?(uint8_t)source[q+2]:0;
                    uint32_t v3=q+3<kt?(uint8_t)source[q+3]:0;
                    /* Aligned ordinary shadow RAM; every padding byte is
                     * written, including compact tails. Hardware S8 mode
                     * reads the low byte of each 16-bit lane. */
                    *destination++=v0|(v1<<16);
                    *destination++=v2|(v3<<16);
                }
            }
            job.abi_version=1;job.pixels=(uint16_t)m;job.cin=(uint16_t)kt;job.cout=(uint16_t)nt;
            job.compute_mode=1;job.output_format=3;job.zero_bias=1;job.input_offset=INPUT;
            job.weight_offset=cache.offsets[oi*kchunks+ki];job.output_offset=OUTPUT;job.timeout_us=1000000;
            if(ioctl(c->fd,PANGO_MAC_IOC_RUN_RESIDENT,&job) || !(job.status&2) || (job.status&4) || job.error_code)return 0;
            st.jobs++;st.cycles+=job.cycles;
            for(unsigned p=0;p<m;p++)for(unsigned channel=0;channel<nt;channel++) {
                int32_t v;memcpy(&v,t->shadow+OUTPUT+(p*nt+channel)*4,4);sums[p*nt+channel]+=v;
            }
        }
        for(unsigned p=0;p<m;p++)for(unsigned channel=0;channel<nt;channel++) {
            int64_t v=sums[p*nt+channel]+(bias?bias[co+channel]:0);
            if(v<INT32_MIN || v>INT32_MAX)return 0;
            out[(size_t)p*n+co+channel]=(int32_t)v;
        }
    }
    if(stats)*stats=st;
    return 1;
}
