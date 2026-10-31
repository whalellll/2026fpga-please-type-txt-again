#include "xq_native_post.h"
#include "crc32_fast.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* The training reference is immutable. Namespace its CLI entry point only. */
#define main xq_training_geometry_cli
#include "../../vision-model-20261020/geometry/geometry_reference.c"
#undef main
#define W 1280u
#define H 720u
#define PIXELS ((size_t)W*H)
static int order_double(const void *a,const void *b)
{double x=*(const double *)a,y=*(const double *)b;return x<y?-1:x>y;}
static double median(const double *a,unsigned n)
{double b[90];memcpy(b,a,n*sizeof(*b));qsort(b,n,sizeof(*b),order_double);return n%2?b[n/2]:(b[n/2]+b[n/2-1])/2;}
static int point(const double h[9],double x,double y,double out[2])
{double d=h[6]*x+h[7]*y+h[8];if(fabs(d)<1e-9)return 0;
 out[0]=(h[0]*x+h[1]*y+h[2])/d;out[1]=(h[3]*x+h[4]*y+h[5])/d;return isfinite(out[0]) && isfinite(out[1]);}
static int inverse(const double h[9],double a[9])
{
    double det=h[0]*(h[4]*h[8]-h[5]*h[7])-h[1]*(h[3]*h[8]-h[5]*h[6])+h[2]*(h[3]*h[7]-h[4]*h[6]);
    if(fabs(det)<1e-12)return 0;
    a[0]=(h[4]*h[8]-h[5]*h[7])/det;a[1]=(h[2]*h[7]-h[1]*h[8])/det;a[2]=(h[1]*h[5]-h[2]*h[4])/det;
    a[3]=(h[5]*h[6]-h[3]*h[8])/det;a[4]=(h[0]*h[8]-h[2]*h[6])/det;a[5]=(h[2]*h[3]-h[0]*h[5])/det;
    a[6]=(h[3]*h[7]-h[4]*h[6])/det;a[7]=(h[1]*h[6]-h[0]*h[7])/det;a[8]=(h[0]*h[4]-h[1]*h[3])/det;return 1;
}
static int round_even(double x)
{double mag=fabs(x);int n=(int)mag;if(mag-n>.5 || (mag-n==.5 && (n&1)))++n;return x<0?-n:n;}
int xnp_load_rng(const char *path,uint8_t data[91][240][4])
{
    FILE *f=fopen(path,"rb");char magic[8];uint32_t header[2];int okay=0;
    if(!f)return 0;
    if(fread(magic,1,8,f)==8 && !memcmp(magic,"XQRNG1\0\0",8) && fread(header,4,2,f)==2 && header[0]==91*240*4 &&
       fread(data,1,header[0],f)==header[0] && fgetc(f)==EOF && !ferror(f) &&
       (crc32_fast(0xffffffffu,data,header[0])^0xffffffffu)==header[1]) {
        okay=1;
        for(unsigned n=16;n<=90;n++)for(unsigned t=0;t<240;t++)for(unsigned i=0;i<4;i++)
            if(data[n][t][i]>=n)okay=0;
    }
    fclose(f);return okay;
}
int xnp_coarse(const double corners[4][2],double image_h[9],xqr_roi *roi)
{
    double h[9],x0=1280,y0=720,x1=0,y1=0;
    if(solve_h(&corners[0][0],0,h))return 0;
    memcpy(image_h,h,sizeof(h));
    image_h[0]*=8./9;image_h[3]*=8./9;image_h[6]*=8./9;
    image_h[1]*=9./8;image_h[4]*=9./8;image_h[7]*=9./8;
    for(unsigned i=0;i<4;i++) {
        if(corners[i][0]<x0)x0=corners[i][0];
        if(corners[i][0]>x1)x1=corners[i][0];
        if(corners[i][1]<y0)y0=corners[i][1];
        if(corners[i][1]>y1)y1=corners[i][1];
    }
    if(roi) {
        /* Values are supplied by the frozen adapter config in the caller;
         * this function returns the unexpanded quad's bounding rectangle. */
        *roi=(xqr_roi){(int)floor(x0),(int)floor(y0),(int)ceil(x1),(int)ceil(y1)};
    }
    return 1;
}
/* Same edge padding, vertical-then-horizontal cumulative sums as NumPy _sum.
 * Integral is temporary and bounded (no per-crossing full-image allocation). */
static int box_sum(const double *in,unsigned hy,unsigned hx,double *out)
{
    unsigned pw=W+2*hx,ph=H+2*hy,stride=pw+1;
    double *integral=calloc((size_t)(ph+1)*stride,sizeof(double));
    if(!integral)return 0;
    for(unsigned x=0;x<pw;x++) {
        int ix=(int)x-(int)hx;double v=0;if(ix<0)ix=0;if(ix>=1280)ix=1279;
        for(unsigned y=0;y<ph;y++) {
            int iy=(int)y-(int)hy;if(iy<0)iy=0;if(iy>=720)iy=719;
            v+=in[(size_t)iy*W+(unsigned)ix];integral[(size_t)(y+1)*stride+x+1]=v;
        }
    }
    for(unsigned y=0;y<=ph;y++) {
        double v=0;for(unsigned x=0;x<=pw;x++){v+=integral[(size_t)y*stride+x];integral[(size_t)y*stride+x]=v;}
    }
    for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++) {
        unsigned b=y+2*hy+1,r=x+2*hx+1;
        out[(size_t)y*W+x]=integral[(size_t)b*stride+r]-integral[(size_t)y*stride+r]-
            integral[(size_t)b*stride+x]+integral[(size_t)y*stride+x];
    }
    free(integral);return 1;
}
/* Normalized least squares via reorthogonalized QR. The delivered Python uses
 * LAPACK lstsq; rank-deficient samples reject here. This numerical seam is
 * explicitly tested and is not advertised as bit-exact LAPACK replacement. */
static int fit(const double grid[90][2],const double pixels[90][2],const uint8_t *keep,unsigned n,double h[9])
{
    double a[180][8],target[180],r[8][8]={{0}},qtb[8]={0},solution[8];
    double cx=0,cy=0,x0=INFINITY,y0=INFINITY,x1=-INFINITY,y1=-INFINITY,scale;
    unsigned count=0,rows=0,i,j,k;
    for(i=0;i<n;i++)if(keep[i]) {
        cx+=pixels[i][0];cy+=pixels[i][1];++count;
        if(pixels[i][0]<x0)x0=pixels[i][0];
        if(pixels[i][0]>x1)x1=pixels[i][0];
        if(pixels[i][1]<y0)y0=pixels[i][1];
        if(pixels[i][1]>y1)y1=pixels[i][1];
    }
    if(count<4)return 0;
    cx/=count;cy/=count;scale=fmax(x1-x0,y1-y0);if(scale<1e-12)return 0;
    for(i=0;i<n;i++)if(keep[i]) {
        double x=grid[i][0],y=grid[i][1],u=(pixels[i][0]-cx)/scale,v=(pixels[i][1]-cy)/scale;
        double row0[8]={x,y,1,0,0,0,-u*x,-u*y},row1[8]={0,0,0,x,y,1,-v*x,-v*y};
        memcpy(a[rows],row0,sizeof(row0));target[rows++]=u;
        memcpy(a[rows],row1,sizeof(row1));target[rows++]=v;
    }
    for(j=0;j<8;j++) {
        for(unsigned pass=0;pass<2;pass++)for(k=0;k<j;k++) {
            double dot=0;for(i=0;i<rows;i++)dot+=a[i][k]*a[i][j];
            r[k][j]+=dot;for(i=0;i<rows;i++)a[i][j]-=dot*a[i][k];
        }
        double norm=0;for(i=0;i<rows;i++)norm+=a[i][j]*a[i][j];norm=sqrt(norm);
        if(norm<1e-12)return 0;
        r[j][j]=norm;
        for(i=0;i<rows;i++){a[i][j]/=norm;qtb[j]+=a[i][j]*target[i];}
    }
    for(int col=7;col>=0;col--){double v=qtb[col];for(k=(unsigned)col+1;k<8;k++)v-=r[col][k]*solution[k];solution[col]=v/r[col][col];}
    h[0]=scale*solution[0]+cx*solution[6];h[1]=scale*solution[1]+cx*solution[7];h[2]=scale*solution[2]+cx;
    h[3]=scale*solution[3]+cy*solution[6];h[4]=scale*solution[4]+cy*solution[7];h[5]=scale*solution[5]+cy;
    h[6]=solution[6];h[7]=solution[7];h[8]=1;return 1;
}
int xnp_refine(const uint8_t *rgb,const double coarse[4][2],const xqr_box *boxes,unsigned nb,
               const uint8_t rng[91][240][4],double refined[4][2],xnp_refinement *stats)
{
    double seed[9],spacing,radius_value,*gray=NULL,*mask=NULL,*tmp=NULL,*score=NULL,*counts=NULL;
    double grid[90][2],pixels[90][2],errors[90],best_value=-INFINITY,h[9];
    uint8_t keep[90],best[90]={0};unsigned n=0,radius;int okay=0;
    if(stats)memset(stats,0,sizeof(*stats));
    if(!rgb || !rng || nb>300 || !xnp_coarse(coarse,seed,NULL))return 0;
    spacing=fmin(hypot(coarse[1][0]-coarse[0][0],coarse[1][1]-coarse[0][1])/9,
                 hypot(coarse[3][0]-coarse[0][0],coarse[3][1]-coarse[0][1])/8);
    radius_value=round_even(.4*spacing);radius=(unsigned)fmin(28,fmax(8,radius_value));
    gray=malloc(PIXELS*8);mask=malloc(PIXELS*8);tmp=malloc(PIXELS*8);score=malloc(PIXELS*8);counts=malloc(PIXELS*8);
    if(!gray || !mask || !tmp || !score || !counts)goto done;
    for(size_t i=0;i<PIXELS;i++){gray[i]=rgb[3*i]*.299+rgb[3*i+1]*.587+rgb[3*i+2]*.114;mask[i]=1;}
    for(unsigned i=0;i<nb;i++) {
        int x0=(int)fmax(0,floor(boxes[i].x0-6.)),x1=(int)fmin(W,ceil(boxes[i].x1+6.));
        int y0=(int)fmax(0,floor(boxes[i].y0-6.)),y1=(int)fmin(H,ceil(boxes[i].y1+6.));
        for(int y=y0;y<y1;y++)for(int x=x0;x<x1;x++)mask[(size_t)y*W+(unsigned)x]=0;
    }
    if(!box_sum(gray,15,15,tmp))goto done;
    for(size_t i=0;i<PIXELS;i++)gray[i]=fmin(1,fmax(0,(tmp[i]/961.-gray[i]-5)/60.))*mask[i];
    if(!box_sum(mask,1,13,counts) || !box_sum(gray,1,13,tmp))goto done;
    for(size_t i=0;i<PIXELS;i++)score[i]=counts[i]<48?-1:tmp[i]/fmax(counts[i],1);
    if(!box_sum(mask,13,1,counts) || !box_sum(gray,13,1,tmp))goto done;
    for(size_t i=0;i<PIXELS;i++)score[i]=score[i]<0 || counts[i]<48 || mask[i]<.5?0:fmin(score[i],tmp[i]/fmax(counts[i],1));
    for(unsigned gy=0;gy<9;gy++)for(unsigned gx=0;gx<10;gx++) {
        double p[2],value=-INFINITY;int bx=0,by=0;
        if(!point(seed,gx,gy,p))goto done;
        int ix=round_even(p[0]),iy=round_even(p[1]);
        int x0=ix-(int)radius,x1=ix+(int)radius+1,y0=iy-(int)radius,y1=iy+(int)radius+1;
        if(x0<0)x0=0;
        if(y0<0)y0=0;
        if(x1>1280)x1=1280;
        if(y1>720)y1=720;
        for(int y=y0;y<y1;y++)for(int x=x0;x<x1;x++) {
            double v=score[(size_t)y*W+(unsigned)x]-.0015*hypot(x-p[0],y-p[1]);
            if(v>value){value=v;bx=x;by=y;}
        }
        if(x0<x1 && y0<y1 && score[(size_t)by*W+(unsigned)bx]>=.26) {
            grid[n][0]=gx;grid[n][1]=gy;pixels[n][0]=bx;pixels[n++][1]=by;
        }
    }
    if(stats)stats->crossings=n;
    if(n<16)goto done;
    for(unsigned trial=0;trial<240;trial++) {
        double x0=10,y0=9,x1=0,y1=0,v;unsigned count=0;
        memset(keep,0,n);
        for(unsigned i=0;i<4;i++){unsigned id=rng[n][trial][i];keep[id]=1;
            if(grid[id][0]<x0)x0=grid[id][0];
            if(grid[id][0]>x1)x1=grid[id][0];
            if(grid[id][1]<y0)y0=grid[id][1];
            if(grid[id][1]>y1)y1=grid[id][1];}
        if(fmin(x1-x0,y1-y0)<3 || !fit(grid,pixels,keep,n,h))continue;
        for(unsigned i=0;i<n;i++) {
            double p[2];keep[i]=0;if(!point(h,grid[i][0],grid[i][1],p))continue;
            double e=hypot(p[0]-pixels[i][0],p[1]-pixels[i][1]);
            if(e<=3.5){keep[i]=1;errors[count++]=e;}
        }
        v=count?count-.03*median(errors,count):-1;
        if(v>best_value){best_value=v;memcpy(best,keep,n);}
    }
    if(!isfinite(best_value))goto done;
    memcpy(keep,best,n);
    for(unsigned trial=0;trial<5;trial++) {
        unsigned count=0;for(unsigned i=0;i<n;i++)count+=keep[i];
        if(count<16 || !fit(grid,pixels,keep,n,h))goto done;
        for(unsigned i=0;i<n;i++){double p[2];best[i]=point(h,grid[i][0],grid[i][1],p) && hypot(p[0]-pixels[i][0],p[1]-pixels[i][1])<=3.5;}
        if(!memcmp(best,keep,n))break;
        memcpy(keep,best,n);
    }
    {
        unsigned count=0;double x0=10,y0=9,x1=0,y1=0;
        for(unsigned i=0;i<n;i++)if(keep[i]){++count;
            if(grid[i][0]<x0)x0=grid[i][0];
            if(grid[i][0]>x1)x1=grid[i][0];
            if(grid[i][1]<y0)y0=grid[i][1];
            if(grid[i][1]>y1)y1=grid[i][1];}
        if(count<16 || fmin((x1-x0)/9,(y1-y0)/8)<.65 || !fit(grid,pixels,keep,n,h))goto done;
        if(stats)stats->inliers=count;
        double xy[4][2]={{0,0},{9,0},{9,8},{0,8}};
        for(unsigned i=0;i<4;i++)if(!point(h,xy[i][0],xy[i][1],refined[i]) ||
            hypot(refined[i][0]-coarse[i][0],refined[i][1]-coarse[i][1])/spacing>.5)goto done;
        if(!xnp_coarse(refined,seed,NULL))goto done;
        count=0;
        for(unsigned i=0;i<n;i++)if(keep[i]){double p[2];if(!point(h,grid[i][0],grid[i][1],p))goto done;errors[count++]=hypot(p[0]-pixels[i][0],p[1]-pixels[i][1]);}
        if(stats){stats->median_residual=median(errors,count);qsort(errors,count,sizeof(double),order_double);
            double at=(count-1)*.95;unsigned lo=(unsigned)at;stats->p95_residual=errors[lo]+(at-lo)*(errors[lo+1<count?lo+1:lo]-errors[lo]);}
    }
    okay=1;
done:
    free(gray);free(mask);free(tmp);free(score);free(counts);return okay;
}
int xnp_finish(const double corners[4][2],const xqr_box *boxes,unsigned nb,uint32_t frame,xqv_result *out,double gui[4][2])
{
    double image[9],inv[9],semantic[9];int edge=-1;unsigned generals[2]={0},votes=0;
    unsigned occupied[90]={0},counts[14]={0};char cells[90]={0};
    const char symbols[]="KABNRCPkabnrcp";const unsigned limits[7]={1,2,2,2,2,2,5};
    if(!out || nb>32 || !xnp_coarse(corners,image,NULL) || !inverse(image,inv))return 0;
    memset(out,0,sizeof(*out));
    for(unsigned i=0;i<nb;i++)if(boxes[i].class_id==0 || boxes[i].class_id==7) {
        double p[2];unsigned camp=boxes[i].class_id==7;int vote;
        if(++generals[camp]>1 || !point(inv,(boxes[i].x0+boxes[i].x1)/2.,(boxes[i].y0+boxes[i].y1)/2.,p) ||
           p[1]<2.5 || p[1]>5.5 || hypot(p[0]-round_even(p[0]),p[1]-round_even(p[1]))>.5)return 0;
        if(p[0]>=-.5 && p[0]<=2.5)vote=3;else if(p[0]>=6.5 && p[0]<=9.5)vote=1;else return 0;
        if(!camp)vote=vote==3?1:3;
        if(votes && edge!=vote)return 0;
        edge=vote;++votes;
    }
    if(!votes || solve_h(&corners[0][0],edge,semantic) || !inverse(semantic,inv))return 0;
    out->abi_version=1;out->frame_id=frame;out->confidence=1000;
    for(unsigned i=0;i<nb;i++) {
        double p[2];unsigned cid=boxes[i].class_id;
        if(cid>=14 || !point(inv,(boxes[i].x0+boxes[i].x1)/2.,(boxes[i].y0+boxes[i].y1)/2.,p))return 0;
        int f=round_even(p[0]),r=round_even(p[1]);
        if(f<0 || f>8 || r<0 || r>9 || .5-hypot(p[0]-f,p[1]-r)<.10 || occupied[r*9+f] || ++counts[cid]>limits[cid%7])return 0;
        occupied[r*9+f]=1;cells[r*9+f]=symbols[cid];
        unsigned conf=(unsigned)floor(boxes[i].score*1000.);
        if(conf<50 || conf>1000)return 0;
        out->pieces[i]=(xqv_piece){(uint8_t)cid,(uint8_t)f,(uint8_t)(9-r),(uint16_t)conf};
        if(conf<out->confidence)out->confidence=(uint16_t)conf;
    }
    if(counts[0]!=1 || counts[7]!=1)return 0;
    unsigned pos=0;
    for(unsigned r=0;r<10;r++) {
        unsigned empty=0;
        for(unsigned f=0;f<9;f++){char c=cells[r*9+f];if(!c){++empty;continue;}if(empty){out->fen[pos++]=(char)('0'+empty);empty=0;}out->fen[pos++]=c;}
        if(empty)out->fen[pos++]=(char)('0'+empty);
        if(r<9)out->fen[pos++]='/';
    }
    memcpy(out->fen+pos," w - - 0 1",11);out->piece_count=nb;
    const double q[4][2]={{0,9},{8,9},{8,0},{0,0}};
    for(unsigned i=0;i<4;i++)if(!point(semantic,q[i][0],q[i][1],gui[i]))return 0;
    return 1;
}
