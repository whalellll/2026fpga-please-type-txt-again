/* Small voice CNN backend. The upstream CPU FFT/CTC and requant stay intact. */
#include "xqvoice_mac.h"
#include "../voice_accel/pango_voice_uapi.h"
#include <fcntl.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
static int fd=-1;
static uint8_t packed_input[16u*256u*2u];
/* One synchronous worker owns this device. Reuse private requests rather than
 * allocate and zero 6 KiB on every tile. No shared or asynchronous ownership. */
static struct pango_voice_cnn_model model_request;
static struct pango_voice_cnn_tile tile_request;
static const uint8_t *resident;
static unsigned resident_k,resident_co,generation;
static unsigned long long jobs,cycles;
int xqvoice_mac_open(void){
 struct pango_voice_info info;
 const char *pipeline=getenv("XQVOICE_MAC_PIPELINE");
 if(pipeline && strcmp(pipeline,"0"))return -9;
 if(fd>=0)return -1;
 fd=open("/dev/pango-voice0",O_RDWR|O_CLOEXEC);if(fd<0)return -2;
 memset(&info,0,sizeof(info));
 if(ioctl(fd,PANGO_VOICE_IOC_INFO,&info) || info.abi_version!=1 || info.device_id!=PANGO_VOICE_ID ||
    info.device_version!=PANGO_VOICE_VERSION || !(info.features&PANGO_VOICE_FEATURE_CNN_TILE)){
  close(fd);fd=-1;return -3;
 }
 resident=NULL;resident_k=resident_co=generation=0;jobs=cycles=0;
 memset(&model_request,0,sizeof(model_request));
 memset(&tile_request,0,sizeof(tile_request));
 fprintf(stderr,"VOICE2_SMALL_ACCEL_ACTIVE device=/dev/pango-voice0 lanes=4 strict=1\n");return 0;
}
void xqvoice_mac_close(void){if(fd>=0)close(fd);fd=-1;resident=NULL;generation=0;}
int xqvoice_mac_prepare_layer(const uint8_t *weights,unsigned k,unsigned co,unsigned job_count){
 struct pango_voice_cnn_model *m=&model_request;
 unsigned n,j;
 if(fd<0 || !weights || k<4 || k>256 || (k&3) || !co || co>32 || !job_count)return -1;
 memset(m,0,sizeof(*m));
 m->abi_version=1;m->k=k;m->cout=co;
 /* Consume the original PFSB-style MAC packing without changing model bytes. */
 for(n=0;n<co;n++)for(j=0;j<k;j++)
  m->weights[n*k+j]=weights[(j/4u)*128u+(((n/2u)*4u+j%4u)*2u)+n%2u];
 if(ioctl(fd,PANGO_VOICE_IOC_CNN_MODEL,m)<0 || !m->generation){resident=NULL;generation=0;return -3;}
 generation=m->generation;resident=weights;resident_k=k;resident_co=co;return 0;
}
int xqvoice_mac_dense(const uint8_t *input,const uint8_t *weights,unsigned pixels,unsigned k,unsigned co,int32_t *output){
 struct pango_voice_cnn_tile *t=&tile_request;
 unsigned i,count;
 if(fd<0 || !input || !output || !pixels || pixels>16 || resident!=weights || k!=resident_k || co!=resident_co || !generation)return -1;
 /* CPU60 ABI reads only pixels*k input bytes and the request header. The
  * kernel overwrites the entire output array on success. Unused input stays
  * private; reserved words are kept zero, including after an ioctl failure. */
 memset(t,0,offsetof(struct pango_voice_cnn_tile,input));
 t->abi_version=1;t->generation=generation;t->pixels=pixels;t->timeout_us=1000000;
 for(i=0;i<pixels*k;i++){
  if(input[i*2u+1u])return -3;
  t->input[i]=input[i*2u];
 }
 if(ioctl(fd,PANGO_VOICE_IOC_CNN_TILE,t)<0 || t->status!=2){resident=NULL;generation=0;return -4;}
 count=pixels*co;
 memcpy(output,t->output,count*sizeof(*output));
 jobs++;cycles+=t->cycles;return 0;
}
unsigned long long xqvoice_mac_jobs(void){return jobs;}
unsigned long long xqvoice_mac_cycles(void){return cycles;}
unsigned long long xqvoice_mac_resident_jobs(void){return jobs;}

/* Private synchronous input only. CPU60 has no async START/FINISH ABI. */
uint8_t *xqvoice_mac_input_buffer(unsigned pixels,unsigned k){
 return fd>=0 && pixels && pixels<=16 && k>=4 && k<=256 && !(k&3)?packed_input:NULL;
}
int xqvoice_mac_async_enabled(void){return 0;}
int xqvoice_mac_start(const uint8_t *w,unsigned p,unsigned k,unsigned co){(void)w;(void)p;(void)k;(void)co;return -99;}
int xqvoice_mac_finish(void){return -99;}
const uint8_t *xqvoice_mac_output_buffer(void){return NULL;}
