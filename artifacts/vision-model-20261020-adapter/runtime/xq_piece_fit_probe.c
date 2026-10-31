/* Observe unchanged training C results without replacing its algorithms or
 * tolerance-based harness. Synthetic vectors only; no camera inputs here. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <inttypes.h>
#include "../geometry_fallback/c_ref/geometry_ref.h"
_Static_assert(sizeof(double)==8,"binary64 required");
static unsigned calls;
static void value(double x)
{
    uint64_t bits;memcpy(&bits,&x,8);printf(" %016" PRIx64,bits);
}
static void quad_h(const GeomPt q[4],const GeomH *h)
{
    for(unsigned i=0;i<4;i++){value(q[i].x);value(q[i].y);}
    for(unsigned i=0;i<3;i++)for(unsigned j=0;j<3;j++)value(h->m[i][j]);
}
static int observed_corners(const GeomPt q[4],int pairing,GeomH *h)
{
    int rc=geom_h_from_corners(q,pairing,h);
    printf("BINARY64 corners %u %d",++calls,rc);if(!rc)quad_h(q,h);puts("");return rc;
}
static int observed_fit(const GeomPt *c,int n,const GeomPt *seed,const double *bounds,
                        GeomPt q[4],GeomH *h,int *kept,double *p95)
{
    int rc=geom_piece_fit(c,n,seed,bounds,q,h,kept,p95);
    printf("BINARY64 piece_fit %u %d",++calls,rc);
    if(!rc){printf(" %d",*kept);value(*p95);quad_h(q,h);}puts("");return rc;
}
static int observed_points(const GeomH *h,GeomPt p[GEOM_N_POINTS])
{
    int rc=geom_grid_points(h,p);
    printf("BINARY64 points90 %u %d",++calls,rc);
    if(!rc)for(unsigned i=0;i<GEOM_N_POINTS;i++){value(p[i].x);value(p[i].y);}
    puts("");return rc;
}
#define geom_h_from_corners observed_corners
#define geom_piece_fit observed_fit
#define geom_grid_points observed_points
#define main training_harness_main
#include "../geometry_fallback/c_ref/test_harness.c"
#undef main
#undef geom_grid_points
#undef geom_piece_fit
#undef geom_h_from_corners
int main(int argc,char **argv)
{
    if(argc!=2)return 2;
    puts("XQ_PIECE_FIT_REFERENCE_PROBE_V1");
    return training_harness_main(argc,argv);
}
