#include "xq_mac.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int emulate(void *opaque,struct pango_mac_job *j)
{
    uint8_t *s=opaque;unsigned p,c,k,tiles=(j->cin+3)/4;
    assert(j->pixels<=16 && j->cin<=256 && j->cout<=256 && j->zero_bias && !j->out_shift && !j->activation);
    /* Frozen SoC uses the compact 64-line weight bank. Channel maxima
     * alone do not permit the Cartesian 256 x 256 descriptor. */
    assert(((j->cout+31)/32)*tiles<=64);
    for(p=0;p<j->pixels;p++)for(c=0;c<j->cout;c++) {
        int32_t sum=0;
        for(k=0;k<j->cin;k++) {
            unsigned wi=j->weight_offset+(c/32*tiles+k/4)*128+(c%32/2*4+k%4)*2+c%2;
            sum+=(int8_t)s[j->input_offset+(p*tiles+k/4)*8+(k%4)*2]*(int8_t)s[wi];
        }
        memcpy(s+j->output_offset+(p*j->cout+c)*4,&sum,4);
    }
    j->cycles=123;return 1;
}
int main(void)
{
    enum {M=19,K=513,N=273};
    int8_t *a=malloc(M*K),*b=malloc(N*K);
    int32_t *out=malloc(M*N*4),*bias=malloc(N*4);
    uint8_t *shadow=calloc(1,0x100000);
    xqm_transport transport={shadow,0x100000,shadow,emulate,NULL};
    xqm_stats stats;unsigned p,c,k;
    assert(a && b && out && bias && shadow);
    for(k=0;k<M*K;k++)a[k]=(int8_t)(k*73u+19u);
    for(k=0;k<N*K;k++)b[k]=(int8_t)(k*37u+5u);
    for(c=0;c<N;c++)bias[c]=(int32_t)c*51-7000;
    assert(xqm_matrix(&transport,a,M*K,b,N*K,bias,N,M,K,N,out,M*N,&stats));
    assert(stats.jobs==54 && stats.cycles==54*123);
    for(p=0;p<M;p++)for(c=0;c<N;c++) {
        int64_t expected=bias[c];
        for(k=0;k<K;k++)expected+=(int)a[p*K+k]*b[c*K+k];
        assert(out[p*N+c]==expected);
    }
    assert(!xqm_matrix(&transport,a,M*K-1,b,N*K,bias,N,M,K,N,out,M*N,&stats));
    assert(!xqm_matrix(&transport,a,1,b,1,NULL,0,1,1,1,(int32_t *)a,1,&stats));
    a[0]=b[0]=127;bias[0]=INT32_MAX;
    assert(!xqm_matrix(&transport,a,1,b,1,bias,1,1,1,1,out,1,&stats));
    free(a);free(b);free(out);free(bias);free(shadow);
    puts("XQ_MAC_TILES_TEST_PASS synthetic M19_K513_N273 jobs54 bank64_tail_deepK_bias_once_overflow=pass");
    return 0;
}
