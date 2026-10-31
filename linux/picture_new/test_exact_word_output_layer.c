#include "xq_int8_layer.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
unsigned xqewo_test_calls;
unsigned xqtest_jobs(void),xqtest_attempts(void),xqtest_raw_jobs(void);
void xqtest_fail_at(unsigned);
static int cancel_now;
static int stopped(void *unused){(void)unused;return cancel_now;}
int main(void)
{
    struct {unsigned batch,h,w,co,k,p,misaligned,word,rectangle;} cases[]={
        {1,2,3,2,1,0,0,1,0}, {1,2,4,3,1,0,0,0,0},
        {1,3,3,4,1,0,0,0,0}, {1,2,4,4,1,0,1,0,0},
        {1,6,5,4,3,1,0,1,0}, {3,2,4,4,1,0,0,1,0},
        {1,240,640,4,1,0,0,0,1}
    };
    xqm_linux device={.fd=-1};assert(xqm_linux_open(&device));device.io.cancelled=stopped;
    for(unsigned t=0;t<sizeof(cases)/sizeof(cases[0]);t++)for(unsigned use_lut=0;use_lut<2;use_lut++){
        xqi_shape s={.batch=cases[t].batch,.cin=1,.height=cases[t].h,.width=cases[t].w,
            .cout=cases[t].co,.kh=cases[t].k,.kw=cases[t].k,.stride_h=1,.stride_w=1,
            .pad_h=cases[t].p,.pad_w=cases[t].p,.dilation_h=1,.dilation_w=1};
        size_t pixels=(size_t)s.height*s.width,n=s.batch*s.cout*pixels;
        size_t ins=s.batch*pixels,weights=s.cout*s.kh*s.kw;
        int8_t *input=malloc(ins),*weight=malloc(weights),*lut=malloc(65536);
        int32_t *bias=malloc(s.cout*4);int64_t *shift=calloc(s.cout,8);
        uint8_t *buffer=malloc(n*2+64);int16_t *want=malloc(n*2);
        assert(input&&weight&&lut&&bias&&shift&&buffer&&want);
        int16_t *out=(void *)(buffer+16+2*cases[t].misaligned);
        for(size_t i=0;i<ins;i++)input[i]=(int8_t)((i*37u)%127u-63u);
        for(size_t i=0;i<weights;i++)weight[i]=(int8_t)((i*3u)%7u-3u);
        for(unsigned i=0;i<65536;i++)lut[i]=(int8_t)((i*73u+19u)&255u);
        const int32_t edges[]={-32768,-1,0,32767};
        for(unsigned c=0;c<s.cout;c++)bias[c]=edges[c&3u];
        xqi_shape cpu=s;cpu.cpu_reference=1;xqm_stats stats;
        assert(xqi_layer(NULL,&cpu,input,weight,bias,shift,lut,use_lut?65536:0,NULL,NULL,want,NULL));
        memset(buffer,0xa5,n*2+64);xqewo_test_calls=0;
        assert(xqi_layer(&device.io,&s,input,weight,bias,shift,lut,use_lut?65536:0,NULL,NULL,out,&stats));
        assert(!memcmp(out,want,n*2));
        assert((xqewo_test_calls>0)==cases[t].word);
        if(cases[t].rectangle)assert(stats.jobs>1);
        for(size_t i=0;i<16+2*cases[t].misaligned;i++)assert(buffer[i]==0xa5);
        for(size_t i=16+2*cases[t].misaligned+n*2;i<n*2+64;i++)assert(buffer[i]==0xa5);
        unsigned attempts=xqtest_attempts(),raw=xqtest_raw_jobs();
        xqtest_fail_at(attempts+1);xqewo_test_calls=0;memset(buffer,0xa5,n*2+64);
        assert(!xqi_layer(&device.io,&s,input,weight,bias,shift,lut,use_lut?65536:0,NULL,NULL,out,&stats));
        assert(xqtest_attempts()==attempts+1 && xqtest_raw_jobs()==raw && !xqewo_test_calls);
        for(size_t i=0;i<n*2+64;i++)assert(buffer[i]==0xa5);
        xqtest_fail_at(0);cancel_now=1;unsigned jobs=xqtest_jobs();
        assert(!xqi_layer(&device.io,&s,input,weight,bias,shift,lut,use_lut?65536:0,NULL,NULL,out,&stats));
        assert(xqtest_jobs()==jobs && !xqewo_test_calls);cancel_now=0;
        assert(xqi_layer(&device.io,&s,input,weight,bias,shift,lut,use_lut?65536:0,NULL,NULL,out,&stats));
        assert(!memcmp(out,want,n*2));
        free(input);free(weight);free(lut);free(bias);free(shift);free(buffer);free(want);
    }
    xqm_linux_close(&device);
    puts("EXACT_WORD_OUTPUT_REAL_LAYER_PASS cases=14 odd_channels_odd_planes_unaligned_rectangles=scalar lut_s16_bits=exact io_cancel_recovery=pass");
    return 0;
}
