#ifndef XQ_NATIVE_TIMING_H
#define XQ_NATIVE_TIMING_H
#include <stdint.h>
enum { XNT_PREPARE,XNT_GRAPH,XNT_POST,XNT_REFINE,XNT_ASSIGN,XNT_STOP };
#ifdef XQ_NATIVE_TIMING
#include <string.h>
#include <time.h>
typedef struct {
    uint64_t start_ns,last_ns,ns[XNT_STOP];
    unsigned phase,clock_errors;
} xnt_profile;
static inline uint64_t xnt_now(xnt_profile *p)
{
#ifdef XNT_CLOCK_NS
    (void)p;return XNT_CLOCK_NS();
#else
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t)){++p->clock_errors;return 0;}
    return (uint64_t)t.tv_sec*1000000000u+(unsigned)t.tv_nsec;
#endif
}
static inline void xnt_begin(xnt_profile *p)
{
    memset(p,0,sizeof(*p));p->start_ns=p->last_ns=xnt_now(p);
}
static inline void xnt_step(xnt_profile *p,unsigned next)
{
    uint64_t end=xnt_now(p);
    if(end<p->last_ns)++p->clock_errors;
    else if(p->phase<XNT_STOP)p->ns[p->phase]+=end-p->last_ns;
    p->last_ns=end;p->phase=next;
}
#else
typedef struct {unsigned unused;} xnt_profile;
static inline void xnt_begin(xnt_profile *p){(void)p;}
static inline void xnt_step(xnt_profile *p,unsigned next){(void)p;(void)next;}
#endif
#endif
