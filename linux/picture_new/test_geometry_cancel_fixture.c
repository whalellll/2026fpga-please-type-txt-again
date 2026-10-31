#define _POSIX_C_SOURCE 200809L
#include "coach_geometry.h"
#include "geometry_cancel.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned polls;
static int no_cancel(void *p){assert(p==&polls);polls++;return 0;}
int main(int argc,char **argv)
{
    assert(argc==3);FILE *f=fopen(argv[1],"rb");assert(f);
    char magic[8];unsigned n;double q[4][2],out[4][2]={{0}};
    xqr_box boxes[300];uint8_t (*rng)[240][4]=malloc(91*240*4),*rgb=malloc(1280*720*3);
    assert(rng && rgb && fread(magic,1,8,f)==8 && !memcmp(magic,"XQGEOM1",8));
    assert(fread(&n,4,1,f)==1 && n<=300 && fread(q,8,8,f)==8 && fread(boxes,24,n,f)==n);
    assert(fread(rng,1,91*240*4,f)==91*240*4 && fread(rgb,1,1280*720*3,f)==1280*720*3 && fgetc(f)==EOF && !fclose(f));
    xnp_refinement stats={0};int okay;
#if defined(XQ_GEOMETRY_CANCEL) && XQ_GEOMETRY_CANCEL
    okay=xqcoach_refine_cancellable(rgb,q,boxes,n,rng,out,&stats,no_cancel,&polls);
#else
    (void)no_cancel;okay=xnp_refine(rgb,q,boxes,n,rng,out,&stats);
#endif
    f=fopen(argv[2],"wbx");assert(f && fwrite(&okay,sizeof(okay),1,f)==1 && fwrite(out,sizeof(out),1,f)==1 && fwrite(&stats,sizeof(stats),1,f)==1 && !fclose(f));
    printf("GEOMETRY_CANCEL_FIXTURE result=%d crossings=%u inliers=%u probes=%u NOT_BOARD\n",okay,stats.crossings,stats.inliers,polls);
    free(rgb);free(rng);return 0;
}
