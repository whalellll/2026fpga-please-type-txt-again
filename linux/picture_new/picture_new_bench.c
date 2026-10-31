#define _POSIX_C_SOURCE 200809L
#include "xq_native_graph.h"
#include "crc32_fast.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static uint64_t now_us(void)
{
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t))exit(8);
    return (uint64_t)t.tv_sec*1000000u+(uint32_t)t.tv_nsec/1000u;
}
int main(int argc,char **argv)
{
    const char *names[]={"board","detector","classifier"};
    const unsigned sides[]={192,640,32};
    unsigned model=3,batch,repeats;int cpu,load_only,rc=2;
    xqm_linux device={.fd=-1};xqn_model *graph=NULL;float *input=NULL;FILE *file=NULL;
    uint64_t start,loaded,ready;
    if(argc!=7){fputs("usage: picture-new-bench board|detector|classifier graph.xqm input.f32 batch cpu|vision32|load repeats\n",stderr);return 2;}
    for(unsigned i=0;i<3;i++)if(!strcmp(argv[1],names[i]))model=i;
    char *end;unsigned long n=strtoul(argv[4],&end,10);if(*end || n<1 || n>256)return 2;batch=(unsigned)n;
    n=strtoul(argv[6],&end,10);if(*end || n<1 || n>5)return 2;repeats=(unsigned)n;
    cpu=!strcmp(argv[5],"cpu");load_only=!strcmp(argv[5],"load");
    if(model>2 || (model!=2 && batch!=1) || (!cpu && !load_only && strcmp(argv[5],"vision32")))return 2;
    start=now_us();
    {
        unsigned char h[16];file=fopen(argv[2],"rb");
        if(!file || fread(h,1,16,file)!=16 || memcmp(h,"XQGRPH1\0",8) || h[12]!=model || h[13] || h[14] || h[15])goto done;
        fclose(file);file=NULL;
    }
    graph=xqn_load(argv[2]);if(!graph)goto done;loaded=now_us();
    if(load_only){printf("PICTURE_MODEL_LOAD_PASS model=%s load_us=%llu\n",names[model],(unsigned long long)(loaded-start));rc=0;goto done;}
    size_t count=(size_t)batch*3*sides[model]*sides[model];
    input=malloc(count*4);if(!input)goto done;
    file=fopen(argv[3],"rb");
    if(!file || fread(input,4,count,file)!=count || fgetc(file)!=EOF)goto done;
    fclose(file);file=NULL;
    if(!cpu && !xqm_linux_open(&device)){fputs("VISION32_REQUIRED no_fallback=1\n",stderr);goto done;}
    ready=now_us();
    for(unsigned repeat=0;repeat<repeats;repeat++){
        xqm_stats stats={0};uint32_t crc=0xffffffffu;uint64_t a=now_us();
        int okay=xqn_run(graph,cpu?NULL:&device.io,batch,input,cpu,&stats);
        uint64_t b=now_us();if(!okay)goto done;
        for(unsigned i=0;i<3;i++){
            unsigned dims[4];const float *out=xqn_output(graph,i,dims);if(!out)break;
            size_t bytes=(size_t)dims[0]*dims[1]*dims[2]*dims[3]*4;
            crc=crc32_fast(crc,out,bytes);
        }
        printf("PICTURE_TIMING model=%s batch=%u backend=%s repeat=%u infer_us=%llu model_load_us=%llu input_open_us=%llu jobs=%llu cycles=%llu hardware_us=%llu output_crc=%08x no_fallback=1\n",
            names[model],batch,cpu?"cpu":"vision32",repeat,
            (unsigned long long)(b-a),(unsigned long long)(loaded-start),(unsigned long long)(ready-loaded),
            (unsigned long long)stats.jobs,(unsigned long long)stats.cycles,
            (unsigned long long)(stats.cycles/495u*10u+(stats.cycles%495u)*10u/495u),crc^0xffffffffu);
        fflush(stdout);
    }
    rc=0;
done:
    if(file)fclose(file);
    free(input);xqn_free(graph);xqm_linux_close(&device);return rc;
}
