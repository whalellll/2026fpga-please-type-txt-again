#define _POSIX_C_SOURCE 200809L
/* CPU integer reference and optional Linux dense MAC device execution. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#if defined(__linux__)
#include <signal.h>
#endif
#include "xqvoice_frontend.h"
#include "xqvoice_decode.h"
#include "xqvoice_mac.h"
#include "xqvoice_capture.h"
#include "xqvoice_tables.h"
#ifndef XQV_HOP_SAMPLES
#define XQV_HOP_SAMPLES 160u
#endif
#include "xqvoice_profile.h"

#define MAX_T 400u
#define MAX_C 40u
#define MAX_N 32u
#define LAYERS 5u
static int backend;
static int32_t final_logits[100u*22u];
static unsigned final_frames;
static uint64_t timestamp_us(void) {
#if defined(__linux__)
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;
    return (uint64_t)t.tv_sec*1000000u+(uint64_t)t.tv_nsec/1000u;
#else
    return (uint64_t)clock()*1000000u/CLOCKS_PER_SEC;
#endif
}

static uint32_t rd32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1]<<8) | ((uint32_t)p[2]<<16) | ((uint32_t)p[3]<<24);
}
static int32_t rs32(const uint8_t *p) {
    uint32_t u=rd32(p);
    return u<=INT32_MAX ? (int32_t)u : (int32_t)((int64_t)u-INT64_C(4294967296));
}
static int s8(uint8_t x) { return x<128u ? (int)x : (int)x-256; }
static int wr32(FILE *f,uint32_t x) {
    uint8_t b[4]={(uint8_t)x,(uint8_t)(x>>8),(uint8_t)(x>>16),(uint8_t)(x>>24)};
    return fwrite(b,1,4,f)==4;
}
static int wr_array(FILE *f,const int32_t *values,size_t count) {
    uint8_t block[1024];size_t start=0;
    while(start<count) {
        size_t n=count-start<256u?count-start:256u,j;
        for(j=0;j<n;j++) {
            uint32_t x=(uint32_t)values[start+j];
            block[j*4u]=(uint8_t)x;block[j*4u+1u]=(uint8_t)(x>>8);
            block[j*4u+2u]=(uint8_t)(x>>16);block[j*4u+3u]=(uint8_t)(x>>24);
        }
        if(fwrite(block,4,n,f)!=n)return 0;
        start+=n;
    }
    return 1;
}
static uint32_t crc32_bytes(const uint8_t *p,size_t n) {
    static const uint32_t table[256]={
        0x00000000u,0x77073096u,0xee0e612cu,0x990951bau,0x076dc419u,0x706af48fu,0xe963a535u,0x9e6495a3u,
        0x0edb8832u,0x79dcb8a4u,0xe0d5e91eu,0x97d2d988u,0x09b64c2bu,0x7eb17cbdu,0xe7b82d07u,0x90bf1d91u,
        0x1db71064u,0x6ab020f2u,0xf3b97148u,0x84be41deu,0x1adad47du,0x6ddde4ebu,0xf4d4b551u,0x83d385c7u,
        0x136c9856u,0x646ba8c0u,0xfd62f97au,0x8a65c9ecu,0x14015c4fu,0x63066cd9u,0xfa0f3d63u,0x8d080df5u,
        0x3b6e20c8u,0x4c69105eu,0xd56041e4u,0xa2677172u,0x3c03e4d1u,0x4b04d447u,0xd20d85fdu,0xa50ab56bu,
        0x35b5a8fau,0x42b2986cu,0xdbbbc9d6u,0xacbcf940u,0x32d86ce3u,0x45df5c75u,0xdcd60dcfu,0xabd13d59u,
        0x26d930acu,0x51de003au,0xc8d75180u,0xbfd06116u,0x21b4f4b5u,0x56b3c423u,0xcfba9599u,0xb8bda50fu,
        0x2802b89eu,0x5f058808u,0xc60cd9b2u,0xb10be924u,0x2f6f7c87u,0x58684c11u,0xc1611dabu,0xb6662d3du,
        0x76dc4190u,0x01db7106u,0x98d220bcu,0xefd5102au,0x71b18589u,0x06b6b51fu,0x9fbfe4a5u,0xe8b8d433u,
        0x7807c9a2u,0x0f00f934u,0x9609a88eu,0xe10e9818u,0x7f6a0dbbu,0x086d3d2du,0x91646c97u,0xe6635c01u,
        0x6b6b51f4u,0x1c6c6162u,0x856530d8u,0xf262004eu,0x6c0695edu,0x1b01a57bu,0x8208f4c1u,0xf50fc457u,
        0x65b0d9c6u,0x12b7e950u,0x8bbeb8eau,0xfcb9887cu,0x62dd1ddfu,0x15da2d49u,0x8cd37cf3u,0xfbd44c65u,
        0x4db26158u,0x3ab551ceu,0xa3bc0074u,0xd4bb30e2u,0x4adfa541u,0x3dd895d7u,0xa4d1c46du,0xd3d6f4fbu,
        0x4369e96au,0x346ed9fcu,0xad678846u,0xda60b8d0u,0x44042d73u,0x33031de5u,0xaa0a4c5fu,0xdd0d7cc9u,
        0x5005713cu,0x270241aau,0xbe0b1010u,0xc90c2086u,0x5768b525u,0x206f85b3u,0xb966d409u,0xce61e49fu,
        0x5edef90eu,0x29d9c998u,0xb0d09822u,0xc7d7a8b4u,0x59b33d17u,0x2eb40d81u,0xb7bd5c3bu,0xc0ba6cadu,
        0xedb88320u,0x9abfb3b6u,0x03b6e20cu,0x74b1d29au,0xead54739u,0x9dd277afu,0x04db2615u,0x73dc1683u,
        0xe3630b12u,0x94643b84u,0x0d6d6a3eu,0x7a6a5aa8u,0xe40ecf0bu,0x9309ff9du,0x0a00ae27u,0x7d079eb1u,
        0xf00f9344u,0x8708a3d2u,0x1e01f268u,0x6906c2feu,0xf762575du,0x806567cbu,0x196c3671u,0x6e6b06e7u,
        0xfed41b76u,0x89d32be0u,0x10da7a5au,0x67dd4accu,0xf9b9df6fu,0x8ebeeff9u,0x17b7be43u,0x60b08ed5u,
        0xd6d6a3e8u,0xa1d1937eu,0x38d8c2c4u,0x4fdff252u,0xd1bb67f1u,0xa6bc5767u,0x3fb506ddu,0x48b2364bu,
        0xd80d2bdau,0xaf0a1b4cu,0x36034af6u,0x41047a60u,0xdf60efc3u,0xa867df55u,0x316e8eefu,0x4669be79u,
        0xcb61b38cu,0xbc66831au,0x256fd2a0u,0x5268e236u,0xcc0c7795u,0xbb0b4703u,0x220216b9u,0x5505262fu,
        0xc5ba3bbeu,0xb2bd0b28u,0x2bb45a92u,0x5cb36a04u,0xc2d7ffa7u,0xb5d0cf31u,0x2cd99e8bu,0x5bdeae1du,
        0x9b64c2b0u,0xec63f226u,0x756aa39cu,0x026d930au,0x9c0906a9u,0xeb0e363fu,0x72076785u,0x05005713u,
        0x95bf4a82u,0xe2b87a14u,0x7bb12baeu,0x0cb61b38u,0x92d28e9bu,0xe5d5be0du,0x7cdcefb7u,0x0bdbdf21u,
        0x86d3d2d4u,0xf1d4e242u,0x68ddb3f8u,0x1fda836eu,0x81be16cdu,0xf6b9265bu,0x6fb077e1u,0x18b74777u,
        0x88085ae6u,0xff0f6a70u,0x66063bcau,0x11010b5cu,0x8f659effu,0xf862ae69u,0x616bffd3u,0x166ccf45u,
        0xa00ae278u,0xd70dd2eeu,0x4e048354u,0x3903b3c2u,0xa7672661u,0xd06016f7u,0x4969474du,0x3e6e77dbu,
        0xaed16a4au,0xd9d65adcu,0x40df0b66u,0x37d83bf0u,0xa9bcae53u,0xdebb9ec5u,0x47b2cf7fu,0x30b5ffe9u,
        0xbdbdf21cu,0xcabac28au,0x53b39330u,0x24b4a3a6u,0xbad03605u,0xcdd70693u,0x54de5729u,0x23d967bfu,
        0xb3667a2eu,0xc4614ab8u,0x5d681b02u,0x2a6f2b94u,0xb40bbe37u,0xc30c8ea1u,0x5a05df1bu,0x2d02ef8du,
    };
    uint32_t c=UINT32_MAX;
    size_t i;
    for(i=0;i<n;i++) {
        c=(c>>8)^table[(c^p[i])&255u];
    }
    return ~c;
}
static int32_t requant(int64_t biased,int32_t multiplier,unsigned shift,int32_t lo,int32_t hi) {
    int64_t product=biased*multiplier;
    int64_t mag=product<0 ? -product : product;
    int64_t q=(mag+(INT64_C(1)<<(shift-1u)))>>shift;
    if(product<0)q=-q;
    if(q<lo)q=lo;
    if(q>hi)q=hi;
    return (int32_t)q;
}
static uint8_t *read_file(const char *path,size_t *length) {
    FILE *f=fopen(path,"rb");
    uint8_t *data;long n;
    if(!f)return NULL;
    if(fseek(f,0,SEEK_END)!=0 || (n=ftell(f))<0 || n>1048576 || fseek(f,0,SEEK_SET)!=0) {
        fclose(f);return NULL;
    }
    data=(uint8_t*)malloc((size_t)n+1u);
    if(!data){fclose(f);return NULL;}
    if(fread(data,1,(size_t)n,f)!=(size_t)n){free(data);fclose(f);return NULL;}
    fclose(f);*length=(size_t)n;return data;
}
static int in_range(uint32_t off,size_t bytes,size_t size,uint32_t header) {
    return off>=header && !(off&3u) && off<=size && bytes<=size-off;
}
static const uint8_t *trusted_model;
static size_t trusted_model_size;
static int (*request_cancel)(void *);
static void *request_cancel_context;
static unsigned long model_validation_count;
static int validate_model(const uint8_t *model,size_t size) {
    uint32_t header,layer,cin=40;
    model_validation_count++;
    if(size<384u || memcmp(model,"XQVINT8\0",8)!=0 || rd32(model+8)!=1u ||
       (header=rd32(model+12))!=384u || rd32(model+16)!=5u || rd32(model+20)!=400u ||
       rd32(model+24)!=40u || rd32(model+44)!=size || rd32(model+48)!=8u ||
       crc32_bytes(model+header,size-header)!=rd32(model+28) || rd32(model+28)!=XQV_MODEL_CRC ||
       (rd32(model+52)?rd32(model+52)!=XQV_HOP_SAMPLES:XQV_HOP_SAMPLES!=160u) ||
       (rd32(model+56) && rd32(model+56)!=512u) || (rd32(model+60) && rd32(model+60)!=400u)) return 10;
    for(layer=0;layer<LAYERS;layer++) {
        const uint8_t *d=model+64u+layer*64u;
        uint32_t ci=rd32(d),co=rd32(d+4),k=rd32(d+8),stride=rd32(d+12),dilation=rd32(d+16),pad=rd32(d+20);
        uint32_t raw=rd32(d+32),packed=rd32(d+36),bias=rd32(d+40),mult=rd32(d+44),shift=rd32(d+48),bytes=rd32(d+52),K,n;
        int32_t lo=rs32(d+24),hi=rs32(d+28);
        if(ci!=cin || ci>MAX_C || co<1u || co>MAX_N || k<1u || k>5u || stride<1u || stride>2u || dilation<1u || dilation>4u || pad>8u)return 12;
        K=ci*k;
        if(K>256u || K%4u || bytes!=((K+3u)/4u)*((co+31u)/32u)*128u || bytes>8192u)return 13;
        if(!in_range(raw,co*K,size,header) || !in_range(packed,bytes,size,header) || !in_range(bias,co*4u,size,header) || !in_range(mult,co*4u,size,header) || !in_range(shift,co*4u,size,header))return 14;
        if((layer<4 && (lo!=0 || hi!=127)) || (layer==4 && (lo!=-32768 || hi!=32767 || co!=22)))return 15;
        for(n=0;n<co;n++)if(rs32(model+mult+n*4u)<=0 || rs32(model+mult+n*4u)>1073741824 || rs32(model+shift+n*4u)<1 || rs32(model+shift+n*4u)>60)return 18;
        cin=co;
    }
    return 0;
}
static int run(const uint8_t *model,size_t size,const uint8_t *input,size_t input_size,FILE *trace) {
    uint8_t current[MAX_T*MAX_C];
    int32_t accum[MAX_T*MAX_N],quant[MAX_T*MAX_N];
    uint8_t input_stage[16u*64u*8u];
    uint32_t header,t,cin=40u,layer;
    uint64_t stamp=xqvp_now();
    if(model!=trusted_model || size!=trusted_model_size) {
        int checked=validate_model(model,size);if(checked)return checked;
    }
    header=rd32(model+12);
    if(input_size<4u || (t=rd32(input))<1u || t>MAX_T || input_size!=4u+t*40u)return 11;
    memcpy(current,input+4,t*40u);
    xqvp_add(XQVP_MODEL_CHECK,xqvp_now()-stamp);
    for(layer=0;layer<LAYERS;layer++) {
        if(request_cancel && request_cancel(request_cancel_context))return 26;
        uint64_t layer_started=xqvp_now();
        const uint8_t *desc=model+64u+layer*64u;
        uint32_t ci=rd32(desc),co=rd32(desc+4),k=rd32(desc+8),stride=rd32(desc+12),dilation=rd32(desc+16),pad=rd32(desc+20);
        int32_t lo=rs32(desc+24),hi=rs32(desc+28);
        uint32_t raw=rd32(desc+32),packed=rd32(desc+36),bias=rd32(desc+40),mult=rd32(desc+44),shift=rd32(desc+48),packed_bytes=rd32(desc+52);
        uint32_t K,ci_tiles,rows,out_t,start,p,n,j;
        int32_t biases[MAX_N],multipliers[MAX_N];unsigned shifts[MAX_N];
        int64_t numerator;
        if(ci!=cin || ci>MAX_C || co<1u || co>MAX_N || k<1u || k>5u || stride<1u || stride>2u || dilation<1u || dilation>4u || pad>8u)return 12;
        K=ci*k;ci_tiles=(K+3u)/4u;rows=ci_tiles*((co+31u)/32u);
        if(K>256u || K%4u || rows>64u || packed_bytes!=rows*128u)return 13;
        if(!in_range(raw,co*K,size,header) || !in_range(packed,packed_bytes,size,header) ||
           !in_range(bias,co*4u,size,header) || !in_range(mult,co*4u,size,header) || !in_range(shift,co*4u,size,header))return 14;
        if((layer<4u && (lo!=0 || hi!=127)) || (layer==4u && (lo!=-32768 || hi!=32767)))return 15;
        numerator=(int64_t)t+2u*pad-dilation*(k-1u)-1;
        if(numerator<0)return 16;
        out_t=(uint32_t)(numerator/stride+1);
        if(out_t<1u || out_t>MAX_T)return 17;
        for(n=0;n<co;n++) {
            int32_t m=rs32(model+mult+n*4u),sh=rs32(model+shift+n*4u);
            if(m<=0 || m>1073741824 || sh<1 || sh>60)return 18;
            biases[n]=rs32(model+bias+n*4u);multipliers[n]=m;shifts[n]=(unsigned)sh;
        }
        if(backend && xqvoice_mac_prepare_layer(model+packed,K,co,(out_t+15u)/16u))return 22;
        /* pixels<=16; four input features occupy eight DMA bytes. */
        for(start=0;start<out_t;start+=16u) {
            if(request_cancel && request_cancel(request_cancel_context))return 26;
            stamp=xqvp_now();
            uint32_t pixels=out_t-start<16u ? out_t-start : 16u;
            memset(input_stage,0,pixels*ci_tiles*8u);
            for(p=0;p<pixels;p++) {
                uint32_t kernel,channel;
                /* Validated bounds: start+p<400, stride<=2, k<=5,
                   dilation<=4 and pad<=8, so signed32 source is safe. */
                int32_t source_base=(int32_t)((start+p)*stride)-(int32_t)pad;
                size_t base=(size_t)p*ci_tiles*8u;
                for(kernel=0;kernel<k;kernel++) {
                    int32_t source=source_base+(int32_t)(kernel*dilation);
                    if(source>=0 && (uint32_t)source<t) {
                        const uint8_t *row=current+(size_t)(uint32_t)source*ci;
                        /* (j/4)*8+(j%4)*2 == j*2; high bytes stay zero. */
                        size_t slot=base+(size_t)kernel*ci*2u;
                        for(channel=0;channel<ci;channel++)input_stage[slot+channel*2u]=row[channel];
                    }
                }
            }
            xqvp_add(XQVP_PACK,xqvp_now()-stamp);stamp=xqvp_now();
            if(backend && xqvoice_mac_dense(input_stage,model+packed,pixels,K,co,accum+start*co))return 22;
            xqvp_add(XQVP_MAC_WAIT,xqvp_now()-stamp);stamp=xqvp_now();
            for(p=0;p<pixels;p++)for(n=0;n<co;n++) {
                int32_t dense=0,emulated=0;
                if(backend!=1)for(j=0;j<K;j++) {
                    uint32_t kernel=j/ci,channel=j%ci;
                    int64_t source=(int64_t)(start+p)*stride+(int64_t)kernel*dilation-pad;
                    int x=source>=0 && source<t ? s8(current[(size_t)source*ci+channel]) : 0;
                    size_t inslot=(size_t)p*ci_tiles*8u+(j/4u)*8u+(j%4u)*2u;
                    size_t wslot=(size_t)(n/32u)*ci_tiles*128u+(j/4u)*128u+(((n%32u)/2u)*4u+j%4u)*2u+n%2u;
                    dense+=x*s8(model[raw+n*K+j]);
                    emulated+=s8(input_stage[inslot])*s8(model[packed+wslot]);
                    if(input_stage[inslot+1u]!=0)return 19;
                }
                if(backend==1)dense=accum[(start+p)*co+n];
                else if(dense!=emulated)return 20;
                if(backend==2 && dense!=accum[(start+p)*co+n])return 23;
                accum[(start+p)*co+n]=dense;
                quant[(start+p)*co+n]=requant((int64_t)dense+biases[n],multipliers[n],shifts[n],lo,hi);
            }
            xqvp_add(XQVP_REQUANT,xqvp_now()-stamp);
        }
        stamp=xqvp_now();
        if(trace) {
            if(!wr32(trace,out_t) || !wr32(trace,co))return 21;
            if(!wr_array(trace,accum,out_t*co) || !wr_array(trace,quant,out_t*co))return 21;
        }
        xqvp_add(XQVP_TRACE,xqvp_now()-stamp);
        if(layer<4u) {
            /* All outputs are complete before reusing current; no aliasing. */
            for(j=0;j<out_t*co;j++)current[j]=(uint8_t)quant[j];
        } else {
            if(co!=22u || out_t>100u)return 24;
            memcpy(final_logits,quant,out_t*co*sizeof(int32_t));final_frames=out_t;
        }
        t=out_t;cin=co;
        xqvp_add(XQVP_LAYER0+layer,xqvp_now()-layer_started);
    }
    return 0;
}
static int profile_exit(int code) {xqvp_emit(code);return code;}
static int worker_main(int argc,char **argv);
int main(int argc,char **argv) {
    if(argc>=2 && !strcmp(argv[1],"--worker"))return worker_main(argc,argv);
#if defined(__linux__)
    /* Late stop requests are harmless after capture has closed the microphone. */
    (void)signal(SIGUSR1,SIG_IGN);
#endif
    uint8_t *model,*input;size_t model_size,input_size;
    FILE *trace;int code,opened=0;uint64_t started=timestamp_us(),inferred,decoded_at,finished,stamp;
    xqvoice_stream_metrics stream_metrics={0};uint32_t feature_crc=0;
    xqvp_init();
    if(argc==4 && strcmp(argv[1],"--features")==0) {
        uint8_t *features=NULL;size_t bytes=0;
        input=read_file(argv[2],&input_size);
        if(!input)return profile_exit(3);
        code=xqvoice_wav_features(input,input_size,&features,&bytes);free(input);
        if(code)return profile_exit(5);
        trace=fopen(argv[3],"wb");
        if(!trace){free(features);return profile_exit(4);}
        code=fwrite(features,1,bytes,trace)==bytes?0:21;
        if(fclose(trace)!=0)code=21;
        free(features);return profile_exit(code);
    }
    if(argc==2 && strcmp(argv[1],"--selftest")==0) {
        if(requant(1,1073741824,31,-32768,32767)!=1 || requant(-1,1073741824,31,-32768,32767)!=-1 ||
           requant(3,1073741824,31,-32768,32767)!=2 || requant(-3,1073741824,31,-32768,32767)!=-2 ||
           requant(999999,1073741824,31,0,127)!=127 || requant(-999999,1073741824,31,0,127)!=0)return profile_exit(2);
        puts("PASS requant positive/negative ties and saturation");return profile_exit(0);
    }
    if(argc<4 || argc>6){fprintf(stderr,"usage: xqvoice-probe model.bin input output.trace [cpu|mac|mac-verify] [wav|wav-batch|wav-stream|capture|listen]\n");return profile_exit(1);}
    backend=0;
    if(argc>=5) {
        if(!strcmp(argv[4],"mac"))backend=1;
        else if(!strcmp(argv[4],"mac-verify"))backend=2;
        else if(strcmp(argv[4],"cpu"))return profile_exit(1);
    }
    stamp=xqvp_now();model=read_file(argv[1],&model_size);input=NULL;
    xqvp_add(XQVP_MODEL_READ,xqvp_now()-stamp);
    /* Resident setup happens before the source starts. Model bytes/CRC and
       numerical kernels stay unchanged; never reopen a device at the endpoint. */
    if(argc==6 && (!strcmp(argv[5],"wav-stream") || !strcmp(argv[5],"wav-batch") ||
                  !strcmp(argv[5],"capture") || !strcmp(argv[5],"listen"))){
        if(!model){return profile_exit(3);}
        stamp=xqvp_now();code=validate_model(model,model_size);
        xqvp_add(XQVP_MODEL_CHECK,xqvp_now()-stamp);
        if(code){free(model);return profile_exit(code);}
        trusted_model=model;trusted_model_size=model_size;
        if(backend){
            stamp=xqvp_now();code=xqvoice_mac_open();xqvp_add(XQVP_MAC_OPEN,xqvp_now()-stamp);
            if(code){free(model);fprintf(stderr,"MAC device/profile unavailable; no CPU fallback\n");return profile_exit(6);}
            opened=1;
        }
    }
    if(argc==6 && (!strcmp(argv[5],"capture") || !strcmp(argv[5],"listen"))) {
        stamp=xqvp_now();
        if(!model || model_size<384u || rd32(model+28)!=XQV_MODEL_CRC || crc32_bytes(model+384,model_size-384)!=XQV_MODEL_CRC ||
           (rd32(model+52)?rd32(model+52)!=XQV_HOP_SAMPLES:XQV_HOP_SAMPLES!=160u) ||
           (rd32(model+56) && rd32(model+56)!=512u) || (rd32(model+60) && rd32(model+60)!=400u)) {
            free(model);return profile_exit(10);
        }
        xqvp_add(XQVP_MODEL_CHECK,xqvp_now()-stamp);
        code=xqvoice_live_features(argv[2],&input,&input_size,!strcmp(argv[5],"listen"),&stream_metrics);
        if(code){xqvoice_mac_close();free(model);fprintf(stderr,"capture error %d\n",code);return profile_exit(7);}
    } else {stamp=xqvp_now();input=read_file(argv[2],&input_size);xqvp_add(XQVP_INPUT_READ,xqvp_now()-stamp);}
    if(!model || !input){xqvoice_mac_close();free(model);free(input);return profile_exit(3);}
    if(argc==6 && strcmp(argv[5],"capture") && strcmp(argv[5],"listen")) {
        uint8_t *qinput=NULL;size_t bytes=0;stamp=xqvp_now();
        int replay=!strcmp(argv[5],"wav-stream") || !strcmp(argv[5],"wav-batch");
        code=replay?xqvoice_replay_features(input,input_size,&qinput,&bytes,!strcmp(argv[5],"wav-stream"),1,&stream_metrics):
                    strcmp(argv[5],"wav")?-1:xqvoice_wav_features(input,input_size,&qinput,&bytes);
        if(code) {
            xqvoice_mac_close();free(model);free(input);fprintf(stderr,"WAV/frontend error\n");return profile_exit(5);
        }
        xqvp_add(XQVP_FEATURE,xqvp_now()-stamp);
        free(input);input=qinput;input_size=bytes;
    }
    stamp=xqvp_now();
    if(backend && !opened && xqvoice_mac_open()) {
        free(model);free(input);fprintf(stderr,"MAC device/profile unavailable; no CPU fallback\n");return profile_exit(6);
    }
    xqvp_add(XQVP_MAC_OPEN,xqvp_now()-stamp);
    if(stream_metrics.frames)feature_crc=crc32_bytes(input,input_size);
    trace=fopen(argv[3],"wb");
    if(!trace){xqvoice_mac_close();free(model);free(input);return profile_exit(4);}
    /* Keep fopen/fclose error checks. GUI explicitly requests /dev/null, so
       that mode needs no intermediate serialization; real traces stay exact. */
    inferred=timestamp_us();stamp=xqvp_now();code=run(model,model_size,input,input_size,strcmp(argv[3],"/dev/null")?trace:NULL);
    xqvp_add(XQVP_CNN,xqvp_now()-stamp);decoded_at=timestamp_us();
    if(fclose(trace)!=0 && code==0)code=21;
    free(model);free(input);
    if(!code) {
        char text[32];int decoded;stamp=xqvp_now();decoded=xqvoice_decode(final_logits,final_frames,text);
        xqvp_add(XQVP_DECODE,xqvp_now()-stamp);
        if(decoded<0)code=25;
        else {
            finished=timestamp_us();
            printf("backend=%s frames=%u text=%s mac_jobs=%llu mac_cycles=%llu prep_us=%llu cnn_us=%llu decode_us=%llu total_us=%llu resident_jobs=%llu\n",
                backend==0?"cpu":backend==1?"mac":"mac-verify",final_frames,text,xqvoice_mac_jobs(),xqvoice_mac_cycles(),
                (unsigned long long)(inferred-started),(unsigned long long)(decoded_at-inferred),
                (unsigned long long)(finished-decoded_at),(unsigned long long)(finished-started),xqvoice_mac_resident_jobs());
            if(stream_metrics.frames){
                printf("VOICE_STREAM_TIMING source=%s streamed=%u paced=%u feature_frames=%u max_backlog_frames=%u feature_crc=%08x feature_tail_us=%llu endpoint_to_result_us=%llu last_voice_to_result_us=%llu\n",
                    (!strcmp(argv[5],"wav-stream") || !strcmp(argv[5],"wav-batch"))?"wav-replay":"microphone",
                    stream_metrics.streamed,stream_metrics.paced,stream_metrics.frames,stream_metrics.max_backlog_frames,feature_crc,
                    (unsigned long long)(stream_metrics.features_done_us-stream_metrics.endpoint_us),
                    (unsigned long long)(finished-stream_metrics.endpoint_us),
                    (unsigned long long)(finished-stream_metrics.last_voice_us));
            }
        }
    }
    xqvp_mac(xqvoice_mac_jobs(),xqvoice_mac_cycles());
    xqvoice_mac_close();
    if(code)fprintf(stderr,"oracle error %d\n",code);
    return profile_exit(code);
}

#include "xqvoice_worker.inc"
