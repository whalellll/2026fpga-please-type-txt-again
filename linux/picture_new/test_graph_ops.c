#include "graph_ops.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void)
{
    int16_t a[]={100,-100},b[]={200,-200},out[64];xqg_s16_view result;
    xqg_s16_view in[2]={{a,2,2,1,1,1,-1},{b,2,2,1,1,1,0}};
    const int16_t concat[]={50,200,-50,-200};
    assert(xqg_op_run(7,in,2,out,64,NULL,&result));
    assert(result.exponent==0 && result.batch==2 && result.channels==2 && !memcmp(out,concat,sizeof(concat)));
    in[0].exponent=-120;in[1].exponent=120;
    assert(xqg_op_run(8,in,2,out,64,NULL,&result));
    assert(result.exponent==120 && out[0]==200 && out[1]==-200);
    int16_t ties[]={1,3,-1,-3};int16_t zero[4]={0};
    in[0]=(xqg_s16_view){ties,4,1,1,1,4,-1};in[1]=(xqg_s16_view){zero,4,1,1,1,4,0};
    const int16_t rounded[]={0,2,0,-2};
    assert(xqg_op_run(8,in,2,out,64,NULL,&result) && !memcmp(out,rounded,sizeof(rounded)));
    int16_t edge[]={-32768,32767,-1,0,1};in[0]=(xqg_s16_view){edge,5,1,1,1,5,-5};
    assert(xqg_op_run(10,in,1,out,64,NULL,&result) && result.exponent==-5 && !memcmp(out,edge,sizeof(edge)));
    assert(xqg_op_run(11,in,1,out,64,NULL,&result) && out[0]==0 && out[1]==32767 && out[2]==0);
    int16_t minimum=-32768;in[0]=(xqg_s16_view){&minimum,1,1,1,1,1,-5};
    for(unsigned type=4;type<=6;type++){
        assert(xqg_op_run(type,in,1,out,64,NULL,&result));
        for(size_t i=0;i<result.count;i++)assert(out[i]==-32768);
    }
    int16_t square[]={100,200,300,400};
    const int16_t bilinear[]={100,125,175,200,150,175,225,250,250,275,325,350,300,325,375,400};
    in[0]=(xqg_s16_view){square,4,1,1,2,2,-5};
    assert(xqg_op_run(6,in,1,out,64,NULL,&result) && !memcmp(out,bilinear,sizeof(bilinear)));
    int16_t averages[]={0,1,1,2,-1,0,-2,-1};const int16_t gap[]={0,2,0,-2};
    in[0]=(xqg_s16_view){averages,8,1,4,1,2,0};
    assert(xqg_op_run(9,in,1,out,64,NULL,&result) && !memcmp(out,gap,sizeof(gap)));
    int16_t *large=malloc(65536*2),*table=malloc(65536*2);assert(large && table);
    for(unsigned i=0;i<65536;i++){large[i]=-32768;table[i]=(int16_t)((int)i-32768);}
    in[0]=(xqg_s16_view){large,65536,1,1,256,256,-5};
    assert(xqg_op_run(9,in,1,out,64,NULL,&result) && out[0]==-32768);
    in[0]=(xqg_s16_view){edge,5,1,1,1,5,-5};xqg_s16_lut lut={table,65536,-5,-15};
    assert(xqg_op_run(3,in,1,out,64,&lut,&result) && result.exponent==-15 && !memcmp(out,edge,sizeof(edge)));
    lut.input_exponent=-4;assert(!xqg_op_run(3,in,1,out,64,&lut,&result) && !result.data);
    assert(!xqg_op_run(12,in,1,out,64,NULL,&result) && !result.data);
    assert(!xqg_op_run(1,in,1,out,64,NULL,&result));
    assert(!xqg_op_run(10,in,1,out,4,NULL,&result) && !result.data);
    in[0].count=4;assert(!xqg_op_run(10,in,1,out,64,NULL,&result));
    in[0]=(xqg_s16_view){large,65792,1,1,257,256,-5};
    assert(!xqg_op_run(9,in,1,out,64,NULL,&result));
    free(large);free(table);
    puts("S16_OPS_BATCH2_TIES_EXP240_MINIMUM_I32_GAP_IDENTITY_AND_GUARDS_PASS");return 0;
}
