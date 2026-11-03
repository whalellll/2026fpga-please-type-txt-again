#include "xq_mac.h"
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static xqm_linux context;
static uint8_t *snapshot;
static struct pango_mac_model model;
static unsigned registrations,runs;
int __wrap_ioctl(int fd,unsigned long request,...)
{
    va_list ap;void *arg;va_start(ap,request);arg=va_arg(ap,void *);va_end(ap);assert(fd==42);
    if(request==PANGO_MAC_IOC_REGISTER_MODEL) {
        model=*(struct pango_mac_model *)arg;assert(pango_mac_model_valid(&model,0x100000));
        memcpy(snapshot+model.offset,context.io.shadow+model.offset,model.bytes);++registrations;return 0;
    }
    assert(request==PANGO_MAC_IOC_RUN_RESIDENT);
    struct pango_mac_job *j=arg;unsigned tiles=(j->cin+3)/4;
    assert(tiles*((j->cout+31)/32)<=64 && j->zero_bias && j->output_format==3);
    assert(pango_mac_resident_sources_valid(model.offset,model.bytes,j->weight_offset,((j->cout+31)/32)*tiles*128,
        0,0,j->input_offset,j->pixels*tiles*8,j->output_offset,j->pixels*j->cout*4));
    for(unsigned p=0;p<j->pixels;p++)for(unsigned co=0;co<j->cout;co++) {
        int32_t v=0;
        for(unsigned k=0;k<j->cin;k++) {
            int8_t a=(int8_t)context.io.shadow[j->input_offset+(p*tiles+k/4)*8+(k%4)*2];
            unsigned at=j->weight_offset+(co/32*tiles+k/4)*128+(co%32/2*4+k%4)*2+co%2;
            v+=(int32_t)a*(int8_t)snapshot[at];
        }
        memcpy(context.io.shadow+j->output_offset+(p*j->cout+co)*4,&v,4);
    }
    ++runs;j->cycles=17;j->status=2;return 0;
}
static void check(unsigned m,unsigned k,unsigned n)
{
    int8_t *a=malloc((size_t)m*k),*b=malloc((size_t)n*k);int32_t *bias=malloc(n*4),*out=malloc((size_t)m*n*4);
    unsigned before=registrations;xqm_stats stats;
    assert(a && b && bias && out);
    for(unsigned i=0;i<m*k;i++)a[i]=(int8_t)((i*17+3)%255-127);
    for(unsigned i=0;i<n*k;i++)b[i]=(int8_t)((i*19+7)%255-127);
    for(unsigned i=0;i<n;i++)bias[i]=(int32_t)i*123-512;
    for(unsigned trial=0;trial<2;trial++) {
        assert(xqm_matrix(&context.io,a,(size_t)m*k,b,(size_t)n*k,bias,n,m,k,n,out,(size_t)m*n,&stats));
        assert(registrations==before+1);
        for(unsigned i=0;i<m;i++)for(unsigned co=0;co<n;co++) {
            int64_t sum=bias[co];for(unsigned q=0;q<k;q++)sum+=(int32_t)a[(size_t)i*k+q]*b[(size_t)co*k+q];
            assert(out[(size_t)i*n+co]==sum);
        }
        /* Destructive changes to the public shadow never mutate registered
         * weights; the mocked device uses its independent snapshot. */
        memset(context.io.shadow+model.offset,0,model.bytes);
    }
    free(a);free(b);free(bias);free(out);
}
int main(void)
{
    context.fd=42;context.io.context=&context;context.io.bytes=0x100000;
    context.io.shadow=calloc(1,0x100000);snapshot=calloc(1,0x100000);assert(snapshot && context.io.shadow);
    check(16,256,256);check(3,3,17);check(16,513,273);check(1,3456,64);check(16,32,256);
    assert(registrations==5 && runs>5);
    free(context.io.shadow);free(snapshot);puts("NATIVE_RESIDENT_MATRIX_TEST_PASS bias_once deepK tails immutable_cache no_MMIO");return 0;
}
