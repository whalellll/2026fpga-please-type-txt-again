#include "coach_geometry.h"
/* One translation unit intentionally reuses the original exact private
 * solve_h/inverse/point/round_even helpers; legacy xnp_finish remains intact. */
#if defined(XQ_GEOMETRY_FUSED) && XQ_GEOMETRY_FUSED
#include XQ_GEOMETRY_FUSED_SOURCE
#elif defined(XQ_GEOMETRY_CANCEL) && XQ_GEOMETRY_CANCEL
#include XQ_GEOMETRY_CANCEL_SOURCE
#elif (defined(XQ_GEOMETRY_ROW_LOCAL) && XQ_GEOMETRY_ROW_LOCAL) || \
    (defined(XQ_GEOMETRY_GRAY_TABLE) && XQ_GEOMETRY_GRAY_TABLE) || \
    (defined(XQ_GEOMETRY_FAST) && XQ_GEOMETRY_FAST)
#include "geometry_locality.c"
#else
#include "../../artifacts/vision-model-20261020-adapter/runtime/xq_native_post.c"
#endif

static int map_candidates(const double corners[4][2],const xqr_box *boxes,unsigned count,
                           const xqcoach_identity *identity,xqcoach_result *out,int estimated)
{
    double image[9],inv[9],semantic[9];int edge=-1;unsigned votes=0;
    xqcoach_result result={0};
    if(!out || !identity || !identity->token || count>XQCOACH_MAX_CANDIDATES || (count && !boxes) ||
       !corners || !xnp_coarse(corners,image,NULL) || !inverse(image,inv))return 0;
    for(unsigned i=0;i<count;i++){
        const xqr_box *b=&boxes[i];
        if(b->class_id>=14 || !isfinite(b->score) || b->score<.05f || b->score>1.f ||
           !isfinite(b->x0) || !isfinite(b->y0) || !isfinite(b->x1) || !isfinite(b->y1) ||
           b->x0<0 || b->y0<0 || b->x1>1280 || b->y1>720 || b->x1<=b->x0 || b->y1<=b->y0)return 0;
        if(b->class_id==0 || b->class_id==7){
            double p[2];unsigned camp=b->class_id==7;int vote;
            if(!point(inv,(b->x0+b->x1)/2.,(b->y0+b->y1)/2.,p) || p[1]<2.5 || p[1]>5.5 ||
               p[0]<-.5 || p[0]>9.5 || hypot(p[0]-round_even(p[0]),p[1]-round_even(p[1]))>.5){if(estimated)continue;return 0;}
            if(p[0]>=-.5 && p[0]<=2.5)vote=3;else if(p[0]>=6.5 && p[0]<=9.5)vote=1;else return 0;
            if(!camp)vote=vote==3?1:3;
            if(votes && edge!=vote)return 0;
            edge=vote;++votes;
        }
    }
    if(!votes || solve_h(&corners[0][0],edge,semantic) || !inverse(semantic,inv))return 0;
    result.identity=*identity;result.count=count;result.estimated=(unsigned)estimated;result.status=estimated?5:0;
    for(unsigned i=0;i<count;i++){
        double p[2];const xqr_box *b=&boxes[i];
        result.candidates[i]=(xqcoach_candidate){b->class_id,255,255,(uint16_t)floor((double)b->score*1000.),b->score,b->x0,b->y0,b->x1,b->y1};
        if(!point(inv,(b->x0+b->x1)/2.,(b->y0+b->y1)/2.,p) || p[0]<-.5 || p[0]>8.5 || p[1]<-.5 || p[1]>9.5){if(estimated)continue;return 0;}
        int f=round_even(p[0]),r=round_even(p[1]);
        /* This is exactly xnp_finish's .10 boundary-margin guard. No
         * duplicate-cell, 32-count or class-limit rejection is performed. */
        if(f<0 || f>8 || r<0 || r>9 || (!estimated && .5-hypot(p[0]-f,p[1]-r)<.10)){if(estimated)continue;return 0;}
        unsigned confidence=(unsigned)floor((double)b->score*1000.);
        if(confidence<50 || confidence>1000)return 0;
        result.candidates[i]=(xqcoach_candidate){(uint8_t)b->class_id,(uint8_t)f,(uint8_t)(9-r),(uint16_t)confidence,
                                               b->score,b->x0,b->y0,b->x1,b->y1};
    }
    const double q[4][2]={{0,9},{8,9},{8,0},{0,0}};
    for(unsigned i=0;i<4;i++)if(!point(semantic,q[i][0],q[i][1],result.corners[i]))return 0;
    *out=result;return 1;
}
int xqcoach_map_candidates(const double q[4][2],const xqr_box *b,unsigned n,const xqcoach_identity *id,xqcoach_result *o)
{return map_candidates(q,b,n,id,o,0);}
int xqcoach_estimate_candidates(const double q[4][2],const xqr_box *b,unsigned n,const xqcoach_identity *id,xqcoach_result *o)
{return map_candidates(q,b,n,id,o,1);}
