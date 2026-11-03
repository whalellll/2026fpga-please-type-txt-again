#define XQ_MATCHED_BENCH_ENTRY xqtest_bench_entry
#include "../matched_bench.c"
#include <assert.h>
unsigned xqih_test_job_count(void);
int main(void)
{
    char *argv[]={"matched-bench",NULL};assert(xqtest_bench_entry(1,argv)==2);
    assert(!bench_cancelled(NULL));assert(!raise(SIGTERM) && bench_cancelled(NULL));
    xqm_linux device={.fd=-1};unsigned before=xqih_test_job_count();
    assert(bench_open(&device) && device.io.cancelled && device.io.cancelled(device.io.context));
    assert(xqih_test_job_count()==before);xqm_linux_close(&device);
    assert(xqtest_bench_entry(1,argv)==2 && !bench_cancelled(NULL));
    assert(!raise(SIGINT) && bench_cancelled(NULL));
    puts("MATCHED_BENCH_SIGINT_TERM_DRIVER_CALLBACK_NO_JOB_PASS_NOT_BOARD");return 0;
}
