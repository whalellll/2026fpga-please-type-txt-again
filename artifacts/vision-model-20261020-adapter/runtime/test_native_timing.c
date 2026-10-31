#include <assert.h>
#include <stdint.h>
#include <stdio.h>
static uint64_t fake_clock;
#define XQ_NATIVE_TIMING 1
#define XNT_CLOCK_NS() fake_clock
#include "xq_native_timing.h"
int main(void)
{
    xnt_profile p;fake_clock=100;xnt_begin(&p);
    fake_clock=500;xnt_step(&p,XNT_GRAPH);
    fake_clock=3000;xnt_step(&p,XNT_POST);
    fake_clock=3500;xnt_step(&p,XNT_REFINE);
    fake_clock=4500;xnt_step(&p,XNT_ASSIGN);
    fake_clock=4800;xnt_step(&p,XNT_STOP);
    assert(p.ns[XNT_PREPARE]==400 && p.ns[XNT_GRAPH]==2500 && p.ns[XNT_POST]==500);
    assert(p.ns[XNT_REFINE]==1000 && p.ns[XNT_ASSIGN]==300 && !p.clock_errors);
    uint64_t sum=0;for(unsigned i=0;i<XNT_STOP;i++)sum+=p.ns[i];
    assert(sum==p.last_ns-p.start_ns && sum==4700);
    fake_clock=6000;xnt_begin(&p);fake_clock=5999;xnt_step(&p,XNT_GRAPH);
    assert(p.clock_errors==1 && p.ns[XNT_PREPARE]==0);
    puts("NATIVE_PHASE_TIMING_TEST_PASS closed_accounting backwards_clock_rejected");return 0;
}
