#include "xq_native_graph.h"
#include "test_v321_mock.h"
#include "xq_sha256.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned allocations,fail_at;
void *__real_malloc(size_t);
void *__wrap_malloc(size_t bytes)
{
    allocations++;
    return fail_at && allocations==fail_at?NULL:__real_malloc(bytes);
}
static int cancelled(void *context) { (void)context;return 1; }
int main(int argc,char **argv)
{
    assert(argc==4);
    /* Mutated metadata fixtures retain valid body CRCs and frozen weights. */
    assert(!xqn_load(argv[2]) && !xqn_load(argv[3]));
    xqn_model *m=xqn_load(argv[1]);assert(m && xqn_input_side(m)==32);
    xqm_linux device={.fd=-1};assert(v321_mock_open(&device));
    const size_t count=3u*3u*32u*32u;
    float *input=malloc(count*4);assert(input);
    for(size_t i=0;i<count;i++)input[i]=(float)((int)(i%127)-63)/128.f;
    xqm_stats stats={0};unsigned dims[4];
    assert(xqn_run(m,NULL,3,input,1,&stats));
    const float *out=xqn_output(m,0,dims);
    assert(out && dims[0]==3 && dims[1] && dims[2]==1 && dims[3]==1);
    size_t bytes=(size_t)dims[0]*dims[1]*4;
    float *expected=malloc(bytes);assert(expected);memcpy(expected,out,bytes);
    v321_mock_reset(0);
    assert(xqn_run(m,&device.io,3,input,0,&stats));
    out=xqn_output(m,0,NULL);assert(out && !memcmp(out,expected,bytes));
    char hash[65];xq_sha256_hex(out,bytes,hash);
    printf("GRAPH_RUNTIME_BATCH3 sha256=%s\n",hash);
    /* A later inference failure must invalidate every output from that model. */
    v321_mock_reset(2);
    assert(!xqn_run(m,&device.io,3,input,0,&stats));
    assert(!xqn_output(m,0,NULL));
    v321_mock_counts counters;v321_mock_read(&counters);
    assert(counters.jobs==1 && counters.errors==1 && counters.attempts==2);
    v321_mock_reset(0);device.io.cancelled=cancelled;
    assert(!xqn_run(m,&device.io,3,input,0,&stats) && !xqn_output(m,0,NULL));
    v321_mock_read(&counters);assert(!counters.attempts);
    device.io.cancelled=NULL;
    allocations=0;fail_at=1;
    assert(!xqn_run(m,&device.io,3,input,0,&stats) && !xqn_output(m,0,NULL));
    fail_at=0;
    assert(xqn_run(m,&device.io,3,input,0,&stats));
    out=xqn_output(m,0,NULL);assert(out && !memcmp(out,expected,bytes));
    free(expected);free(input);xqn_free(m);v321_mock_close(&device);
    puts("GRAPH_RUNTIME_REUSE_CANCEL_IOCTL_OOM_AND_BAD_LIVENESS_PASS");return 0;
}
