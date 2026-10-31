#include "coach_geometry.h"
#include <string.h>
#if defined(XQ_GEOMETRY_CANCEL) && XQ_GEOMETRY_CANCEL
#include "geometry_cancel.h"
#define guard_refine(...) xqcoach_refine_cancellable(__VA_ARGS__,cancelled,context)
#else
#define guard_refine xnp_refine
#endif

int xqcoach_refine_model_first(const uint8_t *rgb,const double grid[4][2],
    const double model[4][2],const xqr_box *boxes,unsigned n,const uint8_t rng[91][240][4],
    const xqcoach_identity *id,double refined[4][2],xnp_refinement *stats,
    int (*cancelled)(void *),void *context,unsigned *used_model)
{
    if(used_model)*used_model=0;
    if(stats)memset(stats,0,sizeof(*stats));
    if(cancelled && cancelled(context))return 0;
    xqcoach_result checked;
    if(model && xqcoach_map_candidates(model,boxes,n,id,&checked)){
        double candidate[4][2];xnp_refinement candidate_stats={0};
        int okay=guard_refine(rgb,model,boxes,n,rng,candidate,&candidate_stats);
        if(cancelled && cancelled(context))return 0;
        if(okay && xqcoach_map_candidates(candidate,boxes,n,id,&checked)){
            memcpy(refined,candidate,sizeof(candidate));
            if(stats)*stats=candidate_stats;
            if(used_model)*used_model=1;
            return 1;
        }
    }
    if(cancelled && cancelled(context))return 0;
    return guard_refine(rgb,grid,boxes,n,rng,refined,stats);
}
#undef guard_refine
