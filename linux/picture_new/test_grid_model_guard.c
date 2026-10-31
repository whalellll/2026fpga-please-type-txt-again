#include "coach_geometry.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static const double quad[4][2]={{200,100},{920,100},{920,612},{200,612}};
static const double bad[4][2]={{200,100},{920,100},{920,612},{200,300}};
static const uint8_t rgb[1]={0},rng[91][240][4]={0};
static unsigned calls,cancel_calls,cancel_at,mode;
static const double (*seen[2])[2];
int __wrap_xnp_refine(const uint8_t *image,const double q[4][2],const xqr_box *boxes,
    unsigned n,const uint8_t random[91][240][4],double out[4][2],xnp_refinement *stats)
{
    assert(image==rgb && boxes && n==3 && random==rng && calls<2);
    seen[calls++]=q;
    memset(stats,0,sizeof(*stats));stats->inliers=40+calls;
    memcpy(out,mode==2 && calls==1?bad:quad,sizeof(quad));
    return mode==3?0:!(mode==1 && calls==1);
}
static int cancel(void *context)
{assert(context==&calls);return ++cancel_calls==cancel_at;}
static void check(unsigned test_mode,const double model[4][2],unsigned stop,
    unsigned expected_calls,int expected_okay,unsigned expected_used)
{
    xqcoach_identity id;assert(xqcoach_identity_init(&id,321,52,123));
    xqr_box boxes[3]={{188,344,212,368,.99f,0},{908,344,932,368,.98f,7},{188,88,212,112,.9f,4}};
    xqcoach_result mapped;assert(xqcoach_map_candidates(quad,boxes,3,&id,&mapped));
    assert(!xqcoach_map_candidates(bad,boxes,3,&id,&mapped));
    double output[4][2];memset(output,0x31,sizeof(output));xnp_refinement stats;
    unsigned used=99;calls=cancel_calls=0;cancel_at=stop;mode=test_mode;
    int okay=xqcoach_refine_model_first(rgb,bad,model,boxes,3,rng,&id,output,&stats,cancel,&calls,&used);
    assert(okay==expected_okay && used==expected_used && calls==expected_calls);
    if(calls){assert(seen[0]==(model==quad?quad:bad));if(calls==2)assert(seen[1]==bad);}
    if(okay){assert(!memcmp(output,quad,sizeof(output)));assert(stats.inliers==40+calls);}
    if(stop && !okay){for(unsigned i=0;i<sizeof(output);i++)assert(((unsigned char *)output)[i]==0x31);}
}
int main(void)
{
    check(0,quad,0,1,1,1); /* Strict raw/refined guards accept the model. */
    check(0,bad,0,1,1,0);  /* Raw mapping rejects without a second refinement. */
    check(0,NULL,0,1,1,0); /* No saved model: original grid path. */
    check(1,quad,0,2,1,0); /* Model refinement fails; retain grid refinement. */
    check(2,quad,0,2,1,0); /* Refinement succeeds but strict mapping rejects. */
    check(3,quad,0,2,0,0); /* Both fail: producer retains estimated-board path. */
    check(0,quad,1,0,0,0); /* Cancel before work. */
    check(0,quad,2,1,0,0); /* Cancel after trial: no result/fallback accepted. */
    puts("GRID_MODEL_GUARD_STRICT_MAPPING_REFINE_FALLBACK_CANCEL_PASS");return 0;
}
