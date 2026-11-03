#define _POSIX_C_SOURCE 200809L
#include "xq_native_graph.h"
#include "crc32_fast.h"
#include "xq_sha256.h"
#include "test_v321_mock.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned records,observer_error;
static v321_mock_counts previous;
static void observe(void *context,unsigned layer,const int8_t *q,size_t qn,
                    const int16_t *out,size_t on,const int32_t *acc,const int16_t *pre)
{
    FILE *f=context;v321_mock_counts current;
    char qhash[65],ahash[65],phash[65],ohash[65];
    v321_mock_read(&current);
    /* Every observed layer must have completed at least one V321 ioctl. */
    if(current.jobs<=previous.jobs || current.errors || current.unexpected || !q || !acc || !pre || !out){observer_error=1;return;}
    xq_sha256_hex(q,qn,qhash);xq_sha256_hex(acc,on*4,ahash);
    xq_sha256_hex(pre,on*2,phash);xq_sha256_hex(out,on*2,ohash);
    if(fprintf(f,"%u %zu %zu %08x %08x %08x %08x %s %s %s %s\n",layer,qn,on,
        crc32_fast(0xffffffffu,q,(uint32_t)qn)^0xffffffffu,
        crc32_fast(0xffffffffu,acc,(uint32_t)(on*4))^0xffffffffu,
        crc32_fast(0xffffffffu,pre,(uint32_t)(on*2))^0xffffffffu,
        crc32_fast(0xffffffffu,out,(uint32_t)(on*2))^0xffffffffu,qhash,ahash,phash,ohash)<0)observer_error=1;
    printf("V321_MOCK_LAYER layer=%u jobs=%llu\n",layer,(unsigned long long)(current.jobs-previous.jobs));
    previous=current;records++;
}
static int load_input(const char *directory,unsigned model,float **out)
{
    static const char *names[]={"board","detector","classifier"};
    char path[1024],magic[8];uint32_t h[8];int32_t exponent;
    int okay=0;FILE *f=NULL;int8_t *input=NULL;int16_t *wide=NULL;float *tensor=NULL;
    unsigned side=model==0?192:model==1?640:32;
    if(snprintf(path,sizeof(path),"%s/%s.input",directory,names[model])>=(int)sizeof(path) || !(f=fopen(path,"rb")))goto done;
    if(fread(magic,1,8,f)!=8 || memcmp(magic,"XQINP1\0\0",8) || fread(h,4,8,f)!=8 || fread(&exponent,4,1,f)!=1 ||
       h[0]!=1 || h[1]!=model || h[2]!=1 || h[3]!=3 || h[4]!=side || h[5]!=side || h[6]!=3*side*side)goto done;
    input=malloc(h[6]);wide=malloc((size_t)h[6]*2);tensor=malloc((size_t)h[6]*4);
    if(!input || !wide || !tensor || fread(input,1,h[6],f)!=h[6] || fgetc(f)!=EOF || ferror(f) ||
       (crc32_fast(0xffffffffu,input,h[6])^0xffffffffu)!=h[7])goto done;
    for(unsigned i=0;i<h[6];i++)wide[i]=input[i];
    if(!xqi_dequantize(wide,h[6],exponent,tensor))goto done;
    *out=tensor;tensor=NULL;okay=1;
done:
    if(f)fclose(f);
    free(input);free(wide);free(tensor);return okay;
}
int main(int argc,char **argv)
{
    static const char *names[]={"board","detector","classifier"};
    const unsigned layers[]={12,60,8};
    xqm_linux device={.fd=-1};FILE *checks=NULL;int rc=2;unsigned fatal_test;
    uint64_t all_jobs=0;
    if(argc!=5 || (strcmp(argv[4],"--mock-v321") && strcmp(argv[4],"--fail-second-ioctl")))return 2;
    fatal_test=!strcmp(argv[4],"--fail-second-ioctl");
    if(!v321_mock_open(&device))return 2;
    checks=fopen(argv[3],"wx");if(!checks)goto done;
    if(fputs("XQ_NATIVE_CHECKS_V1\n",checks)<0)goto done;
    for(unsigned model=0;model<(fatal_test?1u:3u);model++){
        char path[1024];float *input=NULL;xqn_model *network=NULL;xqm_stats stats={0};
        v321_mock_counts counts;unsigned before=records;int success=0;
        v321_mock_reset(fatal_test?2u:0u);memset(&previous,0,sizeof(previous));
        if(!load_input(argv[2],model,&input))goto model_done;
        if(snprintf(path,sizeof(path),"%s/%s.xqm",argv[1],names[model])>=(int)sizeof(path) || !(network=xqn_load(path)))goto model_done;
        xqn_observe(network,observe,checks);
        int okay=xqn_run(network,&device.io,1,input,0,&stats);
        v321_mock_read(&counts);
        if(fatal_test){
            unsigned dims[4];
            if(okay || counts.attempts!=2 || counts.jobs!=1 || counts.errors!=1 || counts.unexpected ||
               records!=before+1 || xqn_output(network,0,dims))goto model_done;
            puts("V321_MOCK_IOCTL_ERROR_FATAL_PASS no_cpu_fallback=1 no_failed_output=1");success=1;
        } else {
            if(!okay || observer_error || records-before!=layers[model] || !counts.jobs || counts.errors || counts.unexpected ||
               counts.jobs!=stats.jobs || counts.cycles!=stats.cycles)goto model_done;
            printf("V321_MOCK_MODEL_PASS model=%s records=%u jobs=%llu cycles=%llu\n",names[model],records-before,
                   (unsigned long long)counts.jobs,(unsigned long long)counts.cycles);
            all_jobs+=counts.jobs;success=1;
        }
model_done:
        free(input);xqn_free(network);if(!success)goto done;
    }
    if(!fatal_test && records!=80)goto done;
    printf("V321_MOCK_GOLDEN_PASS records=%u jobs=%llu hardware_used=0 cpu_graph_fallback=0\n",records,(unsigned long long)all_jobs);rc=0;
done:
    if(checks && fclose(checks))rc=2;
    v321_mock_close(&device);return rc;
}
