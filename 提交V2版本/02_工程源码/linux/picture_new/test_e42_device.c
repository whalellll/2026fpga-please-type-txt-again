/* Explicit synthetic device acceptance; never linked into the product.
 * Run raw2 first, then exact, then ownership with the matching real kernel.
 * Independent scalar dot/round reference is an oracle, never a fallback. */
#include "xq_mac.h"
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void xqv_parameters_begin(const xqm_transport *,struct pango_vision32_job *);
int xqv_run(const xqm_transport *,struct pango_vision32_job *);
static int require(int okay,const char *message)
{if(!okay)fprintf(stderr,"E42_DEVICE_FAIL %s no_fallback=1\n",message);return okay;}
static const int32_t biases[9]={0,1,-1,3,-3,-5,131072,-131072,0};
static const unsigned shifts[9]={0,1,1,1,1,1,0,0,3};
static void fill(xqm_linux *d,struct pango_vision32_job *j,unsigned seed,unsigned mode)
{
    memset(d->io.shadow,0xa5,d->io.bytes);
    *j=(struct pango_vision32_job){.abi_version=1,.input=0x1000,.weights=0x20000,
        .output=0x90000,.params=0x80000,.lut=0x60000,.width=3,.height=3,.cin=3,.cout=9,
        .kernel=3,.stride=1,.padding=1,.flags=mode,.timeout_cycles=4950000,.timeout_us=1000000};
    int8_t *x=(int8_t *)d->io.shadow+j->input,*w=(int8_t *)d->io.shadow+j->weights;
    for(unsigned p=0;p<9;p++){
        for(unsigned c=0;c<3;c++)x[p*4+c]=(int8_t)((int)((p*7+c*11+seed*13)%31)-15);
        x[p*4+3]=127; /* Poison HWC4's padding lane. */
    }
    for(unsigned o=0;o<16;o++)for(unsigned k=0;k<27;k++)
        w[((o/8)*27+k)*8+o%8]=(int8_t)(o>=9?-7:(o==0 || o==8)?(int)((k*3+o+seed)%9)-4:0);
    for(unsigned o=0;o<16;o++){
        int32_t param[3]={o<9?biases[o]:0,1,o<9?(int32_t)shifts[o]:0};
        memcpy(d->io.shadow+j->params+o*12,param,12);
    }
    for(unsigned i=0;i<65536;i++)((int8_t *)d->io.shadow+j->lut)[i]=(int8_t)((int)((i*37+seed*11)%256)-128);
    if(mode!=2)xqv_parameters_begin(&d->io,j);
}
static int32_t dot(const xqm_linux *d,const struct pango_vision32_job *j,unsigned y,unsigned x,unsigned o)
{
    const int8_t *input=(const int8_t *)d->io.shadow+j->input,*weights=(const int8_t *)d->io.shadow+j->weights;
    int64_t sum=0;
    for(unsigned ky=0;ky<3;ky++)for(unsigned kx=0;kx<3;kx++){
        int yy=(int)y+(int)ky-1,xx=(int)x+(int)kx-1;
        if(yy<0 || yy>=3 || xx<0 || xx>=3)continue;
        for(unsigned c=0;c<3;c++)sum+=(int32_t)input[(yy*3+xx)*4+c]*weights[((o/8)*27+(ky*3+kx)*3+c)*8+o%8];
    }
    if(sum<INT32_MIN || sum>INT32_MAX)abort();
    return (int32_t)sum;
}
static int16_t rounded(int64_t n,unsigned shift)
{
    uint64_t mag=n<0?(uint64_t)-n:(uint64_t)n,q=mag>>shift;
    if(shift){uint64_t rem=mag-(q<<shift),half=UINT64_C(1)<<(shift-1);q+=rem>half || (rem==half && (q&1));}
    int64_t value=n<0?-(int64_t)q:(int64_t)q;
    return value>32767?32767:value< -32768?-32768:(int16_t)value;
}
static int execute(xqm_linux *d,struct pango_vision32_job *j,int cache)
{
    unsigned sizes[5];
    if(!require(pango_vision32_sizes(j,d->io.bytes,sizes),"job validation"))return 0;
    memset(d->io.shadow+j->output,0xa5,sizes[2]+4);
    if(!require(xqv_run(&d->io,j),"ioctl/DONE/error"))return 0;
    if(cache>=0 && !require(j->frame_id==(unsigned)cache,"physical parameter lease"))return 0;
    for(unsigned y=0;y<3;y++)for(unsigned x=0;x<3;x++)for(unsigned o=0;o<9;o++){
        unsigned at=(y*3+x)*9+o;
        int32_t expected=dot(d,j,y,x,o),actual;
        if(j->flags==2)memcpy(&actual,d->io.shadow+j->output+at*4,4);
        else{
            int16_t v=rounded((int64_t)expected+biases[o],shifts[o]);
            expected=j->flags==5?((int8_t *)d->io.shadow+j->lut)[(int)v+32768]:v;
            memcpy(&v,d->io.shadow+j->output+at*2,2);actual=v;
        }
        if(!require(actual==expected,"81 complete output values")){
            fprintf(stderr,"index=%u expected=%d actual=%d mode=%u\n",at,expected,actual,j->flags);return 0;
        }
    }
    for(unsigned i=0;i<4;i++)if(!require(d->io.shadow[j->output+sizes[2]+i]==0xa5,"copyout tail sentinel"))return 0;
    printf("E42_VECTOR_PASS mode=%u values=81 hit=%u cycles=%u\n",j->flags,j->frame_id,j->cycles);
    return 1;
}
int main(int argc,char **argv)
{
    if(argc!=2 || (strcmp(argv[1],"--raw2") && strcmp(argv[1],"--exact") && strcmp(argv[1],"--ownership")))return 2;
    xqm_linux a={.fd=-1},b={.fd=-1};struct pango_vision32_job ja,jb;int code=1;
    if(!require(xqm_linux_open(&a),"matching driver"))goto done;
    printf("E42_DEVICE_FEATURES=%08x\n",a.features);
    if(!strcmp(argv[1],"--raw2")){
        fill(&a,&ja,1,2);if(!execute(&a,&ja,-1))goto done;
        puts("E42_RAW2_HALO_CIN3_COUT9_FULL_OUTPUT_PASS");
    }else{
        unsigned required=PANGO_MAC_FEATURE_VISION32_EXACT|PANGO_MAC_FEATURE_VISION32_REUSE;
        if(!require((a.features&required)==required,"exact and reuse capability"))goto done;
        if(!strcmp(argv[1],"--exact")){
            fill(&a,&ja,1,4);if(!execute(&a,&ja,0))goto done;
            fill(&a,&ja,1,5);if(!execute(&a,&ja,0))goto done;
            ((int8_t *)a.io.shadow+ja.input)[0]=-12;
            if(!execute(&a,&ja,1))goto done;
            puts("E42_EXACT4_5_TIES_EVEN_S16_SATURATION_SIGNED_LUT_AND_REUSE_PASS");
        }else{
            if(!require(xqm_linux_open(&b),"second independent fd"))goto done;
            fill(&a,&ja,1,5);fill(&b,&jb,2,5);
            if(!execute(&a,&ja,0) || !execute(&b,&jb,0) || !execute(&a,&ja,0))goto done;
            puts("E42_TWO_FD_IDENTICAL_GENERATION_DIFFERENT_PARAMS_RESTORED_PASS");
        }
    }
    code=0;
done:xqm_linux_close(&b);xqm_linux_close(&a);return code;
}
