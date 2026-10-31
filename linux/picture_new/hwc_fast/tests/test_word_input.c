#define _POSIX_C_SOURCE 200809L
#define XQ_HWC_WORD_INPUT 1
#include "../adapter.c"
#include <assert.h>

static unsigned cancel_at,cancel_calls;
static int fail_next_malloc;
void *__real_malloc(size_t);
void *__wrap_malloc(size_t n)
{if(fail_next_malloc){fail_next_malloc=0;return NULL;}return __real_malloc(n);}
static int cancellation(void *unused)
{(void)unused;++cancel_calls;return cancel_at && cancel_calls>=cancel_at;}
static int reference(const xqm_transport *io,const float *source,int exponent,void **destination)
{
    int8_t row[640],*out=calloc(640u*640u,4);*destination=NULL;
    if(!out)return -1;
#if XQ_HWC_RGB_QUANT
    xqih_input_table table;if(!xqih_input_table_init(&table,exponent))goto fail;
#endif
    for(unsigned c=0;c<3;c++)for(unsigned y=0;y<640;y++) {
        if(stopped(io))goto fail;
#if XQ_HWC_RGB_QUANT
        if(!xqih_input_quantize(&table,source+((size_t)c*640+y)*640,640,row))goto fail;
#else
        if(!xqi_quantize(source+((size_t)c*640+y)*640,640,exponent,row))goto fail;
#endif
        for(unsigned x=0;x<640;x++)out[((size_t)y*640+x)*4+c]=row[x];
    }
    *destination=out;return 1;
fail:
    free(out);return 0;
}
static unsigned checks;
static void compare(const xqm_transport *io,const float *input,int exponent,unsigned cancel)
{
    void *expected=(void *)1,*actual=(void *)1;
    cancel_at=cancel;cancel_calls=0;int a=reference(io,input,exponent,&expected);
    cancel_calls=0;int b=xqih_word_input(io,input,exponent,&actual);
    assert(a==b);
    if(a==1) {
        assert(expected && actual && !memcmp(expected,actual,640u*640u*4));
        const uint8_t *bytes=actual;
        for(size_t i=0;i<640u*640u;i++)assert(bytes[i*4+3]==0);
        assert(cancel_calls==1920);
    } else assert(!expected && !actual);
    free(expected);free(actual);++checks;
}
int main(void)
{
    const size_t count=3u*640u*640u;
    float *input=malloc(count*sizeof(*input));assert(input);
    xqm_transport io={.cancelled=cancellation};
    for(size_t i=0;i<count;i++)input[i]=(float)((i*71u+13u)%256u)/255.f;
    const int exponents[]={-120,-16,-7,-6,0,7,120};
    for(unsigned i=0;i<sizeof(exponents)/sizeof(exponents[0]);i++)compare(&io,input,exponents[i],0);
    const unsigned cancellations[]={1,2,3,639,640,641,1919,1920};
    for(unsigned i=0;i<sizeof(cancellations)/sizeof(cancellations[0]);i++)compare(&io,input,-6,cancellations[i]);
    uint32_t random=UINT32_C(0x2851ab73);
    for(size_t i=0;i<count;i++) {
        random^=random<<13;random^=random>>17;random^=random<<5;
        uint32_t bits=random;
        if((bits&UINT32_C(0x7f800000))==UINT32_C(0x7f800000))bits^=UINT32_C(0x00800000);
        memcpy(input+i,&bits,4);
    }
    compare(&io,input,-6,0);
    const uint32_t exceptions[]={UINT32_C(0x7f800000),UINT32_C(0xff800000),UINT32_C(0x7fc00000),UINT32_MAX};
    const size_t positions[]={0,640u+5u,640u*640u+123u,count-1};
    for(unsigned i=0;i<4;i++) {
        float saved=input[positions[i]];memcpy(input+positions[i],exceptions+i,4);
        compare(&io,input,-6,0);input[positions[i]]=saved;
    }
    cancel_at=0;cancel_calls=0;fail_next_malloc=1;
    void *output=(void *)1;assert(xqih_word_input(&io,input,-6,&output)==-1 && output==NULL);
    assert(!fail_next_malloc && cancel_calls==0);
    free(input);
    printf("HWC_WORD_INPUT_FULL_BYTES_RGB0_FLOAT_EXCEPTION_CANCEL_OOM_PASS_NOT_BOARD checks=%u rgb_lookup=%u\n",checks,XQ_HWC_RGB_QUANT);
    return 0;
}
