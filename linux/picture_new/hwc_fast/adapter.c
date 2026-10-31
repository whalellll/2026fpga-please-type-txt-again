#define _POSIX_C_SOURCE 200809L
#include "adapter.h"
#include "xq_int8_layer.h"
#include "xq_sha256.h"
#ifndef XQ_HWC_RGB_QUANT
#define XQ_HWC_RGB_QUANT 0
#endif
#ifndef XQ_HWC_WORD_INPUT
#define XQ_HWC_WORD_INPUT 0
#endif
#ifndef XQ_HWC_TILE_EXPORT
#define XQ_HWC_TILE_EXPORT 0
#endif
#ifndef XQ_HWC_RGB8_DIRECT
#define XQ_HWC_RGB8_DIRECT 0
#endif
#ifndef XQ_HWC_TAIL_COLUMNS
#define XQ_HWC_TAIL_COLUMNS 0
#endif
#ifndef XQ_HWC_CONCAT_VIEW
#define XQ_HWC_CONCAT_VIEW 0
#endif
#if XQ_HWC_CONCAT_VIEW != 0 && XQ_HWC_CONCAT_VIEW != 1
#error XQ_HWC_CONCAT_VIEW_must_be_zero_or_one
#endif
#if XQ_HWC_TAIL_COLUMNS != 0 && XQ_HWC_TAIL_COLUMNS != 1
#error XQ_HWC_TAIL_COLUMNS_must_be_zero_or_one
#endif
#if XQ_HWC_RGB_QUANT
#include "input_quant.c"
#endif

/* The reviewed provider source is kept byte-identical. Its compact formatting
 * predates this branch's warning policy; keep the exception in this include. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wmisleading-indentation"
#include "integer_hwc.c"
#pragma GCC diagnostic pop
#if XQ_HWC_TAIL_COLUMNS
#include "tail_columns.h"
#endif
#if XQ_HWC_CONCAT_VIEW
#include "concat_view.h"
#endif
#ifndef XQIH_STATS_NOTE
#define XQIH_STATS_NOTE(stats,views) ((void)0)
#endif
#if XQ_HWC_TILE_EXPORT
#include "export_tile.h"
#endif

static int frozen_derived_pack(const xi8_model *model)
{
    const size_t bytes=48u+model->h[8];
    unsigned char *data=malloc(bytes);
    char digest[65];
    if(!data)return 0;
    memcpy(data,"XQINT81\0",8);
    memcpy(data+8,model->h,40);
    memcpy(data+48,model->body,model->h[8]);
    xq_sha256_hex(data,bytes,digest);
    free(data);
    return !strcmp(digest,"d72d039041b41310f037344772eb75ce895ec6fe678bbb31ed547a7ad7453942");
}
xqih_detector *xqih_open(const char *source_pack,const uint32_t header[10])
{
    static const uint32_t frozen_header[10]={1,1,85,3,82,83,84,
        0x54f550,0x551fd0,0x3c17991f};
    char path[1024];
    const char *base;
    size_t prefix;
    if(!source_pack || !header || memcmp(header,frozen_header,sizeof(frozen_header)))return NULL;
    base=strrchr(source_pack,'/');base=base?base+1:source_pack;
    if(strcmp(base,"detector.xqm"))return NULL;
    prefix=(size_t)(base-source_pack);
    if(prefix+sizeof("detector.xqi")>sizeof(path))return NULL;
    memcpy(path,source_pack,prefix);
    memcpy(path+prefix,"detector.xqi",sizeof("detector.xqi"));
    xi8_model *model=xi8_load(path);
    if(model && !frozen_derived_pack(model)){xi8_free(model);model=NULL;}
    return model;
}
void xqih_close(xqih_detector *model){xi8_free(model);}
static int stopped(const xqm_transport *io)
{return io->cancelled && io->cancelled(io->context);}
#if XQ_HWC_RGB8_DIRECT
#include "rgb8_direct.h"
#endif
#if XQ_HWC_WORD_INPUT
/* Normal malloc RAM only. Each word writes RGB plus the required zero lane;
 * no zero-filled allocation or MMIO access is used. Quantization is unchanged.
 * Failure never exposes the partly packed buffer. -1 retains the old immediate
 * allocation-failure return; 0 follows the caller's ordinary cleanup path. */
static int xqih_word_input(const xqm_transport *io,const float *source,int exponent,void **destination)
{
#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error XQ_HWC_WORD_INPUT_requires_the_frozen_little_endian_host_or_RV32_ABI
#endif
    int8_t rows[3][640];
    uint32_t *words=malloc(640u*640u*sizeof(*words));
    *destination=NULL;
    if(!words)return -1;
#if XQ_HWC_RGB_QUANT
    xqih_input_table table;if(!xqih_input_table_init(&table,exponent))goto fail;
#endif
    for(unsigned y=0;y<640;y++) {
        for(unsigned c=0;c<3;c++) {
            if(stopped(io))goto fail;
#if XQ_HWC_RGB_QUANT
            if(!xqih_input_quantize(&table,source+((size_t)c*640+y)*640,640,rows[c]))goto fail;
#else
            if(!xqi_quantize(source+((size_t)c*640+y)*640,640,exponent,rows[c]))goto fail;
#endif
        }
        for(unsigned x=0;x<640;x++)
            words[(size_t)y*640+x]=(uint32_t)(uint8_t)rows[0][x] |
                ((uint32_t)(uint8_t)rows[1][x]<<8) | ((uint32_t)(uint8_t)rows[2][x]<<16);
    }
    *destination=words;return 1;
fail:
    free(words);return 0;
}
#endif
#if XQ_HWC_RGB8_DIRECT
static int xqih_detect_input(xqih_detector *model,const xqm_transport *io,const float *source,
                             const uint8_t *rgb8_source,size_t rgb8_bytes,
                             float *output[3],xqm_stats *stats)
#else
int xqih_detect(xqih_detector *model,const xqm_transport *io,const float *source,
                float *output[3],xqm_stats *stats)
#endif
{
    xi8_tensor input={0};xi8_stats measured={0};
#if XQ_HWC_CONCAT_VIEW
    xqih_concat_stats views={0};
#endif
    int okay=0;
#if !XQ_HWC_WORD_INPUT
    int8_t row[640];
#endif
#ifdef XQ_GRAPH_PROFILE
    uint64_t start=0,packed=0,graphed=0,exported=0,export_core=0;
#endif
    if(stats)memset(stats,0,sizeof(*stats));
#if XQ_HWC_RGB8_DIRECT
    if(!model || !io || (!source && !rgb8_source) || !output)return 0;
#else
    if(!model || !io || !source || !output)return 0;
#endif
    for(unsigned i=0;i<3;i++){free(output[i]);output[i]=NULL;}
#if XQ_HWC_RGB8_DIRECT
    if(rgb8_source && rgb8_bytes!=XQIH_RGB8_INPUT_BYTES)return 0;
#endif
    if(!xqv_exact_available(io) || stopped(io))return 0;
#ifdef XQ_GRAPH_PROFILE
    start=xi8_now();
#endif
/* Default keeps the original scatter and allocation/error behavior. */
#if XQ_HWC_RGB8_DIRECT
    if(rgb8_source) {
        input=(xi8_tensor){.c=3,.h=640,.w=640,.pitch=4,.bits=8,.exponent=model->n[0][18]};
        int prepared=xqih_rgb8_input(io,rgb8_source,rgb8_bytes,input.exponent,&input.data);
        if(prepared<0)return 0;
        if(!prepared)goto done;
    }else {
#endif
#if XQ_HWC_WORD_INPUT
    input=(xi8_tensor){.c=3,.h=640,.w=640,.pitch=4,.bits=8,.exponent=model->n[0][18]};
    int prepared=xqih_word_input(io,source,input.exponent,&input.data);
    if(prepared<0)return 0;
    if(!prepared)goto done;
#else
    input=(xi8_tensor){.data=calloc(640u*640u,4),.c=3,.h=640,.w=640,
                       .pitch=4,.bits=8,.exponent=model->n[0][18]};
    if(!input.data)return 0;
#if XQ_HWC_RGB_QUANT
    xqih_input_table table;if(!xqih_input_table_init(&table,input.exponent))goto done;
#endif
    for(unsigned c=0;c<3;c++)for(unsigned y=0;y<640;y++){
        if(stopped(io))goto done;
#if XQ_HWC_RGB_QUANT
        if(!xqih_input_quantize(&table,source+((size_t)c*640+y)*640,640,row))goto done;
#else
        if(!xqi_quantize(source+((size_t)c*640+y)*640,640,input.exponent,row))goto done;
#endif
        for(unsigned x=0;x<640;x++)((int8_t *)input.data)[((size_t)y*640+x)*4+c]=row[x];
    }
#endif
#if XQ_HWC_RGB8_DIRECT
    }
#endif
#ifdef XQ_GRAPH_PROFILE
    packed=xi8_now();
#endif
#if XQ_HWC_CONCAT_VIEW
    if(!xqih_run_concat(model,io,&input,&measured,&views) || stopped(io))goto done;
    XQIH_STATS_NOTE(&measured,&views);
#elif XQ_HWC_TAIL_COLUMNS
    if(!xqih_run_tail(model,io,&input,&measured) || stopped(io))goto done;
#else
    if(!xi8_run(model,io,&input,&measured) || stopped(io))goto done;
#endif
#ifdef XQ_GRAPH_PROFILE
    graphed=xi8_now();
#endif
    for(unsigned i=0;i<3;i++){
        size_t count=xi8_output_elements(model,i);
        if(!count || stopped(io) || !(output[i]=malloc(count*4)))goto done;
#ifdef XQ_GRAPH_PROFILE
        uint64_t mark=xi8_now();
#endif
#if XQ_HWC_TILE_EXPORT
        if(!xqih_export_f32_tiled(model,i,output[i],count*4,NULL))goto done;
#else
        if(!xi8_export_f32(model,i,output[i],count*4,NULL))goto done;
#endif
#ifdef XQ_GRAPH_PROFILE
        export_core+=xi8_now()-mark;
#endif
    }
#ifdef XQ_GRAPH_PROFILE
    exported=xi8_now();
#endif
    if(stats){stats->jobs=measured.jobs;stats->cycles=measured.cycles;}
    okay=1;
done:
    xi8_tensor_free(&input);
    if(!okay)for(unsigned i=0;i<3;i++){free(output[i]);output[i]=NULL;}
#ifdef XQ_GRAPH_PROFILE
    if(okay){
        uint64_t parts=measured.pack_ticks+measured.output_ticks+measured.weight_ticks+
            measured.ioctl_ticks+measured.ops_ticks+measured.allocate_ticks;
        printf("XQ_HWC_PROFILE okay=1 rgb_lookup=%u input_us=%llu graph_us=%llu heads_us=%llu export_core_us=%llu same_output_us=%llu total_us=%llu pack_us=%llu output_pack_us=%llu parameter_us=%llu ioctl_us=%llu nonconv_us=%llu allocate_us=%llu other_us=%llu jobs=%llu cycles=%llu\n",
            XQ_HWC_RGB_QUANT,(unsigned long long)xi8_us(packed-start),(unsigned long long)xi8_us(graphed-packed),
            (unsigned long long)xi8_us(exported-graphed),(unsigned long long)xi8_us(export_core),
            (unsigned long long)xi8_us(graphed-packed+export_core),(unsigned long long)xi8_us(exported-start),
            (unsigned long long)xi8_us(measured.pack_ticks),(unsigned long long)xi8_us(measured.output_ticks),
            (unsigned long long)xi8_us(measured.weight_ticks),(unsigned long long)xi8_us(measured.ioctl_ticks),
            (unsigned long long)xi8_us(measured.ops_ticks),(unsigned long long)xi8_us(measured.allocate_ticks),
            (unsigned long long)xi8_us(graphed-packed>=parts?graphed-packed-parts:0),
            (unsigned long long)measured.jobs,(unsigned long long)measured.cycles);
    }else puts("XQ_HWC_PROFILE okay=0");
#endif
    return okay;
}
#if XQ_HWC_RGB8_DIRECT
int xqih_detect(xqih_detector *model,const xqm_transport *io,const float *source,
                float *output[3],xqm_stats *stats)
{return xqih_detect_input(model,io,source,NULL,0,output,stats);}
int xqih_detect_rgb8(xqih_detector *model,const xqm_transport *io,const uint8_t *source,
                     size_t bytes,float *output[3],xqm_stats *stats)
{return xqih_detect_input(model,io,NULL,source,bytes,output,stats);}
#endif
