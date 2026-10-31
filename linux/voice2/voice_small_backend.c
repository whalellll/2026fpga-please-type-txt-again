/* Small voice CNN backend; optional exact hardware requant, raw traces retained. */
#include "upstream/xqvoice_mac.h"
#include "../audio/pango_voice_uapi.h"
#include <fcntl.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
static int fd=-1;
static const uint8_t *resident;
static unsigned resident_k,resident_co,generation;
static unsigned long long jobs,cycles;
static unsigned features,quant_ready;
static struct pango_voice_cnn_model layer_model;
static struct pango_voice_cnn_tile tile;
int xqvoice_mac_quant_available(void){
 const char *raw=getenv("VOICE2_RAW_CNN");
 return fd>=0 && (features&PANGO_VOICE_FEATURE_CNN_QUANT) && !(raw && !strcmp(raw,"1"));
}
int xqvoice_mac_open(void){
 struct pango_voice_info info;
 if(fd>=0)return -1;
 fd=open("/dev/pango-voice0",O_RDWR|O_CLOEXEC);if(fd<0)return -2;
 memset(&info,0,sizeof(info));
 if(ioctl(fd,PANGO_VOICE_IOC_INFO,&info) || info.abi_version!=1 || info.device_id!=PANGO_VOICE_ID ||
    info.device_version!=PANGO_VOICE_VERSION || !(info.features&PANGO_VOICE_FEATURE_CNN_TILE)){
  close(fd);fd=-1;return -3;
 }
 resident=NULL;resident_k=resident_co=generation=0;jobs=cycles=0;
 features=info.features;quant_ready=0;
 if(getenv("VOICE2_REQUIRE_QUANT") && !strcmp(getenv("VOICE2_REQUIRE_QUANT"),"1") && !xqvoice_mac_quant_available()){
  close(fd);fd=-1;return -4;
 }
 fprintf(stderr,"VOICE2_SMALL_ACCEL_ACTIVE device=/dev/pango-voice0 lanes=4 strict=1 quant_available=%d\n",!!xqvoice_mac_quant_available());return 0;
}
void xqvoice_mac_close(void){if(fd>=0)close(fd);fd=-1;resident=NULL;generation=0;}
int xqvoice_mac_prepare_layer(const uint8_t *weights,unsigned k,unsigned co,unsigned job_count){
 struct pango_voice_cnn_model *m=&layer_model;
 unsigned n,j;
 if(fd<0 || !weights || k<4 || k>256 || (k&3) || !co || co>32 || !job_count)return -1;
 m->abi_version=1;m->k=k;m->cout=co;m->generation=0;quant_ready=0;
 /* Consume the original PFSB-style MAC packing without changing model bytes. */
 for(n=0;n<co;n++)for(j=0;j<k;j++)
  m->weights[n*k+j]=weights[(j/4u)*128u+(((n/2u)*4u+j%4u)*2u)+n%2u];
 if(ioctl(fd,PANGO_VOICE_IOC_CNN_MODEL,m)<0 || !m->generation){resident=NULL;return -3;}
 generation=m->generation;resident=weights;resident_k=k;resident_co=co;return 0;
}
int xqvoice_mac_prepare_quant(const int32_t *bias,const int32_t *mult,const unsigned *shift,unsigned co,int32_t lo,int32_t hi){
 struct pango_voice_cnn_quant q={0};unsigned i;
 if(!xqvoice_mac_quant_available() || !generation || co!=resident_co || !bias || !mult || !shift)return -1;
 q.abi_version=1;q.generation=generation;q.cout=co;q.clamp_lo=(uint32_t)lo;q.clamp_hi=(uint32_t)hi;
 for(i=0;i<co;i++){q.bias[i]=(uint32_t)bias[i];q.multiplier[i]=(uint32_t)mult[i];q.shift[i]=shift[i];}
 quant_ready=0;if(ioctl(fd,PANGO_VOICE_IOC_CNN_QUANT,&q)<0)return -2;
 quant_ready=1;return 0;
}
static int dense(const uint8_t *input,const uint8_t *weights,unsigned pixels,unsigned k,unsigned co,int32_t *output,int quant){
 struct pango_voice_cnn_tile *t=&tile;
 unsigned i,count;
 if(fd<0 || !input || !output || !pixels || pixels>16 || resident!=weights || k!=resident_k || co!=resident_co || !generation)return -1;
 if(quant && !quant_ready)return -2;
 t->abi_version=1;t->generation=generation;t->pixels=pixels;t->timeout_us=1000000;
 for(i=0;i<pixels*k;i++){
  if(input[i*2u+1u])return -3;
  t->input[i]=input[i*2u];
 }
 if(ioctl(fd,quant?PANGO_VOICE_IOC_CNN_QTILE:PANGO_VOICE_IOC_CNN_TILE,t)<0 || t->status!=2){resident=NULL;generation=quant_ready=0;return -4;}
 count=pixels*co;
 for(i=0;i<count;i++)memcpy(output+i,t->output+i,4);
 jobs++;cycles+=t->cycles;return 0;
}
int xqvoice_mac_dense(const uint8_t *input,const uint8_t *weights,unsigned pixels,unsigned k,unsigned co,int32_t *out){return dense(input,weights,pixels,k,co,out,0);}
int xqvoice_mac_dense_quant(const uint8_t *input,const uint8_t *weights,unsigned pixels,unsigned k,unsigned co,int32_t *out){return dense(input,weights,pixels,k,co,out,1);}
unsigned long long xqvoice_mac_jobs(void){return jobs;}
unsigned long long xqvoice_mac_cycles(void){return cycles;}
unsigned long long xqvoice_mac_resident_jobs(void){return jobs;}
