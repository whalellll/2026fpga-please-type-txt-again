#define _POSIX_C_SOURCE 200809L
/* Test-only gate in real geometry; never linked into a deployment worker. */
#include "test_geometry_cancel_notify.h"
#include "geometry_cancel.h"
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>
void xqgc_test_note(unsigned phase,size_t index)
{
    static int fired;
    const char *path=getenv("XQGC_TEST_REQUEST");
    if(!path || fired || phase!=XQGC_PREFIX_COLUMN || index!=16)return;
    fired=1;puts("GEOMETRY_CANCEL_TEST_REAL_PREFIX_STARTED");fflush(stdout);
    struct timespec a,b,pause={0,5000000};clock_gettime(CLOCK_MONOTONIC,&a);
    while(!access(path,F_OK)){
        clock_gettime(CLOCK_MONOTONIC,&b);if(b.tv_sec-a.tv_sec>=3)break;
        nanosleep(&pause,NULL);
    }
}
