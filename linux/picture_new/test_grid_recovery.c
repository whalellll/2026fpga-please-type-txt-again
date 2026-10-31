#define _POSIX_C_SOURCE 200809L
#include "board_grid_recovery.h"
#include "xq_roi.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static unsigned allocations,cancel_calls,cancel_after;
static int allocation_fail;
void *__real_calloc(size_t,size_t);
void *__wrap_calloc(size_t n,size_t z)
{allocations++;return allocation_fail?NULL:__real_calloc(n,z);}
static int cancel(void *p)
{(void)p;return ++cancel_calls>=cancel_after;}
static void zero(const float v[8])
{for(unsigned i=0;i<8;i++)assert(v[i]==0);}
static void load(const char *p,void *out,size_t bytes)
{FILE *f=fopen(p,"rb");assert(f && fread(out,1,bytes,f)==bytes && fgetc(f)==EOF && !fclose(f));}
static void synthetic_grid(uint8_t *rgb)
{
    /* Independent geometry fixture: no model output, photograph or piece map.
     * The two complete line families have nine and ten intersections. */
    memset(rgb,210,1280u*720u*3u);
    for(unsigned y=157;y<=613;y++)for(unsigned x=217;x<=863;x++){
        int vertical=x>=219 && x<=861 && (x+21)%80<4;
        int horizontal=y>=159 && y<=611 && (y+41)%50<4;
        if(vertical || horizontal){uint8_t *p=rgb+((size_t)y*1280+x)*3;p[0]=p[1]=p[2]=20;}
    }
}
static void synthetic_recovery(uint8_t *rgb)
{
    const float good[8]={220.5f/1280,160.5f/720,860.5f/1280,160.5f/720,
                        860.5f/1280,610.5f/720,220.5f/1280,610.5f/720};
    float bad[8],out[8];xqgrid_stats st;synthetic_grid(rgb);
    for(unsigned corner=0;corner<4;corner++){
        memcpy(bad,good,sizeof(bad));
        bad[2*corner]+=(corner==0 || corner==3)?-.07f:.07f;
        bad[2*corner+1]+=(corner<2)?-.08f:.08f;
        assert(xqgrid_recover(rgb,1280u*720u*3u,bad,out,NULL,NULL,&st));
        assert(st.attempted && st.used && st.corner==corner);
        for(unsigned i=0;i<8;i++){
            if(i/2!=corner)assert(out[i]==bad[i]);
            else assert(fabs((out[i]-good[i])*(i%2?720:1280))<6);
        }
    }
    /* Insufficient original support must not replace either bad corner. */
    memcpy(bad,good,sizeof(bad));bad[0]-=.08f;bad[1]-=.1f;bad[2]+=.07f;bad[3]-=.08f;
    assert(xqgrid_recover(rgb,1280u*720u*3u,bad,out,NULL,NULL,&st));
    assert(st.attempted && !st.used && !memcmp(out,bad,sizeof(out)));
    /* Alias safety also applies to a real replacement, not just the no-op. */
    memcpy(out,good,sizeof(out));out[2]+=.07f;out[3]-=.08f;
    assert(xqgrid_recover(rgb,1280u*720u*3u,out,out,NULL,NULL,&st) && st.used && st.corner==1);
    for(unsigned i=0;i<8;i++)assert(fabs((out[i]-good[i])*(i%2?720:1280))<6);
    puts("GRID_SYNTHETIC_FOUR_CORNERS_RECOVER_TWO_BAD_UNCHANGED_ALIAS_PASS_NOT_BOARD");
}
int main(int argc,char **argv)
{
    const size_t bytes=1280u*720u*3u;uint8_t *rgb=malloc(bytes);assert(rgb);
    if(argc==5 && !strcmp(argv[1],"--private-rgb565")){
        uint32_t *raw=malloc(1843200);float corners[8],out[8];assert(raw);
        load(argv[2],raw,1843200);load(argv[3],corners,sizeof(corners));
        xqv_frame frame={0};frame.rgb565=raw;frame.bytes=1843200;
        assert(xqr_rgb565(&frame,rgb,bytes));xqgrid_stats st;struct timespec a,b;
        assert(!clock_gettime(CLOCK_MONOTONIC,&a));
        assert(xqgrid_recover(rgb,bytes,corners,out,NULL,NULL,&st));
        assert(!clock_gettime(CLOCK_MONOTONIC,&b));
        FILE *f=fopen(argv[4],"wbx");assert(f && fwrite(out,4,8,f)==8 && !fclose(f));
        printf("GRID_PRIVATE_RECOVERY attempted=%u used=%u corner=%u edges=%u elapsed_ns=%lld\n",
            st.attempted,st.used,st.corner,st.edges,(long long)(b.tv_sec-a.tv_sec)*1000000000+b.tv_nsec-a.tv_nsec);
        free(raw);free(rgb);return 0;
    }
    assert(argc==2 && !strcmp(argv[1],"--synthetic"));memset(rgb,210,bytes);
    float normal[8]={.2f,.2f,.8f,.2f,.8f,.8f,.2f,.8f},bad[8],out[8];xqgrid_stats st;
    unsigned n=allocations;
    assert(xqgrid_recover(rgb,bytes,normal,out,NULL,NULL,&st));
    assert(!st.attempted && !st.used && allocations==n && !memcmp(normal,out,sizeof(out)));
    memcpy(out,normal,sizeof(out));assert(xqgrid_recover(rgb,bytes,out,out,NULL,NULL,&st));
    assert(!memcmp(out,normal,sizeof(out)));
    memcpy(bad,normal,sizeof(bad));bad[2]=.97f;bad[3]=.05f;
    assert(xqgrid_recover(rgb,bytes,bad,out,NULL,NULL,&st));
    assert(st.attempted && !st.used && !st.edges && !memcmp(out,bad,sizeof(out)));
    cancel_calls=0;cancel_after=1;
    assert(!xqgrid_recover(rgb,bytes,bad,out,cancel,NULL,&st) && st.cancelled);zero(out);
    cancel_calls=0;cancel_after=8;
    assert(!xqgrid_recover(rgb,bytes,bad,out,cancel,NULL,&st) && st.cancelled);zero(out);
    allocation_fail=1;assert(!xqgrid_recover(rgb,bytes,bad,out,NULL,NULL,&st));zero(out);allocation_fail=0;
    bad[0]=NAN;assert(!xqgrid_recover(rgb,bytes,bad,out,NULL,NULL,&st));zero(out);
    assert(!xqgrid_recover(rgb,bytes-1,normal,out,NULL,NULL,&st));zero(out);
    synthetic_recovery(rgb);
    free(rgb);puts("GRID_NOOP_ALIAS_BLANK_CANCEL_OOM_INVALID_NO_OLD_GEOMETRY_PASS_NOT_BOARD");return 0;
}
