#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
static uint64_t selected_reductions,omitted_reductions;
#ifdef XQGEOM_TEST_REDUCE
#define XQGEOM_REDUCE_NOTE(computed) ((computed)?++selected_reductions:++omitted_reductions)
#endif
#include GEOMETRY_SOURCE
#include "xq_sha256.h"
#include <assert.h>
#include <time.h>
#ifdef XQGEOM_TEST_ALLOC_FAIL
static int fail_allocation=-1,allocation_calls;
void *__real_malloc(size_t);
void *__real_calloc(size_t,size_t);
void *__wrap_malloc(size_t n)
{int fail=fail_allocation>=0 && allocation_calls++==fail_allocation;return fail?NULL:__real_malloc(n);}
void *__wrap_calloc(size_t n,size_t size)
{int fail=fail_allocation>=0 && allocation_calls++==fail_allocation;return fail?NULL:__real_calloc(n,size);}
static void allocation_failures(const uint8_t *rgb,const double q[4][2],const xqr_box *boxes,
                                 const uint8_t rng[91][240][4])
{
    unsigned checked=0;
    for(int at=0;at<16;at++) {
        double refined[4][2]={{0}};xnp_refinement stats={0};
        fail_allocation=at;allocation_calls=0;
        int okay=xnp_refine(rgb,q,boxes,8,rng,refined,&stats);
        fail_allocation=-1;
        if(allocation_calls<=at){assert(okay);break;}
        assert(!okay);++checked;
    }
    assert(checked>=8);
    printf("GEOMETRY_ALLOCATION_FAILURES_PASS count=%u\n",checked);
}
#endif
static void digest(const char *name,const void *data,size_t bytes)
{char hash[65];xq_sha256_hex(data,bytes,hash);printf("GEOMETRY_BITS %s %s\n",name,hash);}
static void refine(const uint8_t *rgb,const double q[4][2],const xqr_box *boxes,unsigned n,
                   const uint8_t rng[91][240][4],unsigned repeat)
{
    for(unsigned i=0;i<repeat;i++){
        double refined[4][2]={{0}};xnp_refinement stats={0};struct timespec a,b;
        assert(!clock_gettime(CLOCK_MONOTONIC,&a));int result=xnp_refine(rgb,q,boxes,n,rng,refined,&stats);
        assert(!clock_gettime(CLOCK_MONOTONIC,&b));
        printf("GEOMETRY_RESULT pass=%d crossings=%u inliers=%u\n",result,stats.crossings,stats.inliers);
        digest("corners",refined,sizeof(refined));digest("statistics",&stats,sizeof(stats));
        printf("GEOMETRY_HOST_OR_QEMU_NS %lld\n",(long long)(b.tv_sec-a.tv_sec)*1000000000+b.tv_nsec-a.tv_nsec);
    }
}
#if defined(XQ_GEOMETRY_SELECTIVE) && XQ_GEOMETRY_SELECTIVE
static void selective_boundaries(void)
{
    double in[15],expected[15],actual[15],previous[15];
    xqgeom_count_value counts[15];xqgeom_mask_value mask[15];
    for(unsigned i=0;i<15;i++) {
        in[i]=(i+1)*(1./19.);counts[i]=i%3+47;mask[i]=i%2;previous[i]=(int)(i%3)-1;
    }
    assert(box_sum(in,1,2,expected,5,3));
    for(unsigned mode=0;mode<8;mode++) {
#ifdef XQGEOM_TEST_REDUCE
        uint64_t before=omitted_reductions;unsigned skipped=0;
#endif
        assert(box_sum_selected(in,1,2,actual,5,3,mode&1?counts:NULL,mode&2?mask:NULL,mode&4?previous:NULL));
        for(unsigned i=0;i<15;i++) {
            int omit=((mode&1) && counts[i]<48) || ((mode&2) && mask[i]<.5) || ((mode&4) && previous[i]<0);
            if(omit){uint64_t bits;memcpy(&bits,actual+i,8);assert(bits==0);
#ifdef XQGEOM_TEST_REDUCE
                ++skipped;
#endif
            }
            else assert(!memcmp(expected+i,actual+i,8));
        }
#ifdef XQGEOM_TEST_REDUCE
        assert(omitted_reductions-before==skipped);
#endif
    }
}
#endif
int main(int argc,char **argv)
{
#if defined(XQ_GEOMETRY_SELECTIVE) && XQ_GEOMETRY_SELECTIVE
    selective_boundaries();
#endif
    if(argc==3 && !strcmp(argv[1],"--private-fixture")){
        FILE *f=fopen(argv[2],"rb");assert(f);char magic[8];unsigned n;double q[4][2];xqr_box boxes[300];
        uint8_t (*rng)[240][4]=malloc(91*240*4),*rgb=malloc(PIXELS*3);assert(rng && rgb);
        assert(fread(magic,1,8,f)==8 && !memcmp(magic,"XQGEOM1",8) && fread(&n,4,1,f)==1 && n<=300);
        assert(fread(q,8,8,f)==8 && fread(boxes,24,n,f)==n && fread(rng,1,91*240*4,f)==91*240*4 && fread(rgb,1,PIXELS*3,f)==PIXELS*3 && fgetc(f)==EOF);fclose(f);
        refine(rgb,q,boxes,n,rng,3);free(rgb);free(rng);
        printf("GEOMETRY_REDUCTIONS retained=%llu omitted=%llu\n",(unsigned long long)selected_reductions,(unsigned long long)omitted_reductions);return 0;
    }
    assert(argc==3 && !strcmp(argv[1],"--synthetic"));
    unsigned shapes[6][4]={{1,1,15,15},{2,3,13,1},{31,17,1,13},{320,192,15,15},{1280,720,1,13},{607,473,15,15}};
    for(unsigned test=0;test<6;test++){
        unsigned w=shapes[test][0],h=shapes[test][1];size_t n=(size_t)w*h;
        double *in=malloc(n*8),*out=malloc(n*8);assert(in && out);
        for(size_t i=0;i<n;i++)in[i]=((int)(((uint32_t)i*1664525u+1013904223u)%10001)-5000)*(1./19.);
        assert(box_sum(in,shapes[test][3],shapes[test][2],out,w,h));char name[30];snprintf(name,sizeof(name),"box_sum_%u",test);digest(name,out,n*8);free(in);free(out);
    }
    uint8_t (*rng)[240][4]=malloc(91*240*4),*rgb=malloc(PIXELS*3);assert(rng && rgb && xnp_load_rng(argv[2],rng));
    double q[4][2]={{150,100},{1050,100},{1050,620},{150,620}},seed[9];assert(xnp_coarse(q,seed,NULL));
    memset(rgb,255,PIXELS*3);refine(rgb,q,NULL,0,rng,1);
    for(unsigned gy=0;gy<9;gy++)for(unsigned gx=0;gx<10;gx++){
        double p[2];assert(point(seed,gx,gy,p));int x=round_even(p[0]),y=round_even(p[1]);
        for(int d=-19;d<=19;d++)for(int t=-1;t<=1;t++){
            int xx=x+d,yy=y+t;if(xx>=0 && yy>=0 && xx<1280 && yy<720)memset(rgb+((size_t)yy*1280+(unsigned)xx)*3,0,3);
            xx=x+t;yy=y+d;if(xx>=0 && yy>=0 && xx<1280 && yy<720)memset(rgb+((size_t)yy*1280+(unsigned)xx)*3,0,3);
        }
    }
    refine(rgb,q,NULL,0,rng,1);
    xqr_box boxes[8];for(unsigned i=0;i<8;i++){double p[2];assert(point(seed,i+1,i%7+1,p));boxes[i]=(xqr_box){p[0]-8,p[1]-8,p[0]+8,p[1]+8,.9f,0};}
    refine(rgb,q,boxes,8,rng,1);
#ifdef XQGEOM_TEST_ALLOC_FAIL
    allocation_failures(rgb,q,boxes,rng);
#endif
    free(rgb);free(rng);
    printf("GEOMETRY_REDUCTIONS retained=%llu omitted=%llu\n",(unsigned long long)selected_reductions,(unsigned long long)omitted_reductions);return 0;
}
