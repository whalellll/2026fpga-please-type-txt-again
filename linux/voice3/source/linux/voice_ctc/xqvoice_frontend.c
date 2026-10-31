#include "xqvoice_frontend.h"
#include "xqvoice_tables.h"
#ifndef XQV_HOP_SAMPLES
#define XQV_HOP_SAMPLES 160u
#endif
#include "xqvoice_profile.h"
#include <stdlib.h>
#include <string.h>

static const uint16_t window_bitrev[400]={
    0,256,128,384,64,320,192,448,32,288,160,416,96,352,224,480,
    16,272,144,400,80,336,208,464,48,304,176,432,112,368,240,496,
    8,264,136,392,72,328,200,456,40,296,168,424,104,360,232,488,
    24,280,152,408,88,344,216,472,56,312,184,440,120,376,248,504,
    4,260,132,388,68,324,196,452,36,292,164,420,100,356,228,484,
    20,276,148,404,84,340,212,468,52,308,180,436,116,372,244,500,
    12,268,140,396,76,332,204,460,44,300,172,428,108,364,236,492,
    28,284,156,412,92,348,220,476,60,316,188,444,124,380,252,508,
    2,258,130,386,66,322,194,450,34,290,162,418,98,354,226,482,
    18,274,146,402,82,338,210,466,50,306,178,434,114,370,242,498,
    10,266,138,394,74,330,202,458,42,298,170,426,106,362,234,490,
    26,282,154,410,90,346,218,474,58,314,186,442,122,378,250,506,
    6,262,134,390,70,326,198,454,38,294,166,422,102,358,230,486,
    22,278,150,406,86,342,214,470,54,310,182,438,118,374,246,502,
    14,270,142,398,78,334,206,462,46,302,174,430,110,366,238,494,
    30,286,158,414,94,350,222,478,62,318,190,446,126,382,254,510,
    1,257,129,385,65,321,193,449,33,289,161,417,97,353,225,481,
    17,273,145,401,81,337,209,465,49,305,177,433,113,369,241,497,
    9,265,137,393,73,329,201,457,41,297,169,425,105,361,233,489,
    25,281,153,409,89,345,217,473,57,313,185,441,121,377,249,505,
    5,261,133,389,69,325,197,453,37,293,165,421,101,357,229,485,
    21,277,149,405,85,341,213,469,53,309,181,437,117,373,245,501,
    13,269,141,397,77,333,205,461,45,301,173,429,109,365,237,493,
    29,285,157,413,93,349,221,477,61,317,189,445,125,381,253,509,
    3,259,131,387,67,323,195,451,35,291,163,419,99,355,227,483,
};
static int64_t round_shift(int64_t x,unsigned shift) {
    int64_t magnitude=x<0 ? -x : x;
    int64_t result=(magnitude+(INT64_C(1)<<(shift-1u)))>>shift;
    return x<0 ? -result : result;
}
static int32_t fft_round_q15(int64_t x) {
    /* GCC/RV32 arithmetic right shift. Ties remain away from zero, including
       negative ties. FFT products cannot approach int64 limits. */
    return (int32_t)((x+16384-(x<0))>>15);
}
static unsigned highest_bit32(uint32_t x) {
    unsigned bit=0;
    if(x>>16u){x>>=16u;bit+=16u;}
    if(x>>8u){x>>=8u;bit+=8u;}
    if(x>>4u){x>>=4u;bit+=4u;}
    if(x>>2u){x>>=2u;bit+=2u;}
    return bit+(x>>1u);
}
static int32_t window_q15(int16_t sample,uint16_t coefficient) {
    /* int16*uint16 and this rounding bias both fit signed32. */
    int32_t product=(int32_t)sample*(int32_t)coefficient;
    return (product+16384-(product<0))>>15;
}
static int32_t log_energy(uint64_t e) {
    unsigned bit,index,rem;uint64_t m;uint32_t high;
    int64_t log;
    /* Energy is FFT-power(Q30) times Mel(Q15), hence Q45. */
    if(e<=3518u)return XQV_LOG_FLOOR_Q20;
    high=(uint32_t)(e>>32);
    bit=high?32u+highest_bit32(high):highest_bit32((uint32_t)e);
    m=bit>=24u ? e>>(bit-24u) : e<<(24u-bit);
    m-=UINT64_C(1)<<24;
    index=(unsigned)(m>>16);rem=(unsigned)(m&65535u);
    log=((int64_t)bit-45)*XQV_LN2_Q20+xq_ln_q20[index];
    log+=((int64_t)(xq_ln_q20[index+1u]-xq_ln_q20[index])*rem+32768)>>16;
    return log<XQV_LOG_FLOOR_Q20 ? XQV_LOG_FLOOR_Q20 : (int32_t)log;
}
int xqvoice_frontend(const int16_t *pcm,size_t samples,int8_t *output,size_t capacity,unsigned *frames) {
    int32_t real[512],imag[512];uint64_t power[257];
    unsigned count,f,i,j,span;
    if(!pcm || !output || !frames || samples<400u || samples>64240u)return -1;
    count=(unsigned)((samples-400u)/XQV_HOP_SAMPLES+1u);
    if(count>400u || capacity<(size_t)count*40u)return -2;
    for(f=0;f<count;f++) {
        uint64_t stamp=xqvp_now();
        memset(real,0,sizeof(real));memset(imag,0,sizeof(imag));
        for(i=0;i<400u;i++)real[window_bitrev[i]]=window_q15(pcm[f*XQV_HOP_SAMPLES+i],xq_window[i]);
        xqvp_add(XQVP_WINDOW,xqvp_now()-stamp);stamp=xqvp_now();
        /* First two stages are exact real-input operations. Imag starts zero. */
        for(i=0;i<512u;i+=2u) {
            int32_t a=real[i],b=real[i+1u];real[i]=a+b;real[i+1u]=a-b;
        }
        for(i=0;i<512u;i+=4u) {
            int32_t a=real[i],b=real[i+2u],quarter=real[i+3u];
            real[i]=a+b;real[i+2u]=a-b;
            real[i+3u]=real[i+1u];imag[i+1u]=-quarter;imag[i+3u]=quarter;
        }
        /* Each independent sub-FFT has real input. Its conjugate pairs
           remain exact under sign-symmetric rounding and symmetric Q15 tables.
           Compute one member per pair; derive its mate without new rounding. */
        /* Fixed span8 twiddle is cos(pi/4)=-sin(pi/4)=23170 Q15.
           Inputs here are at most four windowed int16 samples per component,
           so br+bi and bi-br fit signed32. Factor BEFORE the single rounding,
           preserving every bit while using two products instead of four. */
        for(i=0;i<512u;i+=8u) {
            int32_t a0=real[i],b0=real[i+4u],q=real[i+2u],oq=real[i+6u];
            int32_t ar=real[i+1u],ai=imag[i+1u],br=real[i+5u],bi=imag[i+5u];
            int32_t r=fft_round_q15((int64_t)(br+bi)*xq_cos[64]);
            int32_t v=fft_round_q15((int64_t)(bi-br)*xq_cos[64]);
            int32_t sr=ar+r,si=ai+v,dr=ar-r,di=ai-v;
            real[i]=a0+b0;real[i+4u]=a0-b0;imag[i]=imag[i+4u]=0;
            real[i+2u]=real[i+6u]=q;imag[i+2u]=-oq;imag[i+6u]=oq;
            real[i+1u]=real[i+7u]=sr;imag[i+1u]=si;imag[i+7u]=-si;
            real[i+5u]=real[i+3u]=dr;imag[i+5u]=di;imag[i+3u]=-di;
        }
        for(span=16u;span<512u;span<<=1) {
            unsigned half=span/2u,quarter=span/4u,step=512u/span,base;
            for(base=0;base<512u;base+=span) {
                unsigned q=base+quarter,b=q+half;
                int32_t a0=real[base],b0=real[base+half];
                int32_t nyquist=real[q],odd_nyquist=real[b];
                real[base]=a0+b0;real[base+half]=a0-b0;
                imag[base]=imag[base+half]=0;
                real[q]=real[b]=nyquist;imag[q]=-odd_nyquist;imag[b]=odd_nyquist;
                for(j=1u;j<quarter;j++) {
                    unsigned a=base+j,z=a+half,mirror_lo=base+half-j,mirror_hi=base+span-j;
                    int32_t c=xq_cos[j*step],s=xq_sin[j*step];
                    int32_t ar=real[a],ai=imag[a],br=real[z],bi=imag[z];
                    int32_t r=fft_round_q15((int64_t)br*c-(int64_t)bi*s);
                    int32_t v=fft_round_q15((int64_t)br*s+(int64_t)bi*c);
                    int32_t sr=ar+r,si=ai+v,dr=ar-r,di=ai-v;
                    real[a]=real[mirror_hi]=sr;imag[a]=si;imag[mirror_hi]=-si;
                    real[z]=real[mirror_lo]=dr;imag[z]=di;imag[mirror_lo]=-di;
                }
            }
        }
        /* Final stage: only bins0..256 are consumers. For j=1..127,
           X[256-j]=conj(E[j]-W[j]*O[j]); bins257..511 remain unused. */
        {
            int32_t a0=real[0],b0=real[256],q=real[128],oq=real[384];
            real[0]=a0+b0;real[256]=a0-b0;imag[0]=imag[256]=0;
            real[128]=q;imag[128]=-oq;
        }
        for(j=1u;j<128u;j++) {
            int32_t ar=real[j],ai=imag[j],br=real[j+256u],bi=imag[j+256u];
            int32_t c=xq_cos[j],s=xq_sin[j];
            int32_t r=fft_round_q15((int64_t)br*c-(int64_t)bi*s);
            int32_t v=fft_round_q15((int64_t)br*s+(int64_t)bi*c);
            real[j]=ar+r;imag[j]=ai+v;real[256u-j]=ar-r;imag[256u-j]=v-ai;
        }
        xqvp_add(XQVP_FFT,xqvp_now()-stamp);stamp=xqvp_now();
        for(i=0;i<257u;i++)power[i]=(uint64_t)((int64_t)real[i]*real[i]+(int64_t)imag[i]*imag[i]);
        xqvp_add(XQVP_POWER,xqvp_now()-stamp);stamp=xqvp_now();
        for(i=0;i<40u;i++) {
            uint64_t energy=0;int64_t q;int32_t mel;
            for(j=xq_mel_start[i];j<xq_mel_end[i];j++)energy+=power[j]*xq_mel[i*257u+j];
            mel=log_energy(energy);
            q=round_shift(((int64_t)mel-xq_mean_q20[i])*xq_norm_q24[i],44);
            if(q>127)q=127;
            if(q<-127)q=-127;
            output[f*40u+i]=(int8_t)q;
        }
        xqvp_add(XQVP_MEL_QUANT,xqvp_now()-stamp);
    }
    *frames=count;return 0;
}
static uint32_t u32(const uint8_t *p) {return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static uint16_t u16(const uint8_t *p) {return (uint16_t)((unsigned)p[0]|((unsigned)p[1]<<8));}
int xqvoice_wav_features(const uint8_t *wav,size_t bytes,uint8_t **input,size_t *input_bytes) {
    size_t pos=12,n=0,i;const uint8_t *data=NULL;int format_ok=0,rc;unsigned frames;
    int16_t *pcm;uint8_t *out;
    if(bytes<12 || memcmp(wav,"RIFF",4) || memcmp(wav+8,"WAVE",4))return -10;
    while(pos+8<=bytes) {
        uint32_t length=u32(wav+pos+4);const uint8_t *chunk=wav+pos+8;
        if(length>bytes-pos-8)return -11;
        if(!memcmp(wav+pos,"fmt ",4)) {
            if(length<16 || u16(chunk)!=1 || u16(chunk+2)!=1 || u32(chunk+4)!=16000 || u16(chunk+12)!=2 || u16(chunk+14)!=16)return -12;
            format_ok=1;
        } else if(!memcmp(wav+pos,"data",4)){data=chunk;n=length;}
        pos+=8u+length+(length&1u);
    }
    if(!format_ok || !data || n%2 || n/2<400 || n/2>64240)return -13;
    pcm=(int16_t*)malloc(n);out=(uint8_t*)malloc(4u+400u*40u);
    if(!pcm || !out){free(pcm);free(out);return -14;}
    for(i=0;i<n/2;i++){unsigned v=u16(data+i*2);pcm[i]=(int16_t)(v<32768u ? (int)v : (int)v-65536);}
    rc=xqvoice_frontend(pcm,n/2,(int8_t*)(out+4),400u*40u,&frames);
    free(pcm);
    if(rc){free(out);return rc;}
    out[0]=(uint8_t)frames;out[1]=(uint8_t)(frames>>8);out[2]=(uint8_t)(frames>>16);out[3]=(uint8_t)(frames>>24);
    *input=out;*input_bytes=4u+frames*40u;return 0;
}
