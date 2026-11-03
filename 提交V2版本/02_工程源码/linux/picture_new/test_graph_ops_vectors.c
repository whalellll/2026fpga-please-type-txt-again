#include "graph_ops.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void read_exact(FILE *f,void *p,size_t bytes) { assert(fread(p,1,bytes,f)==bytes); }
int main(int argc,char **argv)
{
    assert(argc==2);FILE *f=fopen(argv[1],"rb");assert(f);
    char magic[8];uint32_t header[2];read_exact(f,magic,8);read_exact(f,header,8);
    assert(!memcmp(magic,"XQOPV1\0\0",8) && header[0]<=241 && header[1]<=1000);
    xqg_s16_lut tables[241]={0};int16_t *owned[241]={0};
    for(unsigned i=0;i<header[0];i++){
        int32_t e[2];read_exact(f,e,8);owned[i]=malloc(65536*2);assert(owned[i]);
        read_exact(f,owned[i],65536*2);tables[i]=(xqg_s16_lut){owned[i],65536,e[0],e[1]};
    }
    unsigned tested[13]={0},failed[13]={0},all_failed=0;
    for(unsigned index=0;index<header[1];index++){
        uint32_t h[9];read_exact(f,h,sizeof(h));
        unsigned type=h[0],nin=h[1];assert(type>=3 && type<=11 && nin>=1 && nin<=4 && h[2] && h[2]<=16777216);
        xqg_s16_view in[4]={0},result;int16_t *data[4]={0};
        for(unsigned i=0;i<nin;i++){
            uint32_t s[6];read_exact(f,s,sizeof(s));assert(s[5] && s[5]<=16777216);
            data[i]=malloc((size_t)s[5]*2);assert(data[i]);read_exact(f,data[i],(size_t)s[5]*2);
            in[i]=(xqg_s16_view){data[i],s[5],s[0],s[1],s[2],s[3],(int32_t)s[4]};
        }
        int16_t *expected=malloc((size_t)h[2]*2),*output=malloc((size_t)h[2]*2);assert(expected && output);
        memset(output,0,(size_t)h[2]*2);
        read_exact(f,expected,(size_t)h[2]*2);
        const xqg_s16_lut *lut=NULL;
        if(h[8]!=UINT32_MAX){assert(h[8]<header[0]);lut=tables+h[8];}
        int okay=xqg_op_run(type,in,nin,output,h[2],lut,&result);
        size_t difference=0;while(difference<h[2] && output[difference]==expected[difference])difference++;
        if(!okay || result.count!=h[2] || result.exponent!=(int32_t)h[3] || result.batch!=h[4] ||
           result.channels!=h[5] || result.height!=h[6] || result.width!=h[7] || difference<h[2]){
            failed[type]++;all_failed++;
            printf("S16_OP_VECTOR_FAIL index=%u type=%u at=%zu expected=%d actual=%d call_ok=%d\n",index,type,difference,
                difference<h[2]?expected[difference]:0,difference<h[2]?output[difference]:0,okay);
        }
        tested[type]++;
        for(unsigned i=0;i<nin;i++)free(data[i]);
        free(expected);free(output);
    }
    assert(fgetc(f)==EOF && !ferror(f));fclose(f);
    for(unsigned i=0;i<header[0];i++)free(owned[i]);
    for(unsigned type=3;type<=11;type++)if(tested[type])
        printf("S16_OP_RESULT type=%u tested=%u failed=%u\n",type,tested[type],failed[type]);
    return all_failed?1:0;
}
