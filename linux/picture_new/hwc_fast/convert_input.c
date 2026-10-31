#define _POSIX_C_SOURCE 200809L
#include "xq_roi.h"
#include "xq_int8_layer.h"
#include "xq_sha256.h"
#include "crc32_fast.h"
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Host handoff tool. Reuse the product's byte resize and frozen quantizer;
 * PNG decoding is lossless RGB8 in the wrapper, never a second resize path. */
static void *read_exact(const char *path,size_t bytes)
{
    FILE *f=fopen(path,"rb");
    void *data=malloc(bytes);
    int okay=f && data && fread(data,1,bytes,f)==bytes && fgetc(f)==EOF && !ferror(f);
    if(f)fclose(f);
    if(!okay){free(data);return NULL;}
    return data;
}
static int number(const char *s,int *v)
{
    char *end;long n=strtol(s,&end,10);
    if(!*s || *end || n<0 || n>1280)return 0;
    *v=(int)n;return 1;
}
static int model_exponent(const char *path,int *exponent)
{
    const size_t size=5582128;
    unsigned char *data=read_exact(path,size);
    char digest[65];int okay=0;
    if(!data)return 0;
    xq_sha256_hex(data,size,digest);
    if(!strcmp(digest,"d72d039041b41310f037344772eb75ce895ec6fe678bbb31ed547a7ad7453942")){
        int32_t value;memcpy(&value,data+48+18*4,4);*exponent=value;okay=1;
    }
    free(data);return okay;
}
int main(int argc,char **argv)
{
    int w,h,x0,y0,x1,y1,exponent,code=2;
    float *values=NULL;
    uint8_t *source=NULL,*rgb=NULL,*scaled=NULL,*chw=NULL;
    int8_t *quantized=NULL,*body=NULL;
    xqr_letterbox plan={0};
    if(argc!=11){
        fputs("usage: hwc-convert model.xqi nchw-f32|rgb8|rgb565 input w h x0 y0 x1 y1 output.hwc8\n",stderr);
        return 2;
    }
    if(!number(argv[4],&w) || !number(argv[5],&h) || !number(argv[6],&x0) ||
       !number(argv[7],&y0) || !number(argv[8],&x1) || !number(argv[9],&y1) ||
       !w || !h || h>720 || x0>=x1 || y0>=y1 || x1>w || y1>h ||
       !model_exponent(argv[1],&exponent))goto done;
    if(!strcmp(argv[2],"nchw-f32")){
        if(w!=640 || h!=640 || x0 || y0 || x1!=640 || y1!=640)goto done;
        values=read_exact(argv[3],3u*640u*640u*4u);if(!values)goto done;
    }else{
        const size_t pixels=(size_t)w*h;
        if(!strcmp(argv[2],"rgb8")){
            rgb=read_exact(argv[3],pixels*3);if(!rgb)goto done;
        }else if(!strcmp(argv[2],"rgb565")){
            if(w!=1280 || h!=720)goto done;
            source=read_exact(argv[3],pixels*2);rgb=malloc(pixels*3);
            xqv_frame frame={.rgb565=(const uint32_t *)source,.bytes=pixels*2};
            if(!source || !rgb || !xqr_rgb565(&frame,rgb,pixels*3))goto done;
        }else goto done;
        xqr_roi roi={x0,y0,x1,y1};
        if(!xqr_letterbox_plan(roi,640,&plan))goto done;
        const size_t small=(size_t)plan.width*plan.height;
        scaled=malloc(small*3);chw=malloc(3u*640u*640u);values=malloc(3u*640u*640u*4u);
        if(!scaled || !chw || !values ||
           !xqr_resize_rgb(rgb,(unsigned)w,(unsigned)h,(size_t)w*3,x0,y0,x1,y1,
                           plan.width,plan.height,scaled,small*3))goto done;
        memset(chw,114,3u*640u*640u);
        for(unsigned c=0;c<3;c++)for(unsigned y=0;y<plan.height;y++)
            memcpy(chw+(size_t)c*640*640+(y+plan.top)*640+plan.left,
                   scaled+(size_t)c*small+y*plan.width,plan.width);
        float unit[256];for(unsigned i=0;i<256;i++)unit[i]=(float)i/255.f;
        for(size_t i=0;i<3u*640u*640u;i++)values[i]=unit[chw[i]];
    }
    quantized=malloc(3u*640u*640u);body=calloc(640u*640u,4);
    if(!quantized || !body || !xqi_quantize(values,3u*640u*640u,exponent,quantized))goto done;
    for(size_t i=0;i<640u*640u;i++)for(unsigned c=0;c<3;c++)
        body[i*4+c]=quantized[(size_t)c*640*640+i];
    uint32_t header[8]={1,640,640,3,4,640u*640u*4u,(uint32_t)exponent,
                        crc32_fast(0xffffffffu,body,640u*640u*4u)^0xffffffffu};
    FILE *out=fopen(argv[10],"wb");if(!out)goto done;
    int okay=fwrite("XQHWC81\0",1,8,out)==8 && fwrite(header,4,8,out)==8 &&
             fwrite(body,1,640u*640u*4u,out)==640u*640u*4u;
    if(fclose(out))okay=0;
    if(!okay)goto done;
    printf("HWC_INPUT_CONVERTED exponent=%d crc=%08x width=%u height=%u left=%u top=%u ratio=%.17g pad_x=%.17g pad_y=%.17g\n",
           exponent,header[7],plan.width,plan.height,plan.left,plan.top,plan.ratio,plan.pad_x,plan.pad_y);
    code=0;
done:
    if(code)fputs("HWC_INPUT_REJECTED: check frozen model, input size/finite values and same-frame ROI\n",stderr);
    free(values);free(source);free(rgb);free(scaled);free(chw);free(quantized);free(body);
    return code;
}
