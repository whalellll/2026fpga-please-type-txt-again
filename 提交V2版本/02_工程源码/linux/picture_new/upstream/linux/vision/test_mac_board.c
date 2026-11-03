#define _POSIX_C_SOURCE 200809L
#include "xq_mac.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
static uint64_t us(void)
{struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000u+t.tv_nsec/1000u;}
static int check(xqm_linux *mac,unsigned m,unsigned k,unsigned n,unsigned seed)
{
    int8_t *a=malloc((size_t)m*k),*b=malloc((size_t)n*k);
    int32_t *bias=malloc(n*4u),*out=malloc((size_t)m*n*4u);
    xqm_stats stats;unsigned p,c,q;uint64_t begin=us(),matrix_us;
    int result=1;
    if(!a || !b || !bias || !out)goto done;
    for(q=0;q<m*k;q++)a[q]=(int8_t)(q*73u+seed);
    for(q=0;q<n*k;q++)b[q]=(int8_t)(q*37u+seed*3u);
    for(c=0;c<n;c++)bias[c]=(int32_t)c*51-7000;
    if(!xqm_matrix(&mac->io,a,(size_t)m*k,b,(size_t)n*k,bias,n,m,k,n,out,(size_t)m*n,&stats)) {
        fputs("XQ_MAC_BOARD_FAIL submit\n",stderr);goto done;
    }
    matrix_us=us()-begin;
    for(p=0;p<m;p++)for(c=0;c<n;c++) {
        int64_t expected=bias[c];
        for(q=0;q<k;q++)expected+=(int)a[(size_t)p*k+q]*(int)b[(size_t)c*k+q];
        if(out[(size_t)p*n+c]!=expected) {
            fprintf(stderr,"XQ_MAC_BOARD_FAIL m=%u k=%u n=%u row=%u col=%u actual=%d expected=%"PRId64"\n",
                    m,k,n,p,c,out[(size_t)p*n+c],expected);goto done;
        }
    }
    printf("XQ_MAC_BOARD_CASE_PASS m=%u k=%u n=%u outputs=%u jobs=%"PRIu64" cycles=%"PRIu64" matrix_us=%"PRIu64"\n",
           m,k,n,m*n,stats.jobs,stats.cycles,matrix_us);
    result=0;
done:
    free(a);free(b);free(bias);free(out);return result;
}
int main(void)
{
    static const unsigned dimensions[][3]={{1,1,1},{3,3,17},{16,256,256},{19,513,273}};
    xqm_linux mac;unsigned i;int failed=0;
    if(!xqm_linux_open(&mac)){perror("XQ_MAC_BOARD_FAIL strict_driver_open");return 1;}
    for(i=0;i<sizeof(dimensions)/sizeof(dimensions[0]);i++)
        if(check(&mac,dimensions[i][0],dimensions[i][1],dimensions[i][2],19u+i)){failed=1;break;}
    xqm_linux_close(&mac);
    if(!failed)puts("XQ_MAC_BOARD_PASS backend=driver s8=pass tails=pass deep_k=pass bias_once=pass model=none");
    return failed;
}
