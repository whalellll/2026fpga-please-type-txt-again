#define _POSIX_C_SOURCE 200809L
/* Inspect only private model state to seed stale heads for boundary guards.
 * Real graph/math/provider and transport oracle are linked unchanged. */
#include "../../graph_runtime.c"
#include "graph_rgb8.h"
#include <assert.h>

void *__real_malloc(size_t);
void *__real_calloc(size_t,size_t);
static unsigned fail_allocation,cancel_after_jobs,cancel_now,cancel_after_calls,cancel_calls;
static size_t fail_size;
unsigned xqih_test_job_count(void);
void xqih_test_fail_after(unsigned);
void *__wrap_malloc(size_t n)
{if(fail_allocation && !--fail_allocation)return NULL;if(fail_size==n){fail_size=0;return NULL;}return __real_malloc(n);}
void *__wrap_calloc(size_t n,size_t size)
{if(fail_allocation && !--fail_allocation)return NULL;return __real_calloc(n,size);}
static int cancellation(void *unused)
{(void)unused;++cancel_calls;return cancel_now || (cancel_after_calls && cancel_calls>=cancel_after_calls) ||
    (cancel_after_jobs && xqih_test_job_count()>=cancel_after_jobs);}
static void observer(void *unused,unsigned i,const int8_t *a,size_t n,const int16_t *b,size_t k,const int32_t *c,const int16_t *d)
{(void)unused;(void)i;(void)a;(void)n;(void)b;(void)k;(void)c;(void)d;abort();}
static void seed(xqn_model *m)
{for(unsigned i=0;i<3;i++){free(m->outputs[i]);m->outputs[i]=malloc(16);assert(m->outputs[i]);}m->batch=1;}
static void invalid(xqn_model *m,const xqm_stats *stats)
{
    xqm_stats zero={0};assert(!memcmp(stats,&zero,sizeof(zero)) && m->batch==0);
    for(unsigned i=0;i<3;i++)assert(!xqn_output(m,i,NULL));
}
static void guards(xqn_model *m,xqm_transport *io,const uint8_t *bytes,const float *floats)
{
    xqm_stats stats;unsigned before=xqih_test_job_count();
    memset(&stats,0xa5,sizeof(stats));assert(!xqn_run_rgb8(NULL,io,1,bytes,XQ_RGB8_DETECTOR_INPUT_BYTES,0,&stats));
    xqm_stats zero={0};assert(!memcmp(&stats,&zero,sizeof(zero)));
    for(unsigned mode=0;mode<6;mode++) {
        seed(m);float *old[3];memcpy(old,m->outputs,sizeof(old));memset(&stats,0xa5,sizeof(stats));
        const xqm_transport *transport=mode==4?NULL:io;
        unsigned batch=mode==1?0:mode==2?2:mode==3?257:1;int cpu=mode==5;
        const uint8_t *source=mode==0?NULL:bytes;const float *reference=mode==0?NULL:floats;
        assert(!xqn_run(m,transport,batch,reference,cpu,&stats));
        assert(!memcmp(old,m->outputs,sizeof(old)) && m->batch==1);
        assert(!xqn_run_rgb8(m,transport,batch,source,XQ_RGB8_DETECTOR_INPUT_BYTES,cpu,&stats));
        assert(!memcmp(old,m->outputs,sizeof(old)) && m->batch==1);
        xqm_stats zero={0};assert(!memcmp(&stats,&zero,sizeof(zero)));
    }
    const size_t lengths[]={0,XQ_RGB8_DETECTOR_INPUT_BYTES-1,XQ_RGB8_DETECTOR_INPUT_BYTES+1,SIZE_MAX};
    for(unsigned i=0;i<sizeof(lengths)/sizeof(*lengths);i++) {
        seed(m);assert(!xqn_run_rgb8(m,io,1,bytes,lengths[i],0,&stats));invalid(m,&stats);
    }
    seed(m);assert(!xqn_run_rgb8(m,NULL,1,bytes,XQ_RGB8_DETECTOR_INPUT_BYTES,1,&stats));invalid(m,&stats);
    seed(m);xqn_observe(m,observer,NULL);
    assert(!xqn_run_rgb8(m,io,1,bytes,XQ_RGB8_DETECTOR_INPUT_BYTES,0,&stats));invalid(m,&stats);xqn_observe(m,NULL,NULL);
    seed(m);unsigned saved=m->input_side;m->input_side=416;
    assert(!xqn_run_rgb8(m,io,1,bytes,XQ_RGB8_DETECTOR_INPUT_BYTES,0,&stats));invalid(m,&stats);m->input_side=saved;
    seed(m);saved=m->header[1];m->header[1]=0;
    assert(!xqn_run_rgb8(m,io,1,bytes,XQ_RGB8_DETECTOR_INPUT_BYTES,0,&stats));invalid(m,&stats);m->header[1]=saved;
    seed(m);xqih_detector *detector=m->hwc_detector;m->hwc_detector=NULL;
    assert(!xqn_run_rgb8(m,io,1,bytes,XQ_RGB8_DETECTOR_INPUT_BYTES,0,&stats));invalid(m,&stats);m->hwc_detector=detector;
    assert(xqih_test_job_count()==before);
    float *adapter_heads[3];for(unsigned i=0;i<3;i++){adapter_heads[i]=malloc(16);assert(adapter_heads[i]);}
    memset(&stats,0xa5,sizeof(stats));
    assert(!xqih_detect_rgb8(m->hwc_detector,io,bytes,XQ_RGB8_DETECTOR_INPUT_BYTES-1,adapter_heads,&stats));
    assert(!memcmp(&stats,&zero,sizeof(zero)));
    for(unsigned i=0;i<3;i++)assert(!adapter_heads[i]);
    assert(xqih_test_job_count()==before);
}
static void complete_pair(xqn_model *m,const xqm_transport *io,const uint8_t *bytes,const float *floats)
{
    float *expected[3];unsigned dimensions[3][4];size_t sizes[3];xqm_stats stats;
    assert(xqn_run(m,io,1,floats,0,&stats) && stats.jobs==166 && m->batch==1);
    for(unsigned i=0;i<3;i++) {
        const float *p=xqn_output(m,i,dimensions[i]);assert(p);
        sizes[i]=(size_t)dimensions[i][0]*dimensions[i][1]*dimensions[i][2]*dimensions[i][3]*4;
        expected[i]=malloc(sizes[i]);assert(expected[i]);memcpy(expected[i],p,sizes[i]);
    }
    assert(xqn_run_rgb8(m,io,1,bytes,XQ_RGB8_DETECTOR_INPUT_BYTES,0,&stats) && stats.jobs==166 && m->batch==1);
    for(unsigned i=0;i<3;i++) {
        unsigned dims[4];const float *p=xqn_output(m,i,dims);assert(p);
        assert(!memcmp(dims,dimensions[i],sizeof(dims)) && !memcmp(expected[i],p,sizes[i]));free(expected[i]);
    }
}
int main(int argc,char **argv)
{
    assert(argc==2 || (argc==3 && (!strcmp(argv[2],"--guards-only") || !strcmp(argv[2],"--pair-only"))));
    int guards_only=argc==3 && !strcmp(argv[2],"--guards-only");
    int pair_only=argc==3 && !strcmp(argv[2],"--pair-only");
    xqn_model *m=xqn_load(argv[1]);assert(m);
    uint8_t *bytes=malloc(XQ_RGB8_DETECTOR_INPUT_BYTES);float *floats=malloc(XQ_RGB8_DETECTOR_INPUT_BYTES*4u);assert(bytes && floats);
    float unit[256];for(unsigned i=0;i<256;i++)unit[i]=(float)i/255.f;
    for(size_t i=0;i<XQ_RGB8_DETECTOR_INPUT_BYTES;i++){bytes[i]=(uint8_t)(i*71u+13u+(i>>9));floats[i]=unit[bytes[i]];}
    xqm_linux device;assert(xqm_linux_open(&device));device.io.cancelled=cancellation;xqm_stats stats;
    if(pair_only) {
        complete_pair(m,&device.io,bytes,floats);
        xqn_free(m);xqm_linux_close(&device);free(bytes);free(floats);
        puts("RGB8_GRAPH_API_COMPLETE_THREE_HEADS_PAIR_PASS_NOT_BOARD");return 0;
    }
    guards(m,&device.io,bytes,floats);
    seed(m);unsigned features=device.features;device.features&=~PANGO_MAC_FEATURE_VISION32_EXACT;
    assert(!xqn_run_rgb8(m,&device.io,1,bytes,XQ_RGB8_DETECTOR_INPUT_BYTES,0,&stats));invalid(m,&stats);device.features=features;
    seed(m);cancel_now=1;assert(!xqn_run_rgb8(m,&device.io,1,bytes,XQ_RGB8_DETECTOR_INPUT_BYTES,0,&stats));invalid(m,&stats);cancel_now=0;
    seed(m);cancel_calls=0;cancel_after_calls=2;
    assert(!xqn_run_rgb8(m,&device.io,1,bytes,XQ_RGB8_DETECTOR_INPUT_BYTES,0,&stats));invalid(m,&stats);cancel_after_calls=0;
    for(unsigned failure=1;failure<=2;failure++) {
        seed(m);fail_allocation=failure;
        assert(!xqn_run_rgb8(m,&device.io,1,bytes,XQ_RGB8_DETECTOR_INPUT_BYTES,0,&stats));invalid(m,&stats);assert(!fail_allocation);
    }
    unsigned before=xqih_test_job_count();seed(m);cancel_after_jobs=before+1;
    assert(!xqn_run_rgb8(m,&device.io,1,bytes,XQ_RGB8_DETECTOR_INPUT_BYTES,0,&stats));invalid(m,&stats);assert(xqih_test_job_count()==before+1);cancel_after_jobs=0;
    before=xqih_test_job_count();seed(m);xqih_test_fail_after(before+1);
    assert(!xqn_run_rgb8(m,&device.io,1,bytes,XQ_RGB8_DETECTOR_INPUT_BYTES,0,&stats));invalid(m,&stats);assert(xqih_test_job_count()==before+1);xqih_test_fail_after(0);
    if(!guards_only) {
        complete_pair(m,&device.io,bytes,floats);
        /* A head allocation fails only after the 166-job graph completed;
         * every already allocated public head must still be invalidated. */
        before=xqih_test_job_count();fail_size=57u*80u*80u*4u;
        assert(!xqn_run_rgb8(m,&device.io,1,bytes,XQ_RGB8_DETECTOR_INPUT_BYTES,0,&stats));invalid(m,&stats);
        assert(!fail_size && xqih_test_job_count()==before+166);
        /* Reusing the same model after all failures must recover byte-exact. */
        complete_pair(m,&device.io,bytes,floats);
    }
    xqn_free(m);xqm_linux_close(&device);free(bytes);free(floats);
    puts(guards_only?"RGB8_GRAPH_API_PREFLIGHT_RETENTION_HWC_INVALIDATION_EARLY_FAILURE_PASS_NOT_FULL_HEADS":
         "RGB8_GRAPH_API_OLD_FLOAT_COMPLETE_THREE_HEADS_FAILURE_RECOVERY_PASS_NOT_BOARD");
    return 0;
}
