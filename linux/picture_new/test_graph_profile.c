#define _POSIX_C_SOURCE 200809L
#include "xq_native_graph.h"
#include "graph_profile.h"
#include "test_v321_mock.h"
#include "crc32_fast.h"
#include "xq_sha256.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static const char *phases[XQG_PHASES]={
    "quantize","dequantize","integer_requantize","fp32_sigmoid","fp32_maxpool",
    "fp32_nearest","fp32_bilinear","fp32_concat","fp32_add","fp32_avgpool",
    "fp32_identity","fp32_relu","weight_layout","input_layout",
    "output_layout_requant","staging_zero","submit_mock","integer_gap"};
static int load_input(const char *dir,const char *name,unsigned kind,float **out)
{
    char path[1024],magic[8];uint32_t h[8];int32_t exponent;
    FILE *f=NULL;int okay=0;int8_t *raw=NULL;int16_t *wide=NULL;float *input=NULL;
    unsigned side=kind==0?192:kind==1?640:32;
    if(snprintf(path,sizeof(path),"%s/%s.input",dir,name)>=(int)sizeof(path) || !(f=fopen(path,"rb")))goto done;
    if(fread(magic,1,8,f)!=8 || memcmp(magic,"XQINP1\0\0",8) || fread(h,4,8,f)!=8 || fread(&exponent,4,1,f)!=1 ||
       h[0]!=1 || h[1]!=kind || h[2]!=1 || h[3]!=3 || h[4]!=side || h[5]!=side || h[6]!=3*side*side)goto done;
    raw=malloc(h[6]);wide=malloc((size_t)h[6]*2);input=malloc((size_t)h[6]*4);
    if(!raw || !wide || !input || fread(raw,1,h[6],f)!=h[6] || fgetc(f)!=EOF || ferror(f) ||
       (crc32_fast(0xffffffffu,raw,h[6])^0xffffffffu)!=h[7])goto done;
    for(unsigned i=0;i<h[6];i++)wide[i]=raw[i];
    if(!xqi_dequantize(wide,h[6],exponent,input))goto done;
    *out=input;input=NULL;okay=1;
done:
    if(f)fclose(f);
    free(raw);free(wide);free(input);return okay;
}
int main(int argc,char **argv)
{
    static const char *names[]={"board","detector","classifier"};
    xqm_linux device={.fd=-1};int rc=2;
    if(argc!=3 || !v321_mock_open(&device))return 2;
    for(unsigned kind=0;kind<3;kind++){
        char path[1024];float *input=NULL;xqn_model *graph=NULL;xqm_stats stats={0};
        xqg_profile p;int okay=0;
        if(!load_input(argv[2],names[kind],kind,&input) ||
           snprintf(path,sizeof(path),"%s/%s.xqm",argv[1],names[kind])>=(int)sizeof(path) || !(graph=xqn_load(path)))goto model_done;
        v321_mock_reset(0);xqg_profile_reset();
        xqg_mark start=xqg_begin();
        if(!xqn_run(graph,&device.io,1,input,0,&stats))goto model_done;
        xqg_mark end=xqg_begin();xqg_profile_read(&p);
        if(p.clock_failures || end.wall<start.wall || end.cpu<start.cpu)goto model_done;
        printf("XQG_TOTAL model=%s wall=%llu cpu=%llu jobs=%llu\n",names[kind],
               (unsigned long long)(end.wall-start.wall),(unsigned long long)(end.cpu-start.cpu),(unsigned long long)stats.jobs);
        for(unsigned phase=0;phase<XQG_PHASES;phase++)
            printf("XQG_PHASE model=%s phase=%s wall=%llu cpu=%llu calls=%llu values=%llu\n",names[kind],phases[phase],
                   (unsigned long long)p.wall[phase],(unsigned long long)p.cpu[phase],
                   (unsigned long long)p.calls[phase],(unsigned long long)p.values[phase]);
        for(unsigned index=0;index<3;index++){
            unsigned dims[4];char hash[65];const float *out=xqn_output(graph,index,dims);if(!out)break;
            size_t bytes=(size_t)dims[0]*dims[1]*dims[2]*dims[3]*4;
            xq_sha256_hex(out,bytes,hash);
            printf("XQG_OUTPUT model=%s index=%u sha256=%s\n",names[kind],index,hash);
        }
        okay=1;
model_done:
        xqn_free(graph);free(input);if(!okay)goto done;
    }
    rc=0;
done:
    v321_mock_close(&device);return rc;
}
