#include "xq_mac.h"
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#define IN 0u
#define OUT 8192u
#define WT 32768u
static unsigned smaller(unsigned a,unsigned b){return a<b?a:b;}
static int overlaps(const void *a,size_t an,const void *b,size_t bn)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    return an && bn && (x<=y?y-x<an:x-y<bn);
}
int xqm_matrix(const xqm_transport *t,const int8_t *a,size_t ab,const int8_t *b,size_t bb,
               const int32_t *bias,size_t biases,unsigned m,unsigned k,unsigned n,
               int32_t *output,size_t output_values,xqm_stats *stats)
{
    unsigned row,co,ci,p,c,q,co_step;
    int64_t *sums;
    xqm_stats totals={0};
    int okay=0;
    if(stats)memset(stats,0,sizeof(*stats));
    if(!t || !t->shadow || !t->submit || t->bytes<WT+65536 || !a || !b || !output ||
       !m || !k || !n || m>1280u*720u || k>65535 || n>65535 ||
       (uint64_t)m*k>ab || (uint64_t)n*k>bb || (uint64_t)m*n>output_values ||
       (uint64_t)m*n>SIZE_MAX/sizeof(int32_t) || (bias && biases<n))return 0;
    if(overlaps(output,(size_t)m*n*4,a,(size_t)m*k) ||
       overlaps(output,(size_t)m*n*4,b,(size_t)n*k) ||
       (bias && overlaps(output,(size_t)m*n*4,bias,n*4u)) ||
       overlaps(a,(size_t)m*k,t->shadow,t->bytes) || overlaps(b,(size_t)n*k,t->shadow,t->bytes) ||
       overlaps(output,(size_t)m*n*4,t->shadow,t->bytes) ||
       (bias && overlaps(bias,n*4u,t->shadow,t->bytes)))return 0;
    /* All K chunks fit this output tile, including the longest chunk.
     * Do not treat the separate 256-channel maxima as a 256x256 bank. */
    co_step=smaller(256u,32u*(XQM_WEIGHT_BANK_LINES/((smaller(k,256u)+3u)/4u)));
    sums=malloc(16u*256u*sizeof(*sums));if(!sums)return 0;
    for(row=0;row<m;row+=16)for(co=0;co<n;co+=co_step) {
        unsigned mt=smaller(m-row,16),nt=smaller(n-co,co_step);
        memset(sums,0,(size_t)mt*nt*sizeof(*sums));
        for(ci=0;ci<k;ci+=256) {
            unsigned kt=smaller(k-ci,256),tiles=(kt+3)/4,cotiles=(nt+31)/32;
            struct pango_mac_job job={0};
            if(t->cancelled && t->cancelled(t->context))goto done;
            memset(t->shadow+IN,0,(size_t)mt*tiles*8);
            memset(t->shadow+WT,0,(size_t)cotiles*tiles*128);
            for(p=0;p<mt;p++)for(q=0;q<kt;q++)
                t->shadow[IN+(p*tiles+q/4)*8+(q%4)*2]=(uint8_t)a[(size_t)(row+p)*k+ci+q];
            for(c=0;c<nt;c++)for(q=0;q<kt;q++) {
                unsigned at=WT+(c/32*tiles+q/4)*128+(c%32/2*4+q%4)*2+c%2;
                t->shadow[at]=(uint8_t)b[(size_t)(co+c)*k+ci+q];
            }
            job.abi_version=PANGO_MAC_ABI_VERSION;job.pixels=(uint16_t)mt;
            job.cin=(uint16_t)kt;job.cout=(uint16_t)nt;
            job.compute_mode=1;job.output_format=3;job.zero_bias=1;
            job.input_offset=IN;job.weight_offset=WT;job.output_offset=OUT;job.timeout_us=1000000;
            if(t->submit(t->context,&job)!=1)goto done;
            totals.jobs++;totals.cycles+=job.cycles;
            for(p=0;p<mt;p++)for(c=0;c<nt;c++) {
                int32_t partial;
                memcpy(&partial,t->shadow+OUT+(p*nt+c)*4,4);
                sums[p*nt+c]+=partial;
            }
        }
        for(p=0;p<mt;p++)for(c=0;c<nt;c++) {
            int64_t value=sums[p*nt+c]+(bias?bias[co+c]:0);
            if(value<INT32_MIN || value>INT32_MAX)goto done;
            output[(size_t)(row+p)*n+co+c]=(int32_t)value;
        }
    }
    okay=1;
done:
    free(sums);if(stats)*stats=totals;return okay;
}
