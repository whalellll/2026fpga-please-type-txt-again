/* Synthetic line-grid controls. No piece-layout prior or real image input. */
#include GEOMETRY_SOURCE
#include <assert.h>
static void dot(uint8_t *rgb,int x,int y,uint8_t value)
{
    for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++){
        int xx=x+dx,yy=y+dy;
        if(xx>=0 && yy>=0 && xx<1280 && yy<720)memset(rgb+((size_t)yy*1280+(unsigned)xx)*3,value,3);
    }
}
static void segment(uint8_t *rgb,const double a[2],const double b[2])
{
    unsigned steps=(unsigned)ceil(fmax(fabs(a[0]-b[0]),fabs(a[1]-b[1])));
    for(unsigned i=0;i<=steps;i++)dot(rgb,round_even(a[0]+(b[0]-a[0])*i/steps),
        round_even(a[1]+(b[1]-a[1])*i/steps),0);
}
int main(int argc,char **argv)
{
    assert(argc==3);uint8_t *rgb=malloc(1280u*720u*3u),(*rng)[240][4]=malloc(91u*240u*4u);
    assert(rgb && rng && xnp_load_rng(argv[1],rng));
    const double truth[4][2]={{150,100},{1050,125},{1040,620},{160,605}};
    double seed[9];assert(xnp_coarse(truth,seed,NULL));
    double spacing=fmin(hypot(truth[1][0]-truth[0][0],truth[1][1]-truth[0][1])/9,
        hypot(truth[3][0]-truth[0][0],truth[3][1]-truth[0][1])/8);
    const char *names[]={"clean","occlusion","one_corner_small","one_corner_large",
        "two_corners_same_bias","whole_quad_small_shift","outside_background","edge_erased"};
    for(unsigned test=0;test<8;test++){
        memset(rgb,255,1280u*720u*3u);double coarse[4][2];memcpy(coarse,truth,sizeof(coarse));
        for(unsigned x=0;x<10;x++){double a[2],b[2];assert(point(seed,x,0,a) && point(seed,x,8,b));segment(rgb,a,b);}
        for(unsigned y=0;y<9;y++){double a[2],b[2];assert(point(seed,0,y,a) && point(seed,9,y,b));segment(rgb,a,b);}
        xqr_box boxes[8];unsigned count=test==1?8:0;
        for(unsigned i=0;i<count;i++){
            double p[2];assert(point(seed,i+1,i%7+1,p));int x=round_even(p[0]),y=round_even(p[1]);
            boxes[i]=(xqr_box){x-14,y-14,x+15,y+15,.9f,4};
            for(int dy=-14;dy<=14;dy++)for(int dx=-14;dx<=14;dx++)dot(rgb,x+dx,y+dy,255);
        }
        if(test==2)coarse[1][0]+=.2*spacing;
        if(test==3)coarse[1][0]+=.8*spacing;
        if(test==4){coarse[1][0]+=.8*spacing;coarse[2][0]+=.8*spacing;}
        if(test==5)for(unsigned i=0;i<4;i++)coarse[i][0]+=.2*spacing;
        if(test==6){const double a[2]={20,20},b[2]={1250,35},c[2]={25,30},d[2]={35,700};segment(rgb,a,b);segment(rgb,c,d);}
        if(test==7)memset(rgb+(size_t)590*1280*3,255,(size_t)(720-590)*1280*3);
        double actual[4][2]={{0}};xnp_refinement stats={0};int okay=xnp_refine(rgb,coarse,boxes,count,rng,actual,&stats);
        double error=0;
        if(okay)for(unsigned i=0;i<4;i++)error=fmax(error,hypot(actual[i][0]-truth[i][0],actual[i][1]-truth[i][1])/spacing);
        printf("GEOMETRY_CORRESPONDENCE case=%s okay=%d crossings=%u inliers=%u truth_error_grid=%.9g\n",
            names[test],okay,stats.crossings,stats.inliers,error);
        if(test==0 || test==1 || test==6)assert(okay && error<.1);
        char path[2048];int written=snprintf(path,sizeof(path),"%s/%s.bin",argv[2],names[test]);
        assert(written>0 && (size_t)written<sizeof(path));FILE *f=fopen(path,"wbx");
        assert(f && fwrite("XQGEOM1",1,8,f)==8 && fwrite(&count,4,1,f)==1 && fwrite(coarse,8,8,f)==8 &&
            fwrite(boxes,24,count,f)==count && fwrite(rng,1,91u*240u*4u,f)==91u*240u*4u &&
            fwrite(rgb,1,1280u*720u*3u,f)==1280u*720u*3u && !fclose(f));
    }
    free(rgb);free(rng);puts("GEOMETRY_SYNTHETIC_CORRESPONDENCE_CONTROLS_COMPLETE_NOT_BOARD");return 0;
}
