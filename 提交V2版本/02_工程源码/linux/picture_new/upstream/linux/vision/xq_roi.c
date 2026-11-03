#include "xq_roi.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

int xqr_roi_valid(xqr_roi r)
{ return r.x0>=0 && r.y0>=0 && r.x1>r.x0 && r.y1>r.y0 && r.x1<=1280 && r.y1<=720; }
static unsigned round_ratio(unsigned value,unsigned numerator,unsigned denominator)
{
    unsigned q=value*numerator/denominator,r=value*numerator%denominator;
    return q+(2*r>denominator || (2*r==denominator && (q&1u)));
}
int xqr_letterbox_plan(xqr_roi r,unsigned size,xqr_letterbox *out)
{
    unsigned w,h,d;
    if (!out) return 0;
    memset(out,0,sizeof(*out));
    if(!xqr_roi_valid(r) || (size!=320 && size!=640))return 0;
    w=(unsigned)(r.x1-r.x0);h=(unsigned)(r.y1-r.y0);d=w>h?w:h;
    if(d<size)d=size;
    out->size=size;out->width=round_ratio(w,size,d);out->height=round_ratio(h,size,d);
    out->left=(size-out->width)/2;out->top=(size-out->height)/2;
    out->ratio=(double)size/d;out->pad_x=(size-out->width)/2.0;out->pad_y=(size-out->height)/2.0;
    out->roi=r;
    return out->width && out->height;
}
int xqr_rgb565(const xqv_frame *frame,uint8_t *rgb,size_t capacity)
{
    unsigned i;
    if(!frame || !frame->rgb565 || frame->bytes!=XQV_FRAME_BYTES || !rgb || capacity<1280u*720u*3u)return 0;
    for(i=0;i<1280u*720u;i++) {
        uint16_t p=(uint16_t)(frame->rgb565[i/2]>>(16*(i%2)));
        /* Bit replication is an explicit camera receiver rule, not a claim
         * that the delivered RGB888 photographs retain the same precision. */
        rgb[3*i]=(uint8_t)(((p>>11)<<3)|((p>>11)>>2));
        rgb[3*i+1]=(uint8_t)((((p>>5)&63)<<2)|(((p>>5)&63)>>4));
        rgb[3*i+2]=(uint8_t)(((p&31)<<3)|((p&31)>>2));
    }
    return 1;
}
static int floor_int(double x) { int v=(int)x;return v-(x<v); }
static int ceil_int(double x) { int v=(int)x;return v+(x>v); }
static unsigned coefficient(double v)
{
    unsigned q=(unsigned)v;
    double f=v-q;
    return q+(f>.5 || (f==.5 && (q&1u)));
}
typedef struct {int index;unsigned a,b;} resize_axis;
static resize_axis axis(unsigned position,unsigned src,unsigned dst,int clamp)
{
    /* OpenCV first converts the half-pixel coordinate to float. */
    float coordinate=(float)(((position+.5)*(double)src/dst)-.5);
    resize_axis p;
    double frac;
    p.index=floor_int(coordinate);frac=coordinate-p.index;
    if(clamp && p.index<0){p.index=0;frac=0;}
    if(clamp && p.index>=(int)src-1){p.index=(int)src-1;frac=0;}
    p.a=coefficient((float)(1-frac)*2048);p.b=coefficient((float)frac*2048);
    return p;
}
static uint8_t pixel(const uint8_t *rgb,unsigned w,unsigned h,size_t stride,int x,int y,unsigned channel)
{
    return x<0 || y<0 || x>=(int)w || y>=(int)h ? 114 : rgb[(size_t)y*stride+3u*(unsigned)x+channel];
}
int xqr_resize_rgb(const uint8_t *rgb,unsigned w,unsigned h,size_t stride,
                   int x0,int y0,int x1,int y1,unsigned dw,unsigned dh,uint8_t *out,size_t capacity)
{
    resize_axis xs[640];
    unsigned x,y,c,sw,sh;
    if(!rgb || !out || !w || !h || w>1280 || h>720 || stride<3u*w ||
       !dw || !dh || dw>640 || dh>640 || capacity<(size_t)dw*dh*3 ||
       x0<-2048 || y0<-2048 || x1>3328 || y1>2768 || x1<=x0 || y1<=y0)return 0;
    sw=(unsigned)(x1-x0);sh=(unsigned)(y1-y0);
    for(x=0;x<dw;x++)xs[x]=axis(x,sw,dw,1);
    for(y=0;y<dh;y++) {
        resize_axis ay=axis(y,sh,dh,0);
        int first=ay.index<0?0:ay.index,second=ay.index+1;
        int sy,sy1;
        if(first>=(int)sh)first=(int)sh-1;
        if(second<0)second=0;
        if(second>=(int)sh)second=(int)sh-1;
        sy=y0+first;sy1=y0+second;
        for(x=0;x<dw;x++) {
            int sx=x0+xs[x].index,sx1=x0+(xs[x].index+1<(int)sw?xs[x].index+1:xs[x].index);
            for(c=0;c<3;c++) {
                unsigned a=pixel(rgb,w,h,stride,sx,sy,c)*xs[x].a+pixel(rgb,w,h,stride,sx1,sy,c)*xs[x].b;
                unsigned b=pixel(rgb,w,h,stride,sx,sy1,c)*xs[x].a+pixel(rgb,w,h,stride,sx1,sy1,c)*xs[x].b;
                /* Scalar INTER_LINEAR vertical stage from OpenCV 4.10's
                 * uchar path: preserve its intermediate truncation. */
                out[(size_t)c*dw*dh+(size_t)y*dw+x]=(uint8_t)((((ay.a*(a>>4))>>16)+((ay.b*(b>>4))>>16)+2)>>2);
            }
        }
    }
    return 1;
}
int xqr_detector_input(const uint8_t *rgb,xqr_roi r,unsigned size,uint8_t *out,size_t capacity,xqr_letterbox *plan)
{
    xqr_letterbox p;
    uint8_t *scaled;
    unsigned c,y;
    if(!out || capacity<(size_t)size*size*3 || !xqr_letterbox_plan(r,size,&p))return 0;
    scaled=malloc((size_t)p.width*p.height*3);
    if(!scaled)return 0;
    if(!xqr_resize_rgb(rgb,1280,720,1280*3,r.x0,r.y0,r.x1,r.y1,p.width,p.height,scaled,(size_t)p.width*p.height*3)){
        free(scaled);return 0;
    }
    memset(out,114,(size_t)size*size*3);
    for(c=0;c<3;c++)for(y=0;y<p.height;y++)
        memcpy(out+(size_t)c*size*size+(y+p.top)*size+p.left,scaled+(size_t)c*p.width*p.height+y*p.width,p.width);
    free(scaled);if(plan)*plan=p;return 1;
}
static int box_valid(const xqr_box *b)
{
    return b && isfinite(b->x0) && isfinite(b->y0) && isfinite(b->x1) && isfinite(b->y1) &&
        isfinite(b->score) && b->x1>b->x0 && b->y1>b->y0 && b->score>=0 && b->score<=1 && b->class_id<14;
}
int xqr_piece_crop(const uint8_t *rgb,const xqr_box *box,uint8_t *out,size_t capacity)
{
    double side,cx,cy;
    if(!box_valid(box) || box->x0<0 || box->y0<0 || box->x1>1280 || box->y1>720)return 0;
    side=fmax((double)box->x1-box->x0,(double)box->y1-box->y0)*1.25;
    cx=((double)box->x0+box->x1)/2;cy=((double)box->y0+box->y1)/2;
    return xqr_resize_rgb(rgb,1280,720,1280*3,floor_int(cx-side/2),floor_int(cy-side/2),
        ceil_int(cx+side/2),ceil_int(cy+side/2),32,32,out,capacity);
}
int xqr_box_original(const xqr_letterbox *p,xqr_box *b)
{
    float values[4];
    unsigned i;
    if(!p || !b || !box_valid(b) || p->ratio<=0 || !xqr_roi_valid(p->roi))return 0;
    values[0]=b->x0;values[1]=b->y0;values[2]=b->x1;values[3]=b->y1;
    for(i=0;i<4;i++) {
        double v=(values[i]-(i%2?p->pad_y:p->pad_x))/p->ratio;
        double limit=i%2?p->roi.y1-p->roi.y0:p->roi.x1-p->roi.x0;
        if(v<0)v=0;
        if(v>limit)v=limit;
        values[i]=(float)(v+(i%2?p->roi.y0:p->roi.x0));
    }
    b->x0=values[0];b->y0=values[1];b->x1=values[2];b->y1=values[3];
    return box_valid(b);
}
static float overlap(const xqr_box *a,const xqr_box *b)
{
    double w=fmin(a->x1,b->x1)-fmax(a->x0,b->x0),h=fmin(a->y1,b->y1)-fmax(a->y0,b->y0),inter;
    if(w<=0 || h<=0)return 0;
    inter=w*h;
    return (float)(inter/(((double)a->x1-a->x0)*(a->y1-a->y0)+((double)b->x1-b->x0)*(b->y1-b->y0)-inter));
}
int xqr_nms(const xqr_box *in,unsigned n,float threshold,float iou,unsigned maximum,
            xqr_box *work,size_t capacity,xqr_box *out,unsigned *count)
{
    unsigned i,j,remaining=0;
    if(count)*count=0;
    if(!count || (!in && n) || !work || !out || n>352800 || capacity<n || !maximum || maximum>300 ||
       !isfinite(threshold) || !isfinite(iou) || threshold<0 || threshold>1 || iou<0 || iou>1)return 0;
    if(work==in || work==out)return 0;
    for(i=0;i<n;i++) {
        if(!box_valid(in+i))return 0;
        if(in[i].score>threshold)work[remaining++]=in[i];
    }
    /* Selection of at most 300 winners is O(max_det*N), bounded and stable;
     * no global qsort comparator context or cross-thread mutable state. */
    while(remaining && *count<maximum) {
        unsigned best=0;
        xqr_box chosen;
        for(i=1;i<remaining;i++)if(work[i].score>work[best].score)best=i;
        chosen=work[best];out[(*count)++]=chosen;
        for(i=0,j=0;i<remaining;i++)if(i!=best &&
            (work[i].class_id!=chosen.class_id || overlap(work+i,&chosen)<=iou))work[j++]=work[i];
        remaining=j;
    }
    return 1;
}
int xqr_fuse(const xqr_box *in,const float *prob,unsigned n,xqr_box *out,unsigned *count)
{
    unsigned i,c,used=0;
    if(count)*count=0;
    if(!count || (!in && n) || (!prob && n) || !out || n>300)return 0;
    for(i=0;i<n;i++) {
        unsigned best=0;
        double sum=0;
        if(!box_valid(in+i))return 0;
        for(c=0;c<15;c++) {
            float p=prob[15*i+c];
            if(!isfinite(p) || p<0 || p>1)return 0;
            sum+=p;if(p>prob[15*i+best])best=c;
        }
        if(fabs(sum-1)>.001)return 0;
        if(best<14) {
            out[used]=in[i];out[used].class_id=best;
            out[used].score=in[i].score*prob[15*i+best];++used;
        }
    }
    *count=used;return 1;
}
int xqr_manual_init(xqr_manual *m,xqr_roi r,const double c[4][2],uint64_t view)
{
    unsigned i;
    if(!m)return 0;
    memset(m,0,sizeof(*m));
    if(!c || !view || !xqr_roi_valid(r))return 0;
    for(i=0;i<4;i++)if(!isfinite(c[i][0]) || !isfinite(c[i][1]) || c[i][0]<r.x0 || c[i][0]>=r.x1 ||
        c[i][1]<r.y0 || c[i][1]>=r.y1)return 0;
    if(!xqg_corners(&m->grid,c))return 0;
    memcpy(m->corners,c,sizeof(m->corners));m->roi=r;m->view_id=view;return 1;
}
int xqr_map(const xqr_manual *m,uint64_t view,const xqr_box *boxes,unsigned n,
            uint32_t frame,float threshold,xqv_result *out,unsigned *outside)
{
    xqg_detection detections[32];
    unsigned i,j,used=0;
    if(out)memset(out,0,sizeof(*out));
    if(outside)*outside=0;
    if(!m || !m->grid.valid || view!=m->view_id || !view || !out || (!boxes && n) || n>300 ||
       !isfinite(threshold) || threshold<0 || threshold>1)return 0;
    for(i=0;i<n;i++) {
        double x,y;
        if(!box_valid(boxes+i) || boxes[i].x0<0 || boxes[i].y0<0 || boxes[i].x1>1280 || boxes[i].y1>720)return 0;
        if(boxes[i].score<threshold)continue;
        x=((double)boxes[i].x0+boxes[i].x1)/2;y=((double)boxes[i].y0+boxes[i].y1)/2;
        for(j=0;j<4;j++) {
            unsigned k=(j+1)%4;
            double cross=(m->corners[k][0]-m->corners[j][0])*(y-m->corners[j][1])-
                         (m->corners[k][1]-m->corners[j][1])*(x-m->corners[j][0]);
            if(cross>1e-7)break;
        }
        if(j!=4){if(outside)++*outside;continue;}
        if(used==32)return 0;
        detections[used]=(xqg_detection){x,y,(uint16_t)boxes[i].x0,(uint16_t)boxes[i].y0,
            (uint16_t)boxes[i].x1,(uint16_t)boxes[i].y1,(uint16_t)(boxes[i].score*1000),
            (uint8_t)boxes[i].class_id};++used;
    }
    if(!xqg_map(&m->grid,detections,used,frame,out)){memset(out,0,sizeof(*out));return 0;}
    return 1;
}
int xqr_rectify(const xqr_manual *m,const xqv_frame *f,uint32_t *out,unsigned w,unsigned h,size_t capacity)
{
    unsigned x,y;
    if(!m || !m->grid.valid || !f || !f->rgb565 || f->bytes!=XQV_FRAME_BYTES || !out ||
       w<2 || h<2 || w>640 || h>720 || (w&1) || capacity<(size_t)w*h*2)return 0;
    for(y=0;y<h;y++)for(x=0;x<w;x+=2) {
        unsigned lane;uint32_t word=0;
        for(lane=0;lane<2;lane++) {
            double sx,sy;unsigned at,ix,iy;
            if(!xqg_project(&m->grid,8.0*(x+lane)/(w-1),9.0*(h-1-y)/(h-1),&sx,&sy))return 0;
            ix=(unsigned)(sx+.5);iy=(unsigned)(sy+.5);
            if(ix>1279)ix=1279;
            if(iy>719)iy=719;
            at=iy*1280+ix;
            if(at>=1280u*720u)return 0;
            word|=((f->rgb565[at/2]>>(16*(at%2)))&65535u)<<(16*lane);
        }
        out[(y*w+x)/2]=word;
    }
    return 1;
}
