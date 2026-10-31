#include "xq_mac.h"
#include "xq_resident_matrix.h"
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static xqm_linux context;
static uint8_t *snapshot;
static struct pango_mac_model model;
static unsigned registrations,runs;
#ifdef XQ_NATIVE_TIMING
static int force_run_failure;
#endif
int __wrap_ioctl(int fd,unsigned long request,...)
{
    va_list ap;void *arg;va_start(ap,request);arg=va_arg(ap,void *);va_end(ap);assert(fd==42);
    if(request==PANGO_MAC_IOC_REGISTER_MODEL) {
        model=*(struct pango_mac_model *)arg;assert(pango_mac_model_valid(&model,0x100000));
        memcpy(snapshot+model.offset,context.io.shadow+model.offset,model.bytes);++registrations;return 0;
    }
    assert(request==PANGO_MAC_IOC_RUN_RESIDENT);
    struct pango_mac_job *j=arg;unsigned tiles=(j->cin+3)/4;
#ifdef XQ_NATIVE_TIMING
    if(force_run_failure)return -1;
#endif
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
#ifdef XQ_NATIVE_TIMING
    xqn_resident_profile_reset();
#endif
    context.fd=42;context.io.context=&context;context.io.bytes=0x100000;
    context.io.shadow=calloc(1,0x100000);snapshot=calloc(1,0x100000);assert(snapshot && context.io.shadow);
    check(16,256,256);check(3,3,17);check(16,513,273);check(1,3456,64);check(16,32,256);
    assert(registrations==5 && runs>5);
    /* Two layers pinned once, alternating over several frames. This catches
     * the old one-layer/global-cache design re-registering every layer. */
    int8_t w0[9]={1,2,3,4,5,6,7,8,9},w1[9]={9,8,7,6,5,4,3,2,1},a[3]={1,-2,3};
    int32_t result[3];xqm_stats st;
    xqn_resident_layer layers[2]={{w0,3,3},{w1,3,3}};
    unsigned prior=registrations;assert(xqn_resident_prepare(&context.io,layers,2));
    for(unsigned frame=0;frame<3;frame++)for(unsigned layer=0;layer<2;layer++) {
        const int8_t *w=layer?w1:w0;
        assert(xqm_matrix(&context.io,a,3,w,9,NULL,0,1,3,3,result,3,&st));
        for(unsigned c=0;c<3;c++)assert(result[c]==a[0]*w[c*3]+a[1]*w[c*3+1]+a[2]*w[c*3+2]);
        memset(context.io.shadow+model.offset,0,model.bytes);
    }
    assert(registrations==prior+1);
    int8_t nchw[30];int32_t point[9];for(unsigned i=0;i<30;i++)nchw[i]=(int8_t)(i-11);
    assert(xqn_resident_pointwise(&context.io,nchw,30,w0,9,NULL,0,3,3,3,5,4,point,9,&st));
    for(unsigned p=0;p<3;p++)for(unsigned c=0;c<3;c++) {
        unsigned pos=4+p;int expected=0;
        for(unsigned k=0;k<3;k++)expected+=nchw[(pos/5*3+k)*5+pos%5]*w0[c*3+k];
        assert(point[p*3+c]==expected);
    }
    assert(!xqn_resident_pointwise(&context.io,nchw,30,w0,9,NULL,0,3,3,3,5,9,point,9,&st));
    int8_t unknown[9]={0};assert(!xqm_matrix(&context.io,a,3,unknown,9,NULL,0,1,3,3,result,3,&st));
    xqn_resident_layer too_big={w0,65535,1024};assert(!xqn_resident_prepare(&context.io,&too_big,1));
    assert(xqm_matrix(&context.io,a,3,w0,9,NULL,0,1,3,3,result,3,&st));
#ifdef XQ_NATIVE_TIMING
    force_run_failure=1;
    assert(!xqm_matrix(&context.io,a,3,w0,9,NULL,0,1,3,3,result,3,&st));
    force_run_failure=0;
    xqn_resident_profile profile;xqn_resident_profile_read(&profile);
    assert(profile.enabled && profile.errors==1 && profile.runs==runs);
    assert(profile.registrations==registrations && profile.calls==runs+registrations+1);
    assert(profile.cycles==(uint64_t)runs*17 && profile.ioctl_ns>0);
    xqn_resident_profile_reset();xqn_resident_profile_read(&profile);
    assert(profile.enabled && !profile.calls && !profile.ioctl_ns && !profile.cycles);
    puts("NATIVE_COUNTER_TIMING_TEST_PASS successful_jobs errors registrations reset no_fallback");
#endif
    context.resident_free(context.resident_cache);context.resident_cache=NULL;context.resident_free=NULL;
    free(context.io.shadow);free(snapshot);puts("NATIVE_RESIDENT_MATRIX_TEST_PASS bias_once deepK tails immutable_cache no_MMIO");return 0;
}
