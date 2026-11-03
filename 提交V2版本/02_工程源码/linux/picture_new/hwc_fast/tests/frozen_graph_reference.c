/* Full-output oracle using the unchanged r14 graph and direct CPU dot path.
 * Synthetic or explicitly authorized private frames only; no dataset scan. */
#include "xq_native_graph.h"
#include <stdio.h>
#include <stdlib.h>

int main(int argc,char **argv)
{
    if(argc!=4)return 2;
    xqn_model *model=xqn_load(argv[1]);
    if(!model || xqn_input_side(model)!=640){xqn_free(model);return 2;}
    size_t count=3u*640u*640u;
    float *input=malloc(count*sizeof(*input));
    FILE *file=fopen(argv[2],"rb");
    int okay=input && file && fread(input,sizeof(*input),count,file)==count &&
             fgetc(file)==EOF && !ferror(file);
    if(file && fclose(file))okay=0;
    xqm_stats stats={0};
    if(okay)okay=xqn_run(model,NULL,1,input,1,&stats);
    file=okay?fopen(argv[3],"wb"):NULL;
    if(!file)okay=0;
    for(unsigned i=0;okay && i<3;i++){
        unsigned dims[4];const float *output=xqn_output(model,i,dims);
        if(!output){okay=0;break;}
        size_t elements=(size_t)dims[0]*dims[1]*dims[2]*dims[3];
        okay=elements && fwrite(dims,4,4,file)==4 &&
             fwrite(output,4,elements,file)==elements;
    }
    if(file && fclose(file))okay=0;
    free(input);xqn_free(model);
    if(okay)puts("FROZEN_GRAPH_DIRECT_CPU_FULL_OUTPUT_COMPLETE");
    return okay?0:1;
}
