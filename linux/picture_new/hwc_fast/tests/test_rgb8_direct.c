#define _POSIX_C_SOURCE 200809L
#define XQ_HWC_RGB8_DIRECT 1
#ifdef XQIH_RGB8_PREP_NO_PROBE
#define XQ_HWC_WORD_INPUT 1
#endif
#include "../adapter.c"
#include <assert.h>

/* The prior direct per-pixel implementation remains only as a test oracle. */
static int pixel_reference(const xqm_transport *io,const uint8_t *source,size_t bytes,
                            int exponent,void **destination)
{
    *destination=NULL;
    if(!source || bytes!=XQIH_RGB8_INPUT_BYTES)return 0;
    uint32_t *words=malloc(640u*640u*sizeof(*words));if(!words)return -1;
    int8_t palette[256];if(!xqih_rgb8_palette(exponent,palette))goto fail;
    for(unsigned y=0;y<640;y++) {
        for(unsigned c=0;c<3;c++)if(stopped(io))goto fail;
        size_t row=(size_t)y*640;
        for(unsigned x=0;x<640;x++) {
            size_t p=row+x;
            words[p]=(uint32_t)(uint8_t)palette[source[p]] |
                ((uint32_t)(uint8_t)palette[source[640u*640u+p]]<<8) |
                ((uint32_t)(uint8_t)palette[source[2u*640u*640u+p]]<<16);
        }
    }
    *destination=words;return 1;
fail:
    free(words);return 0;
}

#ifdef XQIH_RGB8_PREP_NO_PROBE
/* Keep the original C expression and materialized F32 boundary. Its buffer is
 * allocated before timing, while normalization and HWC malloc/packing are in. */
static __attribute__((noinline)) void frozen_normalize_rgb(const uint8_t *source,float *out)
{
    float unit[256];for(unsigned i=0;i<256;i++)unit[i]=(float)i/255.f;
    for(size_t i=0;i<XQIH_RGB8_INPUT_BYTES;i++)out[i]=unit[source[i]];
}
static int prepare(unsigned variant,const xqm_transport *io,const uint8_t *source,float *normalized,void **output)
{
    if(variant==2)return xqih_rgb8_input(io,source,XQIH_RGB8_INPUT_BYTES,-6,output);
    if(variant==1)return pixel_reference(io,source,XQIH_RGB8_INPUT_BYTES,-6,output);
    frozen_normalize_rgb(source,normalized);
    return xqih_word_input(io,normalized,-6,output);
}
int main(int argc,char **argv)
{
    assert(argc==1 || (argc==2 && !strcmp(argv[1],"--bench")));
    uint8_t *source=malloc(XQIH_RGB8_INPUT_BYTES);
    float *normalized=malloc(XQIH_RGB8_INPUT_BYTES*sizeof(float));assert(source && normalized);
    for(unsigned c=0;c<3;c++)for(size_t p=0;p<640u*640u;p++)
        source[c*640u*640u+p]=(uint8_t)(p*17u+c*43u+(p>>8));
    xqm_transport io={0};void *expected=NULL,*warm=NULL;
    assert(prepare(0,&io,source,normalized,&expected)==1);
    for(unsigned variant=1;variant<3;variant++) {
        assert(prepare(variant,&io,source,normalized,&warm)==1);
        assert(!memcmp(expected,warm,640u*640u*4));free(warm);warm=NULL;
    }
    if(argc==2) {
        for(unsigned repeat=0;repeat<3;repeat++)for(unsigned variant=0;variant<3;variant++) {
            struct timespec a,b;void *output=NULL;
            assert(!clock_gettime(CLOCK_MONOTONIC,&a));
            int okay=prepare(variant,&io,source,normalized,&output);
            assert(!clock_gettime(CLOCK_MONOTONIC,&b));assert(okay==1);
            /* Consume bytes after stopping the clock; includes no graph and
             * no normalization-buffer allocation, free, comparison or probe. */
            assert(!memcmp(expected,output,640u*640u*4));free(output);
            printf("RGB8_PREP_NO_PROBE_NS variant=%u value=%llu input_bytes=1228800 output_bytes=1638400\n",variant,
                (unsigned long long)(b.tv_sec-a.tv_sec)*1000000000u+b.tv_nsec-a.tv_nsec);
        }
    }else puts("RGB8_PREP_NO_PROBE_F32_PIXEL_BLOCK32_COMPLETE_HWC_BYTES_PASS_NOT_GRAPH_OR_BOARD");
    free(expected);free(normalized);free(source);return 0;
}
#else
static unsigned cancel_at,cancel_calls,fail_next_malloc,checks,palette_values;
void *__real_malloc(size_t);
void *__wrap_malloc(size_t size)
{if(fail_next_malloc){fail_next_malloc=0;return NULL;}return __real_malloc(size);}
static int cancellation(void *unused)
{(void)unused;++cancel_calls;return cancel_at && cancel_calls>=cancel_at;}
static int reference(const xqm_transport *io,const uint8_t *source,int exponent,void **destination)
{
    int8_t row[640],*out=calloc(640u*640u,4);float unit[256],normalized[640];
    *destination=NULL;if(!out)return -1;
    for(unsigned i=0;i<256;i++)unit[i]=(float)i/255.f;
    for(unsigned c=0;c<3;c++)for(unsigned y=0;y<640;y++) {
        if(stopped(io))goto fail;
        for(unsigned x=0;x<640;x++)normalized[x]=unit[source[((size_t)c*640+y)*640+x]];
        if(!xqi_quantize(normalized,640,exponent,row))goto fail;
        for(unsigned x=0;x<640;x++)out[((size_t)y*640+x)*4+c]=row[x];
    }
    *destination=out;return 1;
fail:
    free(out);return 0;
}
static void same(const xqm_transport *io,const uint8_t *source,int exponent,unsigned cancel)
{
    void *a=(void *)1,*b=(void *)1,*pixel=(void *)1;
    cancel_at=cancel;cancel_calls=0;int ra=reference(io,source,exponent,&a);
    cancel_calls=0;int rb=xqih_rgb8_input(io,source,XQIH_RGB8_INPUT_BYTES,exponent,&b);
    unsigned block_calls=cancel_calls;
    cancel_calls=0;int rp=pixel_reference(io,source,XQIH_RGB8_INPUT_BYTES,exponent,&pixel);
    assert(ra==rb && ra==rp);
    if(ra==1) {
        assert(a && b && pixel && !memcmp(a,b,640u*640u*4) && !memcmp(pixel,b,640u*640u*4));
        assert(cancel_calls==1920 && block_calls==1920);
        for(size_t i=0;i<640u*640u;i++)assert(((uint8_t *)b)[4*i+3]==0);
    }else assert(!a && !b && !pixel);
    free(a);free(b);free(pixel);++checks;
}
int main(void)
{
    for(int exponent=-120;exponent<=120;exponent++) {
        int8_t table[256];assert(xqih_rgb8_palette(exponent,table));
        for(unsigned color=0;color<256;color++) {
            float normalized=(float)color/255.f;int8_t value;
            assert(xqi_quantize(&normalized,1,exponent,&value) && table[color]==value);++palette_values;
        }
    }
    uint8_t *source=malloc(XQIH_RGB8_INPUT_BYTES);assert(source);
    for(unsigned c=0;c<3;c++)for(size_t p=0;p<640u*640u;p++)
        source[c*640u*640u+p]=(uint8_t)(p*17u+c*43u+(p>>8));
    xqm_transport io={.cancelled=cancellation};
    const int exponents[]={-120,-16,-7,-6,0,7,120};
    for(unsigned i=0;i<sizeof(exponents)/sizeof(*exponents);i++)same(&io,source,exponents[i],0);
    const unsigned cancellations[]={1,2,3,639,640,641,1919,1920};
    for(unsigned i=0;i<sizeof(cancellations)/sizeof(*cancellations);i++)same(&io,source,-6,cancellations[i]);
    same(&io,source,-121,0);same(&io,source,121,0);
    const size_t lengths[]={0,XQIH_RGB8_INPUT_BYTES-1,XQIH_RGB8_INPUT_BYTES+1,SIZE_MAX};
    for(unsigned i=0;i<sizeof(lengths)/sizeof(*lengths);i++) {
        void *out=(void *)1;cancel_calls=0;fail_next_malloc=1;
        assert(!xqih_rgb8_input(&io,source,lengths[i],-6,&out) && !out);
        assert(fail_next_malloc==1 && cancel_calls==0);fail_next_malloc=0;++checks;
    }
    void *out=(void *)1;cancel_calls=0;fail_next_malloc=1;
    assert(xqih_rgb8_input(&io,source,XQIH_RGB8_INPUT_BYTES,-6,&out)==-1 && !out);
    assert(!fail_next_malloc && cancel_calls==0);++checks;
    out=(void *)1;assert(!xqih_rgb8_input(&io,NULL,XQIH_RGB8_INPUT_BYTES,-6,&out) && !out);++checks;
    free(source);
    printf("RGB8_DIRECT_BLOCK32_PIXEL_F32_PALETTE_FULL_HWC_BYTES_LENGTH_CANCEL_OOM_PASS checks=%u palette_values=%u output_bytes=1638400\n",checks,palette_values);
    return 0;
}
#endif
