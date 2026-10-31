#include "board_grid_recovery.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

#ifndef XQ_GRID_PLAN_FAST
#define XQ_GRID_PLAN_FAST 0
#endif
#if XQ_GRID_PLAN_FAST != 0 && XQ_GRID_PLAN_FAST != 1
#error XQ_GRID_PLAN_FAST_must_be_zero_or_one
#endif
#ifndef XQ_GRID_DOT_CACHE
#define XQ_GRID_DOT_CACHE 0
#endif
#if XQ_GRID_DOT_CACHE != 0 && XQ_GRID_DOT_CACHE != 1
#error XQ_GRID_DOT_CACHE_must_be_zero_or_one
#endif

/* Candidate only. Integer image/Hough work; small floating line/lattice fits.
 * Nine/ten grid lines are geometry, never an assumed initial piece position.
 * Up to two occluded outer lines may be extrapolated from internal repeats.
 * Both line families must support the SAME three original model corners. */
enum { W=1280,H=720,S=4,DW=320,DH=180,R=370,NR=741,NA=180,
       MAX_EDGES=DW*DH,MAX_LINES=40,KEEP=16,NSETS=64 };
typedef struct {int16_t x,y;uint16_t weight;uint8_t angle,pad;} edge;
typedef struct {double d,rho,nx,ny,fit_rho,log_votes;unsigned votes;int angle;} line;
typedef struct {double score,step,left_shift,right_shift;unsigned support,matched;int first,last;} lattice;
typedef struct {line lines[MAX_LINES];int count,angle;double nx,ny;lattice best[4][KEEP];unsigned counts[4];} family;
typedef struct {
    uint8_t gray[DW*DH];edge edges[MAX_EDGES];unsigned nedges;
    uint32_t accumulator[NA*NR];int32_t cosine[NA],sine[NA];uint8_t atan_table[257];
    double q[4][2],center[2];int32_t center_q16[2];
    family families[2];int (*cancelled)(void *);void *context;
} state;
static int stopped(state *s){return s->cancelled && s->cancelled(s->context);}
static unsigned popcount4(unsigned x)
{return (x&1u)+((x>>1)&1u)+((x>>2)&1u)+((x>>3)&1u);}
static int angle_distance(int a,int b)
{int d=abs(a-b);return d<180-d?d:180-d;}
static int round_q31(int64_t v)
{
    uint64_t a=v<0?(uint64_t)-v:(uint64_t)v,q=a>>31,r=a&UINT64_C(0x7fffffff);
    q+=r>UINT64_C(0x40000000) || (r==UINT64_C(0x40000000) && (q&1));
    return v<0?-(int)q:(int)q;
}
static int rho_at(const state *s,int x,int y,int a)
{
    int64_t xx=(int64_t)x*65536-s->center_q16[0],yy=(int64_t)y*65536-s->center_q16[1];
    return round_q31(xx*s->cosine[a]+yy*s->sine[a]);
}
static int edge_angle(const state *s,int x,int y)
{
    unsigned ax=(unsigned)abs(x),ay=(unsigned)abs(y);int a;
    if(!ax && !ay)return 0;
    if(ax>=ay)a=s->atan_table[(ay*256+ax/2)/ax];
    else a=90-s->atan_table[(ax*256+ay/2)/ay];
    if(x<0)a=180-a;
    if(y<0)a=-a;
    a%=180;return a<0?a+180:a;
}
static int make_edges(state *s,const uint8_t *rgb)
{
    for(unsigned y=0;y<DH;y++){
        if(stopped(s))return 0;
        for(unsigned x=0;x<DW;x++){
            unsigned sum=0;
            for(unsigned dy=0;dy<S;dy++)for(unsigned dx=0;dx<S;dx++){
                const uint8_t *p=rgb+((size_t)(y*S+dy)*W+x*S+dx)*3;
                sum+=(p[0]*77u+p[1]*150u+p[2]*29u+128u)>>8;
            }
            s->gray[y*DW+x]=(uint8_t)(sum/16);
        }
    }
    double x0=s->q[0][0],x1=x0,y0=s->q[0][1],y1=y0;
    for(unsigned i=1;i<4;i++){
        x0=fmin(x0,s->q[i][0]);x1=fmax(x1,s->q[i][0]);
        y0=fmin(y0,s->q[i][1]);y1=fmax(y1,s->q[i][1]);
    }
    int left=(int)floor(x0-16),right=(int)ceil(x1+16),top=(int)floor(y0-16),bottom=(int)ceil(y1+16);
    for(int y=1;y<DH-1;y++){
        if(stopped(s))return 0;
        if(y<top || y>bottom)continue;
        for(int x=1;x<DW-1;x++){
            if(x<left || x>right)continue;
            const uint8_t *p=s->gray+y*DW+x;
            int gx=p[-DW+1]+2*p[1]+p[DW+1]-p[-DW-1]-2*p[-1]-p[DW-1];
            int gy=p[DW-1]+2*p[DW]+p[DW+1]-p[-DW-1]-2*p[-DW]-p[-DW+1];
            unsigned m=(unsigned)(abs(gx)+abs(gy));if(m<24)continue;
            edge *e=s->edges+s->nedges++;e->x=(int16_t)x;e->y=(int16_t)y;
            e->weight=(uint16_t)(m<255?m:255);e->angle=(uint8_t)edge_angle(s,gx,gy);
        }
    }
    return 1;
}
static int hough(state *s,int normals[2])
{
    for(unsigned i=0;i<s->nedges;i++){
        if(!(i&255) && stopped(s))return 0;
        const edge *e=s->edges+i;
        for(int d=-2;d<=2;d++){
            int a=(e->angle+d+180)%180,r=rho_at(s,e->x,e->y,a)+R;
            if(r>=0 && r<NR)s->accumulator[a*NR+r]+=e->weight;
        }
    }
    uint32_t energy[NA];
    for(int a=0;a<NA;a++){
        uint32_t best[12]={0};
        for(int r=0;r<NR;r++){
            uint32_t v=s->accumulator[a*NR+r];if(v<=best[0])continue;
            int i=0;while(i<11 && v>best[i+1]){best[i]=best[i+1];i++;}best[i]=v;
        }
        energy[a]=0;for(unsigned i=0;i<12;i++)energy[a]+=best[i];
    }
    normals[0]=0;for(int a=1;a<NA;a++)if(energy[a]>energy[normals[0]])normals[0]=a;
    normals[1]=-1;
    for(int a=0;a<NA;a++)if(angle_distance(a,normals[0])>=55 &&
        (normals[1]<0 || energy[a]>energy[normals[1]]))normals[1]=a;
    return 1;
}
static int line_order(const void *a,const void *b)
{double d=((const line *)a)->d-((const line *)b)->d;return d<0?-1:d>0;}
static void fit_line(state *s,line *l)
{
    int64_t sw=0,sx=0,sy=0,sxx=0,sxy=0,syy=0;unsigned count=0;
    int64_t rho_q15=(int64_t)llround(l->rho*32768);
    for(unsigned i=0;i<s->nedges;i++){
        const edge *e=s->edges+i;
        int64_t d=(int64_t)e->x*s->cosine[l->angle]+(int64_t)e->y*s->sine[l->angle]-rho_q15;
        if(d<=-49152 || d>=49152 || angle_distance(e->angle,l->angle)>=7)continue;
        int64_t w=e->weight,x=e->x,y=e->y;
        sw+=w;sx+=w*x;sy+=w*y;sxx+=w*x*x;sxy+=w*x*y;syy+=w*y*y;count++;
    }
    l->nx=s->cosine[l->angle]/32768.;l->ny=s->sine[l->angle]/32768.;l->fit_rho=l->rho;
    if(count<=12 || !sw)return;
    double cx=(double)sx/sw,cy=(double)sy/sw;
    double a=(double)sxx/sw-cx*cx,b=(double)sxy/sw-cx*cy,c=(double)syy/sw-cy*cy;
    double theta=.5*atan2(2*b,a-c),nx=-sin(theta),ny=cos(theta),dot=nx*l->nx+ny*l->ny;
    if(fabs(dot)<=.99)return;
    if(dot<0){nx=-nx;ny=-ny;}
    l->nx=nx;l->ny=ny;l->fit_rho=nx*cx+ny*cy;
}
static int make_family(state *s,family *f,int angle)
{
    uint32_t hist[NR]={0},smooth[NR];f->angle=angle;
    f->nx=s->cosine[angle]/32768.;f->ny=s->sine[angle]/32768.;
    for(unsigned i=0;i<s->nedges;i++){
        const edge *e=s->edges+i;if(angle_distance(e->angle,angle)>=12)continue;
        int r=rho_at(s,e->x,e->y,angle)+R;if(r>=0 && r<NR)hist[r]+=e->weight;
    }
    for(int r=0;r<NR;r++)smooth[r]=2*hist[r]+(r?hist[r-1]:0)+(r+1<NR?hist[r+1]:0);
    for(int i=0;i<MAX_LINES;i++){
        int best=0;for(int r=1;r<NR;r++)if(smooth[r]>smooth[best])best=r;
        if(!smooth[best])break;
        line *l=f->lines+f->count++;l->d=best-R;l->angle=angle;l->votes=smooth[best];
        l->log_votes=log1p(l->votes);l->rho=l->d+s->center[0]*f->nx+s->center[1]*f->ny;
        for(int r=best-3;r<=best+3;r++)if(r>=0 && r<NR)smooth[r]=0;
    }
    qsort(f->lines,(size_t)f->count,sizeof(line),line_order);
    for(int i=0;i<f->count;i++){if(stopped(s))return 0;fit_line(s,f->lines+i);}
    return 1;
}
static void boundary(const family *f,const lattice *l,int end,double n[2],double *rho)
{
    const line *p=f->lines+(end?l->last:l->first);
    double delta=end?l->right_shift:l->left_shift;
    n[0]=p->nx;n[1]=p->ny;
    /* A PCA normal can have either sign. Translate along the family normal,
     * not by adding an unsigned distance to a signed line constant. */
    *rho=p->fit_rho+delta*(p->nx*f->nx+p->ny*f->ny);
}
static void keep_lattice(family *f,const lattice *l)
{
    for(unsigned excluded=0;excluded<4;excluded++){
        unsigned mask=15u^(1u<<excluded),count=f->counts[excluded];
        if((l->support&mask)!=mask)continue;
        if(count==KEEP && l->score<=f->best[excluded][KEEP-1].score)continue;
        if(count<KEEP)f->counts[excluded]=++count;
        unsigned at=count-1;
        while(at && l->score>f->best[excluded][at-1].score){
            f->best[excluded][at]=f->best[excluded][at-1];at--;
        }
        f->best[excluded][at]=*l;
    }
}
static int find_lattices(state *s,family *f,unsigned count)
{
    memset(f->counts,0,sizeof(f->counts));
#if XQ_GRID_DOT_CACHE
    /* These normals and model corners stay fixed for this family. Store the
     * same binary64 multiply/add results once; shifts, matching, scores and
     * strict tie traversal below keep their original operation order. */
    double projected[4],line_projected[MAX_LINES][4];
    for(unsigned c=0;c<4;c++){
        projected[c]=s->q[c][0]*f->nx+s->q[c][1]*f->ny;
        for(int i=0;i<f->count;i++)
            line_projected[i][c]=s->q[c][0]*f->lines[i].nx+s->q[c][1]*f->lines[i].ny;
    }
#endif
    for(int i=0;i<f->count;i++)for(int j=i+1;j<f->count;j++){
        if(stopped(s))return 0;
        for(unsigned left=0;left<=1;left++)for(unsigned right=0;right<=1;right++){
            lattice l={0};l.first=i;l.last=j;
            l.step=(f->lines[j].d-f->lines[i].d)/(count-1-left-right);
            if(l.step<4)continue;
            l.left_shift=-(double)left*l.step;l.right_shift=right*l.step;
#if XQ_GRID_PLAN_FAST
            /* This is the unchanged final anchor rejection, moved ahead of
             * matching. It does not select a lattice or change its score. */
            int anchored=1;
            for(unsigned end=0;end<2;end++){
                const line *p=f->lines+(end?j:i);
                double rho=p->rho+(end?l.right_shift:l.left_shift);
                double error=INFINITY;
                for(unsigned c=0;c<4;c++){
#if XQ_GRID_DOT_CACHE
                    double distance=projected[c]-rho;
#else
                    double distance=s->q[c][0]*f->nx+s->q[c][1]*f->ny-rho;
#endif
                    error=fmin(error,fabs(distance));
                }
                if(error>.6*l.step)anchored=0;
            }
            if(!anchored)continue;
#endif
            double start=f->lines[i].d+l.left_shift,error_sum=0,logs=0;
            unsigned unique=0;uint8_t seen[MAX_LINES]={0};int nearest=0;
            for(unsigned k=0;k<count;k++){
                double target=start+k*l.step;
                while(nearest+1<f->count && fabs(f->lines[nearest+1].d-target)<fabs(f->lines[nearest].d-target))nearest++;
                double e=fabs(f->lines[nearest].d-target)/l.step;
                error_sum+=fmin(e,1);
                if(e<.22){l.matched++;logs+=f->lines[nearest].log_votes;
                    if(!seen[nearest]){seen[nearest]=1;unique++;}}
#if XQ_GRID_PLAN_FAST
                unsigned remaining=count-1-k;
                if(l.matched+remaining<count-2 || unique+remaining<count-2)break;
#endif
            }
            if(l.matched<count-2 || unique<count-2)continue;
#if !XQ_GRID_PLAN_FAST
            int anchored=1;
            for(unsigned end=0;end<2;end++){
                const line *p=f->lines+(end?j:i);
                double rho=p->rho+(end?l.right_shift:l.left_shift);
                double error=INFINITY;
                for(unsigned c=0;c<4;c++){
#if XQ_GRID_DOT_CACHE
                    double distance=projected[c]-rho;
#else
                    double distance=s->q[c][0]*f->nx+s->q[c][1]*f->ny-rho;
#endif
                    error=fmin(error,fabs(distance));
                }
                if(error>.6*l.step)anchored=0;
            }
            if(!anchored)continue;
#endif
            double n0[2],n1[2],r0,r1;boundary(f,&l,0,n0,&r0);boundary(f,&l,1,n1,&r1);
            for(unsigned c=0;c<4;c++){
#if XQ_GRID_DOT_CACHE
                double a=fabs(line_projected[i][c]-r0);
                double b=fabs(line_projected[j][c]-r1);
#else
                double a=fabs(s->q[c][0]*n0[0]+s->q[c][1]*n0[1]-r0);
                double b=fabs(s->q[c][0]*n1[0]+s->q[c][1]*n1[1]-r1);
#endif
                if(fmin(a,b)<=.5*l.step)l.support|=1u<<c;
            }
            if(popcount4(l.support)<3)continue;
            l.score=l.matched*100.+logs-30*error_sum;keep_lattice(f,&l);
        }
    }
    return 1;
}
static int intersection(const double a[2],double ra,const double b[2],double rb,double p[2])
{
    double d=a[0]*b[1]-a[1]*b[0];if(fabs(d)<1e-6)return 0;
    p[0]=(ra*b[1]-a[1]*rb)/d;p[1]=(a[0]*rb-ra*b[0])/d;
    return isfinite(p[0]) && isfinite(p[1]);
}
static void sort4(double a[4])
{
    for(unsigned i=1;i<4;i++){double v=a[i];unsigned k=i;
        while(k && v<a[k-1]){a[k]=a[k-1];k--;}a[k]=v;}
}
#if XQ_GRID_PLAN_FAST
/* Compare fields individually: struct padding is not an identity, and double
 * bit identity preserves signed zeros and every original score/tie decision. */
static int same_lattice(const lattice *a,const lattice *b)
{
    return !memcmp(&a->score,&b->score,sizeof(double)) &&
        !memcmp(&a->step,&b->step,sizeof(double)) &&
        !memcmp(&a->left_shift,&b->left_shift,sizeof(double)) &&
        !memcmp(&a->right_shift,&b->right_shift,sizeof(double)) &&
        a->support==b->support && a->matched==b->matched &&
        a->first==b->first && a->last==b->last;
}
static int seen_lattice(const lattice *p,const lattice *const seen[NSETS],unsigned count)
{
    for(unsigned i=0;i<count;i++)if(same_lattice(p,seen[i]))return 1;
    return 0;
}
#endif
static int combine(state *s,double *best_score,double result[4][2])
{
    family *a=s->families,*b=s->families+1;
#if XQ_GRID_PLAN_FAST
    const lattice *seen_a[NSETS],*unique_b[NSETS];unsigned na=0,nb=0;
    for(unsigned exb=0;exb<4;exb++)for(unsigned ib=0;ib<b->counts[exb];ib++){
        const lattice *lb=&b->best[exb][ib];
        if(!seen_lattice(lb,unique_b,nb))unique_b[nb++]=lb;
    }
#endif
    for(unsigned exa=0;exa<4;exa++)for(unsigned ia=0;ia<a->counts[exa];ia++){
        if(stopped(s))return 0;
        const lattice *la=&a->best[exa][ia];double an[2][2],ar[2];
#if XQ_GRID_PLAN_FAST
        /* Keep the first occurrence in the original traversal. Identical
         * later pairs cannot beat its strict > score, even on an exact tie.
         * The original outer cancellation checks remain in the same order. */
        if(seen_lattice(la,seen_a,na))continue;
        seen_a[na++]=la;
#endif
        boundary(a,la,0,an[0],ar);boundary(a,la,1,an[1],ar+1);
#if XQ_GRID_PLAN_FAST
        for(unsigned ib=0;ib<nb;ib++){
            const lattice *lb=unique_b[ib];
#else
        for(unsigned exb=0;exb<4;exb++)for(unsigned ib=0;ib<b->counts[exb];ib++){
            const lattice *lb=&b->best[exb][ib];
#endif
            if(popcount4(la->support&lb->support)<3)continue;
            double bn[2][2],br[2],p[4][2];boundary(b,lb,0,bn[0],br);boundary(b,lb,1,bn[1],br+1);
            if(!intersection(an[0],ar[0],bn[0],br[0],p[0]) ||
               !intersection(an[1],ar[1],bn[0],br[0],p[1]) ||
               !intersection(an[1],ar[1],bn[1],br[1],p[2]) ||
               !intersection(an[0],ar[0],bn[1],br[1],p[3]))continue;
            double spacing=fmin(la->step,lb->step),cost=INFINITY;unsigned order[4]={0};
            for(unsigned reverse=0;reverse<2;reverse++)for(unsigned shift=0;shift<4;shift++){
                double errors[4];unsigned permutation[4];
                for(unsigned k=0;k<4;k++){
                    unsigned t=(k+4-shift)%4;permutation[k]=reverse?3-t:t;
                    double dx=p[permutation[k]][0]-s->q[k][0],dy=p[permutation[k]][1]-s->q[k][1];
                    errors[k]=dx*dx+dy*dy;
                }
                sort4(errors);if(errors[2]>.25*spacing*spacing)continue;
                double v=sqrt(errors[0])+sqrt(errors[1])+sqrt(errors[2]);
                if(v<cost){cost=v;memcpy(order,permutation,sizeof(order));}
            }
            if(!isfinite(cost))continue;
            double score=la->score+lb->score-10*cost/spacing;
            if(score>*best_score){
                *best_score=score;
                for(unsigned k=0;k<4;k++)memcpy(result[k],p[order[k]],2*sizeof(double));
            }
        }
    }
    return 1;
}
int xqgrid_recover(const uint8_t *rgb,size_t bytes,const float original[8],float output[8],
                   int (*cancelled)(void *),void *context,xqgrid_stats *stats)
{
    float base[8];state *s=NULL;int okay=0;
    if(stats)memset(stats,0,sizeof(*stats));
    if(!output)return 0;
    if(!rgb || bytes!=(size_t)W*H*3 || !original)goto done;
    memcpy(base,original,sizeof(base));
    for(unsigned i=0;i<8;i++)if(!isfinite(base[i]) || base[i]<0 || base[i]>1)goto done;
    if(cancelled && cancelled(context)){if(stats)stats->cancelled=1;goto done;}
    double q[4][2],minimum=INFINITY;
    for(unsigned i=0;i<4;i++){q[i][0]=(double)base[2*i]*W-.5;q[i][1]=(double)base[2*i+1]*H-.5;}
    for(unsigned i=0;i<4;i++){
        unsigned j=(i+1)%4;double dx=q[i][0]-q[j][0],dy=q[i][1]-q[j][1];
        minimum=fmin(minimum,dx*dx+dy*dy);
    }
    double dx=q[0][0]+q[2][0]-q[1][0]-q[3][0],dy=q[0][1]+q[2][1]-q[1][1]-q[3][1];
    /* A whole-cell affine closure error is only an attempt trigger. It never
     * accepts geometry. Healthy/perspective inputs can remain unchanged. */
    if(minimum<=0 || dx*dx+dy*dy<=minimum/81){memcpy(output,base,sizeof(base));return 1;}
    if(stats)stats->attempted=1;
    s=calloc(1,sizeof(*s));if(!s)goto done;
    s->cancelled=cancelled;s->context=context;
    for(unsigned i=0;i<4;i++)for(unsigned j=0;j<2;j++){
        s->q[i][j]=(q[i][j]-1.5)/S;s->center[j]+=s->q[i][j]/4;
    }
    for(unsigned j=0;j<2;j++)s->center_q16[j]=(int32_t)llround(s->center[j]*65536);
    const double pi=3.14159265358979323846;
    for(unsigned a=0;a<NA;a++){
        s->cosine[a]=(int32_t)llround(cos(a*pi/180)*32768);
        s->sine[a]=(int32_t)llround(sin(a*pi/180)*32768);
    }
    for(unsigned i=0;i<=256;i++)s->atan_table[i]=(uint8_t)lround(atan(i/256.)*180/pi);
    int normals[2];
    if(!make_edges(s,rgb) || !hough(s,normals))goto done;
    if(stats){stats->edges=s->nedges;stats->normal0=(unsigned)normals[0];stats->normal1=(unsigned)normals[1];}
    if(!s->nedges){memcpy(output,base,sizeof(base));okay=1;goto done;}
    for(unsigned i=0;i<2;i++)if(!make_family(s,s->families+i,normals[i]))goto done;
    double score=-INFINITY,proposal[4][2]={{0}};
    for(unsigned assignment=0;assignment<2;assignment++){
        if(!find_lattices(s,s->families,assignment?10:9) ||
           !find_lattices(s,s->families+1,assignment?9:10) || !combine(s,&score,proposal))goto done;
    }
    memcpy(output,base,sizeof(base));okay=1;
    if(isfinite(score)){
        double errors[4],ranked[4];unsigned corner=0;
        for(unsigned i=0;i<4;i++){
            proposal[i][0]=proposal[i][0]*S+1.5;proposal[i][1]=proposal[i][1]*S+1.5;
            double ex=proposal[i][0]-q[i][0],ey=proposal[i][1]-q[i][1];errors[i]=ex*ex+ey*ey;
            ranked[i]=errors[i];if(errors[i]>errors[corner])corner=i;
        }
        sort4(ranked);
        double limit=minimum/(81*4);
        if(ranked[2]<=limit && ranked[3]>limit && proposal[corner][0]>=0 && proposal[corner][0]<W &&
           proposal[corner][1]>=0 && proposal[corner][1]<H){
            output[corner*2]=(float)((proposal[corner][0]+.5)/W);
            output[corner*2+1]=(float)((proposal[corner][1]+.5)/H);
            if(stats){stats->used=1;stats->corner=corner;stats->score=score;}
        }
    }
done:
    if(s && stopped(s)){okay=0;if(stats)stats->cancelled=1;}
    free(s);if(!okay)memset(output,0,8*sizeof(float));return okay;
}
