#include "xq_native_geometry.h"
#include "xq_native_post.h"
#include "../geometry_fallback/c_ref/geometry_ref.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
static int valid_quad(const double q[4][2])
{
    GeomPt pts[4];double image[9];
    if(!q)return 0;
    for(unsigned i=0;i<4;i++) {
        if(!isfinite(q[i][0]) || !isfinite(q[i][1]) || q[i][0]<0 || q[i][0]>=1280 || q[i][1]<0 || q[i][1]>=720)return 0;
        pts[i]=(GeomPt){q[i][0],q[i][1]};
    }
    return geom_check_quad(pts,NULL,NULL,NULL,NULL)==GEOM_OK && xnp_coarse(q,image,NULL);
}
static void publish(xng_state *s,xng_geometry *out,const double q[4][2],xng_source source)
{
    memcpy(out->corners,q,sizeof(out->corners));out->token=s->token;out->frame=s->frame;
    out->crc=s->crc;out->source=source;s->cached=*out;s->has_cached=1;s->resolved=1;
}
int xng_begin(xng_state *s,uint64_t token,uint32_t frame,uint32_t crc)
{
    if(!s || !token || token<=s->token)return 0;
    s->token=token;s->frame=frame;s->crc=crc;s->active=1;s->resolved=0;return 1;
}
xng_event xng_resolve(xng_state *s,const double board[4][2],int board_valid,
                     const xqr_box *boxes,unsigned n,const double seed[4][2],xng_geometry *out)
{
    GeomPt centers[300],initial[4],q[4];GeomH h;
    const double bounds[4]={0,0,1279,719};int kept=0;double p95=0,corners[4][2];
    if(!out)return XNG_BAD_REQUEST;
    memset(out,0,sizeof(*out));
    if(!s || !s->active || s->resolved || n>300 || (n && !boxes))return XNG_BAD_REQUEST;
    if(board_valid && valid_quad(board)) {
        publish(s,out,board,XNG_BOARD_MODEL);s->failures=0;return XNG_OK;
    }
    s->resolved=1; /* A single frozen capture cannot count as several failures. */
    if(s->failures<3)++s->failures;
    if(s->failures<3)return XNG_RETAKE;
    for(unsigned i=0;i<n;i++) {
        if(!isfinite(boxes[i].x0) || !isfinite(boxes[i].y0) || !isfinite(boxes[i].x1) || !isfinite(boxes[i].y1) ||
           boxes[i].x0<0 || boxes[i].y0<0 || boxes[i].x1>1280 || boxes[i].y1>720 ||
           boxes[i].x1<=boxes[i].x0 || boxes[i].y1<=boxes[i].y0)return XNG_MANUAL_REQUIRED;
        centers[i]=(GeomPt){((double)boxes[i].x0+boxes[i].x1)/2,((double)boxes[i].y0+boxes[i].y1)/2};
    }
    if(seed && valid_quad(seed))for(unsigned i=0;i<4;i++)initial[i]=(GeomPt){seed[i][0],seed[i][1]};
    else seed=NULL;
    if(geom_piece_fit(centers,(int)n,seed?initial:NULL,bounds,q,&h,&kept,&p95)!=GEOM_OK ||
       kept<GEOM_MIN_KEPT || !isfinite(p95))return XNG_MANUAL_REQUIRED;
    for(unsigned i=0;i<4;i++){corners[i][0]=q[i].x;corners[i][1]=q[i].y;}
    if(!valid_quad(corners))return XNG_MANUAL_REQUIRED;
    out->kept=(unsigned)kept;out->p95=p95;publish(s,out,corners,XNG_PIECE_FIT);return XNG_OK;
}
xng_event xng_manual(xng_state *s,uint64_t token,uint32_t frame,uint32_t crc,const double q[4][2],xng_geometry *out)
{
    if(!out)return XNG_BAD_REQUEST;
    memset(out,0,sizeof(*out));
    if(!s || !s->active || token!=s->token || frame!=s->frame || crc!=s->crc)return XNG_BAD_REQUEST;
    if(!valid_quad(q))return XNG_MANUAL_REQUIRED;
    publish(s,out,q,XNG_MANUAL);return XNG_OK;
}
int xng_cached(const xng_state *s,xng_geometry *out)
{
    if(!out)return 0;
    memset(out,0,sizeof(*out));
    if(!s || !s->has_cached)return 0;
    *out=s->cached;out->source=XNG_CACHED;return 1;
}
int xng_read_manual(const char *path,uint64_t token,uint32_t frame,uint32_t crc,double q[4][2])
{
    char magic[32];unsigned long long t;unsigned f,c;int ch,okay=0;
    FILE *file=path?fopen(path,"r"):NULL;if(!file)return 0;
    if(fscanf(file,"%31s %llu %u %x",magic,&t,&f,&c)!=4 || strcmp(magic,"XQ_MANUAL_CORNERS_V1") ||
       t!=token || f!=frame || c!=crc)goto done;
    for(unsigned i=0;i<4;i++)if(fscanf(file,"%lf %lf",&q[i][0],&q[i][1])!=2)goto done;
    do{ch=fgetc(file);}while(ch==' ' || ch=='\n' || ch=='\r' || ch=='\t');
    okay=ch==EOF && !ferror(file) && valid_quad(q);
done:
    fclose(file);return okay;
}
const char *xng_source_name(xng_source source)
{
    switch(source){case XNG_BOARD_MODEL:return "board_model";case XNG_PIECE_FIT:return "piece_fit";
    case XNG_MANUAL:return "manual";case XNG_CACHED:return "cached";default:return "none";}
}
