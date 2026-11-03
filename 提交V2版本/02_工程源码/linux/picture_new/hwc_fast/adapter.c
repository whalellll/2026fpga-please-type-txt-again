#define _POSIX_C_SOURCE 200809L
#include "adapter.h"
#include "xq_int8_layer.h"
#include "xq_sha256.h"
#ifndef XQ_HWC_RGB_QUANT
#define XQ_HWC_RGB_QUANT 0
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
int xqih_detect(xqih_detector *model,const xqm_transport *io,const float *source,
                float *output[3],xqm_stats *stats)
{
    xi8_tensor input={0};xi8_stats measured={0};
    int8_t row[640];int okay=0;
#ifdef XQ_GRAPH_PROFILE
    uint64_t start=0,packed=0,graphed=0,exported=0,export_core=0;
#endif
    if(stats)memset(stats,0,sizeof(*stats));
    if(!model || !io || !source || !output)return 0;
    for(unsigned i=0;i<3;i++){free(output[i]);output[i]=NULL;}
    if(!xqv_exact_available(io) || stopped(io))return 0;
#ifdef XQ_GRAPH_PROFILE
    start=xi8_now();
#endif
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
#ifdef XQ_GRAPH_PROFILE
    packed=xi8_now();
#endif
    if(!xi8_run(model,io,&input,&measured) || stopped(io))goto done;
#ifdef XQ_GRAPH_PROFILE
    graphed=xi8_now();
#endif
    for(unsigned i=0;i<3;i++){
        size_t count=xi8_output_elements(model,i);
        if(!count || stopped(io) || !(output[i]=malloc(count*4)))goto done;
#ifdef XQ_GRAPH_PROFILE
        uint64_t mark=xi8_now();
#endif
        if(!xi8_export_f32(model,i,output[i],count*4,NULL))goto done;
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
