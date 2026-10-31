#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stddef.h>
static unsigned last_phase;static size_t last_index;
static void cancel_note(unsigned p,size_t n){last_phase=p;last_index=n;}
#define XQGC_NOTE(phase,index) cancel_note(phase,index)
#include "geometry_cancel.h"
#include GEOMETRY_SOURCE
#include "xq_sha256.h"
#include <assert.h>

static int armed,requested,cancel_on_integral;
static unsigned allocations,after_cancel,live,fail_at,target_phase,callbacks,allocator_depth;
static size_t target_index;
static void *tracked[32];
void *__real_malloc(size_t);void *__real_calloc(size_t,size_t);void __real_free(void *);
static void record(void *p)
{
    if(!armed)return;
    ++allocations;if(requested)++after_cancel;
    if(p){unsigned i=0;while(i<32 && tracked[i])i++;assert(i<32);tracked[i]=p;live++;}
}
void *__wrap_malloc(size_t n)
{
    /* Static musl calloc calls public malloc; count its outer allocation once. */
    if(allocator_depth)return __real_malloc(n);
    void *p=armed && fail_at==allocations+1?NULL:__real_malloc(n);record(p);return p;
}
void *__wrap_calloc(size_t n,size_t z)
{
    allocator_depth++;
    void *p=armed && fail_at==allocations+1?NULL:__real_calloc(n,z);
    allocator_depth--;record(p);
    if(armed && cancel_on_integral && z==sizeof(double) && n>1000)requested=1;
    return p;
}
void __wrap_free(void *p)
{
    if(p)for(unsigned i=0;i<32;i++)if(tracked[i]==p){tracked[i]=NULL;assert(live);live--;break;}
    __real_free(p);
}
static int cancel(void *p)
{
    assert(p==&requested);callbacks++;
    if(target_phase && last_phase==target_phase && last_index>=target_index)requested=1;
    return requested;
}
static int invoke(const uint8_t *rgb,const double q[4][2],const xqr_box *boxes,unsigned count,
    const uint8_t rng[91][240][4],double corners[4][2],xnp_refinement *stats)
{
#if defined(XQ_GEOMETRY_CANCEL) && XQ_GEOMETRY_CANCEL
    return xqcoach_refine_cancellable(rgb,q,boxes,count,rng,corners,stats,cancel,&requested);
#else
    /* Current guard's real before/after boundary, without internal probes. */
    int okay=0;
    if(!cancel(&requested))okay=xnp_refine(rgb,q,boxes,count,rng,corners,stats);
    if(cancel(&requested)){memset(corners,0,8*sizeof(double));memset(stats,0,sizeof(*stats));return 0;}
    return okay;
#endif
}
static void reset(void)
{
    assert(!live && !allocator_depth);memset(tracked,0,sizeof(tracked));armed=requested=cancel_on_integral=0;
    allocations=after_cancel=fail_at=target_phase=callbacks=last_phase=0;target_index=last_index=0;
}
static void zero(const void *p,size_t n)
{for(size_t i=0;i<n;i++)assert(!((const unsigned char *)p)[i]);}
static void signature(const char *label,int okay,const double q[4][2],const xnp_refinement *stats)
{
    char a[65],b[65];xq_sha256_hex(q,8*sizeof(double),a);xq_sha256_hex(stats,sizeof(*stats),b);
    printf("GEOMETRY_CANCEL_BITS %s result=%d corners=%s stats=%s\n",label,okay,a,b);
}
int main(int argc,char **argv)
{
    assert(argc==3);uint8_t *rgb=malloc(1280u*720u*3u),(*rng)[240][4]=malloc(91*240*4);
    assert(rgb && rng && xnp_load_rng(argv[1],rng));
    double q[4][2]={{150,100},{1050,100},{1050,620},{150,620}},seed[9];assert(xnp_coarse(q,seed,NULL));
    xqr_box boxes[8];
    for(unsigned i=0;i<8;i++){double p[2];assert(point(seed,i+1,i%7+1,p));boxes[i]=(xqr_box){p[0]-8,p[1]-8,p[0]+8,p[1]+8,.9f,4};}
    memset(rgb,255,1280u*720u*3u);
    for(unsigned gy=0;gy<9;gy++)for(unsigned gx=0;gx<10;gx++){
        double p[2];assert(point(seed,gx,gy,p));int x=round_even(p[0]),y=round_even(p[1]);
        for(int d=-19;d<=19;d++)for(int t=-1;t<=1;t++){
            int xx=x+d,yy=y+t;if(xx>=0 && yy>=0 && xx<1280 && yy<720)memset(rgb+((size_t)yy*1280+(unsigned)xx)*3,0,3);
            xx=x+t;yy=y+d;if(xx>=0 && yy>=0 && xx<1280 && yy<720)memset(rgb+((size_t)yy*1280+(unsigned)xx)*3,0,3);
        }
    }
    double expected[4][2]={{0}},actual[4][2];xnp_refinement expected_stats={0},stats;
    reset();int okay=xnp_refine(rgb,q,boxes,8,rng,expected,&expected_stats);assert(okay);
    signature("reference",okay,expected,&expected_stats);
    if(!strcmp(argv[2],"--reference")){free(rgb);free(rng);return 0;}
    reset();armed=1;cancel_on_integral=1;memset(actual,0xa5,sizeof(actual));memset(&stats,0xa5,sizeof(stats));
    assert(!invoke(rgb,q,boxes,8,rng,actual,&stats));armed=0;
    printf("GEOMETRY_CANCEL_ALLOC_AUDIT requested=%d live=%u allocations=%u callbacks=%u\n",requested,live,allocations,callbacks);fflush(stdout);
    assert(requested && !live);zero(actual,sizeof(actual));zero(&stats,sizeof(stats));
    printf("GEOMETRY_CANCEL_INTEGRAL_REPRO allocations_after_cancel=%u\n",after_cancel);fflush(stdout);
    assert(after_cancel==0);
#if defined(XQ_GEOMETRY_CANCEL) && XQ_GEOMETRY_CANCEL
    for(unsigned phase=XQGC_START;phase<=XQGC_FINAL;phase++){
        reset();target_phase=phase;armed=1;memset(actual,0xa5,sizeof(actual));memset(&stats,0xa5,sizeof(stats));
        assert(!invoke(rgb,q,boxes,8,rng,actual,&stats));armed=0;
        assert(requested && callbacks && !live);zero(actual,sizeof(actual));zero(&stats,sizeof(stats));
    }
    for(unsigned at=1;at<=9;at++){
        reset();fail_at=at;armed=1;memset(actual,0,sizeof(actual));
        okay=invoke(rgb,q,boxes,8,rng,actual,&stats);armed=0;assert(!live);
        if(allocations<at){assert(okay);break;}assert(!okay);
    }
    reset();armed=1;memset(actual,0,sizeof(actual));assert(invoke(rgb,q,boxes,8,rng,actual,&stats));armed=0;
    assert(!live && !memcmp(actual,expected,sizeof(actual)) && !memcmp(&stats,&expected_stats,sizeof(stats)));
    puts("GEOMETRY_REAL_CANCEL_13_PHASES_OOM_RECOVERY_EXACT_PASS_NOT_BOARD");
#else
    (void)cancel_note;
#endif
    free(rgb);free(rng);return 0;
}
