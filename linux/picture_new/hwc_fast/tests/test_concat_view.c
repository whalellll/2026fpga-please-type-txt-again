#define _POSIX_C_SOURCE 200809L
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wmisleading-indentation"
#include "../integer_hwc.c"
#pragma GCC diagnostic pop
#include "../concat_view.h"
#include <assert.h>
int xqv_run(const xqm_transport *io,struct pango_vision32_job *j){(void)io;(void)j;abort();}
void xqv_parameters_begin(const xqm_transport *io,struct pango_vision32_job *j){(void)io;(void)j;abort();}
int xqv_exact_available(const xqm_transport *io){(void)io;abort();}
static unsigned cases,cancel_calls;
static int cancel(void *p){(void)p;return ++cancel_calls>=2;}
static void check(unsigned width,unsigned height,unsigned parts,unsigned bits,unsigned shift,int delta,unsigned pattern)
{
    int32_t nodes[8][32]={{0}};xi8_model model={0};xi8_tensor values[200]={{0}},materialized={0};
    model.n=nodes;model.h[2]=8;model.h[4]=5;model.h[5]=6;model.h[6]=7;
    int32_t *n=nodes[4];n[0]=7;n[4]=(int32_t)parts;n[19]=-4;n[26]=1;n[27]=(int32_t)bits;
    nodes[5][0]=1;nodes[5][4]=1;nodes[5][5]=4;
    unsigned channels=0;
    for(unsigned p=0;p<parts;p++){
        xi8_tensor *v=values+p;v->c=pattern==2?1:p%2?3:1;v->pitch=v->c+2;v->w=width;v->h=height;
        v->bits=pattern==1?8:p%2?8:16;v->exponent=-4+(int)(p?shift%3:shift);n[5+p]=(int32_t)p;
        size_t count=(size_t)width*height*v->pitch;v->data=malloc(count*v->bits/8);assert(v->data);
        for(size_t i=0;i<count;i++)put(v,i,(int16_t)(i*509+p*73+pattern*101));
        channels+=v->c;
    }
    n[1]=(int32_t)channels;n[2]=(int32_t)height;n[3]=(int32_t)width;
    materialized=(xi8_tensor){.c=channels,.pitch=channels,.w=width,.h=height,.bits=bits,.exponent=-4};
    materialized.data=malloc((size_t)width*height*channels*bits/8);assert(materialized.data);
    assert(nonconv(n,values,&materialized));xqih_concat_view view;
    assert(xqih_concat_plan(&model,4,values,&view));
    unsigned rectangles[3][4]={{0,0,width,height},{2,3,width+4,height+6},{width-1,height-1,3,4}};
    for(unsigned i=0;i<3;i++){
        int sx=i==1?-(int)rectangles[i][0]:(int)rectangles[i][0];
        int sy=i==1?-(int)rectangles[i][1]:(int)rectangles[i][1];
        unsigned w=rectangles[i][2],h=rectangles[i][3];size_t bytes=(size_t)w*h*align4(channels);
        uint8_t *expected=malloc(bytes),*guard=malloc(bytes+128);assert(expected && guard);memset(expected,0x5a,bytes);memset(guard,0xa5,bytes+128);
        xi8_stats before={0},after={0};xqm_transport io={0};
        pack_input(expected,&materialized,w,h,sx,sy,-4-delta,&before);
        assert(xqih_pack_concat(guard+64,&view,w,h,sx,sy,-4-delta,&after,&io));
        assert(!memcmp(expected,guard+64,bytes));assert(before.input_zero_bytes==after.input_zero_bytes);
        for(unsigned j=0;j<64;j++)assert(guard[j]==0xa5 && guard[bytes+64+j]==0xa5);
        cancel_calls=0;io.cancelled=cancel;assert(!xqih_pack_concat(guard+64,&view,w,h+1,sx,sy,-4-delta,&after,&io));
        free(expected);free(guard);cases++;
    }
    xqih_concat_view saved;memset(&saved,0x5a,sizeof(saved));view=saved;
    n[26]=2;assert(!xqih_concat_plan(&model,4,values,&view) && !memcmp(&saved,&view,sizeof(view)));n[26]=1;
    nodes[5][5]=3;assert(!xqih_concat_plan(&model,4,values,&view));nodes[5][5]=4;
    model.h[4]=4;assert(!xqih_concat_plan(&model,4,values,&view));model.h[4]=5;
    int exponent=values[0].exponent;values[0].exponent=-5;assert(!xqih_concat_plan(&model,4,values,&view));
    values[0].exponent=-4+(int)(33-values[0].bits);assert(!xqih_concat_plan(&model,4,values,&view));values[0].exponent=exponent;
    for(unsigned p=0;p<parts;p++)xi8_tensor_free(values+p);
    xi8_tensor_free(&materialized);
}
int main(void)
{
    assert(!xqih_run_concat(NULL,NULL,NULL,NULL,NULL));
    int deltas[]={-20,-8,-1,0,1,7};
    for(unsigned i=0;i<6;i++)for(unsigned bits=8;bits<=16;bits+=8)for(unsigned p=2;p<=4;p+=2){
        check(1+i*5,1+i, p,bits,i%3,deltas[i],0);
    }
    for(unsigned bits=8;bits<=16;bits+=8)for(unsigned shift=0;shift<=16;shift+=8)
        for(unsigned i=0;i<6;i++)check(128,512,2,bits,shift,deltas[i],2);
    for(unsigned bits=8;bits<=16;bits+=8)for(unsigned i=0;i<6;i++){
        check(256,1,4,bits,0,deltas[i],1);check(256,1,2,bits,24,deltas[i],1);
    }
    printf("CONCAT_VIEW_TWO_STAGE_STORAGE_HALO_PITCH_S8_S16_CANCEL_AND_REJECT_PASS cases=%u\n",cases);return 0;
}
