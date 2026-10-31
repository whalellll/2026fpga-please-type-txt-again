/* Extend the real adapter boundary test, keeping its original assertions. */
#define main original_product_checks
#define __wrap_malloc original_wrap_malloc
#define __wrap_calloc original_wrap_calloc
#include "product_adapter.c"
#undef __wrap_calloc
#undef __wrap_malloc
#undef main
#include <string.h>

static unsigned count_allocations,allocations;
static size_t last_sizes[3];
void *__wrap_malloc(size_t n)
{if(count_allocations){last_sizes[allocations%3]=n;++allocations;}return original_wrap_malloc(n);}
void *__wrap_calloc(size_t n,size_t size)
{if(count_allocations){last_sizes[allocations%3]=n*size;++allocations;}return original_wrap_calloc(n,size);}

int main(int argc,char **argv)
{
    assert(original_product_checks(argc,argv)==0);
    xqn_model *m=xqn_load(argv[1]);assert(m);
    float *input=malloc(3u*640u*640u*4);assert(input);
    FILE *f=fopen(argv[2],"rb");assert(f);
    assert(fread(input,4,3u*640u*640u,f)==3u*640u*640u && fgetc(f)==EOF && !ferror(f));
    assert(!fclose(f));
    xqm_linux device;assert(xqm_linux_open(&device));device.io.cancelled=cancelled;
    xqm_stats st;
    allocations=0;count_allocations=1;
    assert(xqn_run(m,&device.io,1,input,0,&st) && st.jobs==166);
    count_allocations=0;assert(allocations>=6);
    assert(last_sizes[(allocations-3)%3]==1459200);
    assert(last_sizes[(allocations-2)%3]==364800);
    assert(last_sizes[(allocations-1)%3]==91200);
    /* The retained F32 API still rejects non-finite tensors before any job,
     * including when it shares the new byte entry's execution/cleanup tail. */
    uint32_t saved_input,invalid_float[]={0x7fc12345u,0x7f800000u,0xff800000u};
    memcpy(&saved_input,input,4);
    for(unsigned i=0;i<sizeof(invalid_float)/sizeof(*invalid_float);i++) {
        unsigned before=xqih_test_job_count();memcpy(input,invalid_float+i,4);
        assert(!xqn_run(m,&device.io,1,input,0,&st));invalid(m);
        assert(xqih_test_job_count()==before);
    }
    memcpy(input,&saved_input,4);
    /* The last three allocations are the output heads. Also sample an
     * intermediate graph allocation, in addition to the old early failures. */
    unsigned failures[]={1,2,allocations/2,allocations-2,allocations-1,allocations};
    for(unsigned i=0;i<sizeof(failures)/sizeof(*failures);i++) {
        fail_allocation=failures[i];
        assert(!xqn_run(m,&device.io,1,input,0,&st));
        invalid(m);assert(!fail_allocation);
    }
    const unsigned offsets[]={1,83,165};
    for(unsigned i=0;i<sizeof(offsets)/sizeof(*offsets);i++) {
        unsigned before=xqih_test_job_count();
        xqih_test_fail_after(before+offsets[i]);
        assert(!xqn_run(m,&device.io,1,input,0,&st));invalid(m);
        assert(xqih_test_job_count()==before+offsets[i]);xqih_test_fail_after(0);
    }
    const unsigned cancels[]={1,83,166};
    for(unsigned i=0;i<sizeof(cancels)/sizeof(*cancels);i++) {
        unsigned before=xqih_test_job_count();cancel_after_jobs=before+cancels[i];
        assert(!xqn_run(m,&device.io,1,input,0,&st));invalid(m);
        assert(xqih_test_job_count()==before+cancels[i]);cancel_after_jobs=0;
    }
    /* Recovery on the same model must replace invalid outputs with three
     * complete heads, rather than retaining a stale successful result. */
    assert(xqn_run(m,&device.io,1,input,0,&st) && st.jobs==166);
    f=fopen(argv[3],"rb");assert(f);
    for(unsigned i=0;i<3;i++) {
        unsigned dims[4],expected_dims[4];const float *values=xqn_output(m,i,dims);assert(values);
        assert(fread(expected_dims,4,4,f)==4 && !memcmp(dims,expected_dims,sizeof(dims)));
        size_t count=(size_t)dims[0]*dims[1]*dims[2]*dims[3];float expected[256];
        for(size_t at=0;at<count;at+=256) {
            size_t n=count-at<256?count-at:256;
            assert(fread(expected,4,n,f)==n && !memcmp(values+at,expected,n*4));
        }
    }
    assert(fgetc(f)==EOF && !ferror(f) && !fclose(f));
    xqn_free(m);free(input);xqm_linux_close(&device);
    printf("HWC_CANDIDATE_EARLY_MIDDLE_HEAD_OOM_IO_CANCEL_AND_RECOVERY_PASS allocations=%u\n",allocations);
    return 0;
}
