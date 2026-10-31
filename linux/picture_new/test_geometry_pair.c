#define _POSIX_C_SOURCE 200809L
#include "xq_native_post.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

_Static_assert(sizeof(xqr_box)==24,"frozen fixture box ABI");
_Static_assert(sizeof(unsigned)==4 && sizeof(double)==8,"frozen fixture numeric ABI");

typedef int (*refine_fn)(const uint8_t *,const double [4][2],const xqr_box *,unsigned,
                        const uint8_t [91][240][4],double [4][2],xnp_refinement *);
extern int baseline_refine(const uint8_t *,const double [4][2],const xqr_box *,unsigned,
                           const uint8_t [91][240][4],double [4][2],xnp_refinement *);
extern int candidate_refine(const uint8_t *,const double [4][2],const xqr_box *,unsigned,
                            const uint8_t [91][240][4],double [4][2],xnp_refinement *);

typedef struct {int okay;double corners[4][2];xnp_refinement statistics;} outcome;

static uint64_t now(clockid_t kind)
{
    struct timespec t;
    if(clock_gettime(kind,&t))exit(4);
    return (uint64_t)t.tv_sec*UINT64_C(1000000000)+(uint64_t)t.tv_nsec;
}

static int equal(const outcome *a,const outcome *b)
{
    const char *kind=a->okay!=b->okay?"status":
        memcmp(a->corners,b->corners,sizeof(a->corners))?"corners":
        memcmp(&a->statistics,&b->statistics,sizeof(a->statistics))?"statistics":NULL;
    if(!kind)return 1;
    fprintf(stderr,"GEOMETRY_PAIR_MISMATCH kind=%s\n",kind);
    return 0;
}

int main(int argc,char **argv)
{
    int negative_corner=argc==3 && !strcmp(argv[2],"--negative-corner");
    int negative_stats=argc==3 && !strcmp(argv[2],"--negative-stats");
    if(argc!=2 && !negative_corner && !negative_stats)return 2;
    FILE *file=fopen(argv[1],"rb");
    if(!file)return 2;
    char magic[8];unsigned n;double coarse[4][2];xqr_box boxes[300];
    uint8_t (*rng)[240][4]=malloc(91u*240u*4u),*rgb=malloc(1280u*720u*3u);
    if(!rng || !rgb) {free(rgb);free(rng);fclose(file);return 2;}
    int valid=fread(magic,1,8,file)==8 && !memcmp(magic,"XQGEOM1",8) &&
        fread(&n,4,1,file)==1 && n<=300 && fread(coarse,8,8,file)==8 &&
        fread(boxes,24,n,file)==n && fread(rng,1,91u*240u*4u,file)==91u*240u*4u &&
        fread(rgb,1,1280u*720u*3u,file)==1280u*720u*3u && fgetc(file)==EOF && !ferror(file);
    fclose(file);
    if(!valid) {free(rgb);free(rng);return 2;}
    refine_fn variants[2]={baseline_refine,candidate_refine};
    outcome reference={0};
    reference.okay=variants[0](rgb,coarse,boxes,n,rng,reference.corners,&reference.statistics);
    outcome warm={0};
    warm.okay=variants[1](rgb,coarse,boxes,n,rng,warm.corners,&warm.statistics);
    if(!equal(&reference,&warm)) {free(rgb);free(rng);return 3;}
    printf("GEOMETRY_PAIR_REFERENCE okay=%d\n",reference.okay);
    for(unsigned repeat=0;repeat<4;repeat++)for(unsigned slot=0;slot<2;slot++) {
        unsigned variant=slot^(repeat&1u);
        outcome actual={0};
        uint64_t wall=now(CLOCK_MONOTONIC),cpu=now(CLOCK_PROCESS_CPUTIME_ID);
        actual.okay=variants[variant](rgb,coarse,boxes,n,rng,actual.corners,&actual.statistics);
        uint64_t elapsed_cpu=now(CLOCK_PROCESS_CPUTIME_ID)-cpu;
        uint64_t elapsed_wall=now(CLOCK_MONOTONIC)-wall;
        if(variant && negative_corner)((uint8_t *)actual.corners)[0]^=1;
        if(variant && negative_stats)((uint8_t *)&actual.statistics)[0]^=1;
        if(!equal(&reference,&actual)) {free(rgb);free(rng);return 3;}
        printf("GEOMETRY_PAIR_NS repeat=%u variant=%u cpu=%llu wall=%llu\n",repeat,variant,
            (unsigned long long)elapsed_cpu,(unsigned long long)elapsed_wall);
    }
    free(rgb);free(rng);
    puts("GEOMETRY_PAIR_FULL_CORNERS_STATISTICS_EQUAL_NOT_PRODUCT_OR_BOARD_ACCEPTANCE");
    return 0;
}
