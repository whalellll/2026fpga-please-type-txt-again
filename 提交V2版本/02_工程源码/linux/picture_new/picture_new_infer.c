#include "xq_native_graph.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Board192/detector640/classifier32 graph entry point. Parameters and trained
 * weights are supplied through the pinned XQGRPH1 files, never fabricated. */
int main(int argc,char **argv)
{
    const char *names[]={"board","detector","classifier"};
    const unsigned sides[]={192,640,32};
    unsigned model=3,batch=1;int rc=2;xqm_linux device={.fd=-1};
    xqn_model *graph=NULL;float *input=NULL;FILE *f=NULL;xqm_stats stats={0};
    if(argc<5 || argc>6){fputs("usage: picture-new-infer board|detector|classifier graph.xqm input.f32 output.f32 [batch]\n",stderr);return 2;}
    for(unsigned i=0;i<3;i++)if(!strcmp(argv[1],names[i]))model=i;
    if(argc==6){char *end;unsigned long n=strtoul(argv[5],&end,10);if(*end || n<1 || n>256)return 2;batch=(unsigned)n;}
    if(model>2 || (model!=2 && batch!=1))return 2;
    size_t count=(size_t)batch*3*sides[model]*sides[model];
    input=malloc(count*sizeof(float));if(!input)goto done;
    /* xqn_run derives input dimensions from the graph's kind. Check that
     * kind against the allocated CLI input before loading/running it. */
    {
        unsigned char header[16];
        f=fopen(argv[2],"rb");
        if(!f || fread(header,1,sizeof(header),f)!=sizeof(header) ||
           memcmp(header,"XQGRPH1\0",8) || header[12]!=model ||
           header[13] || header[14] || header[15]){
            fputs("PICTURE_NEW_MODEL_REQUIRED_OR_INVALID\n",stderr);goto done;
        }
        fclose(f);f=NULL;
    }
    graph=xqn_load(argv[2]);if(!graph){fputs("PICTURE_NEW_MODEL_REQUIRED_OR_INVALID\n",stderr);goto done;}
    f=fopen(argv[3],"rb");if(!f || fread(input,sizeof(float),count,f)!=count || fgetc(f)!=EOF)goto done;
    fclose(f);f=NULL;
    if(!xqm_linux_open(&device)){fputs("PICTURE_NEW_VISION32_REQUIRED no_fallback=1\n",stderr);goto done;}
    if(!xqn_run(graph,&device.io,batch,input,0,&stats))goto done;
    f=fopen(argv[4],"wb");if(!f)goto done;
    for(unsigned i=0;i<3;i++){
        unsigned dims[4];const float *out=xqn_output(graph,i,dims);if(!out)break;
        size_t n=(size_t)dims[0]*dims[1]*dims[2]*dims[3];
        if(fwrite(dims,4,4,f)!=4 || fwrite(out,sizeof(float),n,f)!=n)goto done;
    }
    if(fclose(f)){f=NULL;goto done;}f=NULL;
    printf("PICTURE_NEW_GRAPH_COMPLETE model=%s batch=%u backend=vision32 jobs=%llu cycles=%llu no_fallback=1\n",names[model],batch,(unsigned long long)stats.jobs,(unsigned long long)stats.cycles);rc=0;
done:
    if(f)fclose(f);
    free(input);xqn_free(graph);xqm_linux_close(&device);return rc;
}
