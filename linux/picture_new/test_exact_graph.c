#include "xq_native_graph.h"
#include "crc32_fast.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
unsigned xqtest_jobs(void),xqtest_attempts(void),xqtest_raw_jobs(void),xqtest_exact_jobs(void);
void xqtest_fail_at(unsigned);
static int stop_after;
static int stopped(void *unused){(void)unused;return stop_after && xqtest_jobs()>=(unsigned)stop_after;}
static float *input(const char *dir,unsigned role,unsigned batch)
{
    const char *names[]={"board","detector","classifier"};char path[1024],magic[8];uint32_t h[8];int32_t e;
    snprintf(path,sizeof(path),"%s/%s.input",dir,names[role]);FILE *f=fopen(path,"rb");assert(f);
    assert(fread(magic,1,8,f)==8 && !memcmp(magic,"XQINP1\0\0",8) && fread(h,4,8,f)==8 && fread(&e,4,1,f)==1);
    assert(h[0]==1 && h[1]==role && h[2]==1 && h[3]==3);
    int8_t *codes=malloc(h[6]);int16_t *wide=malloc((size_t)h[6]*2);float *v=malloc((size_t)h[6]*batch*4);assert(codes && wide && v);
    assert(fread(codes,1,h[6],f)==h[6] && fgetc(f)==EOF && (crc32_fast(0xffffffffu,codes,h[6])^0xffffffffu)==h[7]);fclose(f);
    for(unsigned i=0;i<h[6];i++)wide[i]=codes[i];assert(xqi_dequantize(wide,h[6],e,v));
    for(unsigned b=1;b<batch;b++)memcpy(v+(size_t)b*h[6],v,(size_t)h[6]*4);
    free(codes);free(wide);return v;
}
int main(int argc,char **argv)
{
    assert(argc==3);const char *names[]={"board","detector","classifier"};
    xqm_linux device={.fd=-1};assert(xqm_linux_open(&device));device.io.cancelled=stopped;
    for(unsigned role=0;role<3;role++)for(unsigned trial=0;trial<(role==2?3u:1u);trial++){
        unsigned batches[3]={1,3,8},batch=role==2?batches[trial]:1;char path[1024];
        snprintf(path,sizeof(path),"%s/%s.xqm",argv[1],names[role]);xqn_model *m=xqn_load(path);assert(m);
        float *v=input(argv[2],role,batch),*expected[3]={0};size_t bytes[3]={0};xqm_stats stats;
        assert(xqn_run(m,NULL,batch,v,1,&stats));
        for(unsigned head=0;head<3;head++){
            unsigned dims[4];const float *p=xqn_output(m,head,dims);if(!p)continue;
            bytes[head]=(size_t)dims[0]*dims[1]*dims[2]*dims[3]*4;expected[head]=malloc(bytes[head]);assert(expected[head]);memcpy(expected[head],p,bytes[head]);
        }
        unsigned exact=xqtest_exact_jobs();assert(xqn_run(m,&device.io,batch,v,0,&stats));
        for(unsigned head=0;head<3;head++)if(bytes[head])assert(!memcmp(xqn_output(m,head,NULL),expected[head],bytes[head]));
        assert(xqtest_exact_jobs()>exact); /* Red on the old CPU epilogue path. */
        unsigned features=device.features,raw=xqtest_raw_jobs();exact=xqtest_exact_jobs();device.features&=~PANGO_MAC_FEATURE_VISION32_EXACT;
        assert(xqn_run(m,&device.io,batch,v,0,&stats) && xqtest_raw_jobs()>raw && xqtest_exact_jobs()==exact);
        for(unsigned head=0;head<3;head++)if(bytes[head])assert(!memcmp(xqn_output(m,head,NULL),expected[head],bytes[head]));
        device.features=features;
        unsigned attempts=xqtest_attempts();raw=xqtest_raw_jobs();xqtest_fail_at(attempts+1);
        assert(!xqn_run(m,&device.io,batch,v,0,&stats) && xqtest_attempts()==attempts+1 && xqtest_raw_jobs()==raw);
        for(unsigned head=0;head<3;head++)assert(!xqn_output(m,head,NULL));xqtest_fail_at(0);
        stop_after=(int)xqtest_jobs()+1;assert(!xqn_run(m,&device.io,batch,v,0,&stats));
        for(unsigned head=0;head<3;head++)assert(!xqn_output(m,head,NULL));stop_after=0;
        for(unsigned head=0;head<3;head++)free(expected[head]);free(v);xqn_free(m);
        printf("EXACT_GRAPH_CPU_REFERENCE_BIT_EQUAL model=%s batch=%u old_caps_raw2=1 ioctl_fatal=1 cancel_invalidates=1\n",names[role],batch);
    }
    xqm_linux other={.fd=-1};assert(xqm_linux_open(&other));assert(other.io.shadow!=device.io.shadow);xqm_linux_close(&other);
    xqm_linux_close(&device);puts("EXACT_GRAPH_ALL3_CLASSIFIER_B1_3_8_OUTPUT_CAPS_FATAL_CANCEL_PASS_NOT_BOARD");return 0;
}
