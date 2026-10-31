#define _POSIX_C_SOURCE 200809L
#include "xq_native_graph.h"
#include "graph_profile.h"
#include "xq_sha256.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static uint64_t cpu_ns(void)
{
    struct timespec t;assert(!clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t));
    return (uint64_t)t.tv_sec*1000000000u+(unsigned)t.tv_nsec;
}
int main(int argc,char **argv)
{
    assert(argc==2);
    xqm_linux device={.fd=-1};assert(xqm_linux_open(&device));
    const char *names[]={"board","classifier"};
    for(unsigned kind=0;kind<2;kind++){
        unsigned side=kind?32:192,batch=kind?32:1;
        size_t count=(size_t)batch*3*side*side;
        uint8_t *rgb=malloc(count);float *input=malloc(count*sizeof(float));assert(rgb&&input);
        for(size_t i=0;i<count;i++)rgb[i]=(uint8_t)(i*73u+(i/257u)*19u);
        uint64_t before=cpu_ns();
        float unit[256];for(unsigned i=0;i<256;i++)unit[i]=(float)i/255.f;
        for(size_t i=0;i<count;i++)input[i]=unit[rgb[i]];
        uint64_t prepare=cpu_ns()-before;
        char path[1024];assert(snprintf(path,sizeof(path),"%s/%s.xqm",argv[1],names[kind])<(int)sizeof(path));
        xqn_model *m=xqn_load(path);assert(m);
        xqm_stats st;assert(xqn_run(m,&device.io,batch,input,0,&st));
        xqg_profile p;xqg_profile_read(&p);assert(!p.clock_failures);
        printf("AUX_PREPARE name=%s batch=%u values=%zu normalize_cpu_ns=%llu jobs=%llu\n",names[kind],batch,count,
               (unsigned long long)prepare,(unsigned long long)st.jobs);
        for(unsigned phase=0;phase<XQG_PHASES;phase++)
            printf("AUX_PHASE name=%s phase=%u cpu_ns=%llu calls=%llu values=%llu\n",names[kind],phase,
                   (unsigned long long)p.cpu[phase],(unsigned long long)p.calls[phase],(unsigned long long)p.values[phase]);
        for(unsigned i=0;i<3;i++){
            unsigned dims[4];const float *data=xqn_output(m,i,dims);if(!data)break;
            char digest[65];xq_sha256_hex(data,(size_t)dims[0]*dims[1]*dims[2]*dims[3]*4,digest);
            printf("AUX_OUTPUT name=%s head=%u sha256=%s\n",names[kind],i,digest);
        }
        xqn_free(m);free(input);free(rgb);
    }
    xqm_linux_close(&device);puts("AUX_FROZEN_PROFILE_COMPLETE_NOT_BOARD");return 0;
}
