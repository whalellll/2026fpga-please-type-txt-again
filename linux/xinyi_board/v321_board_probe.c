#define _POSIX_C_SOURCE 200809L
#include "pango_mac_uapi.h"
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

static int prepare(unsigned which,uint8_t *shadow,struct pango_vision32_job *j,int32_t *expected,unsigned *count)
{
 unsigned sizes[5];memset(shadow,0,0x20000);memset(j,0,sizeof(*j));
 j->abi_version=PANGO_VISION32_ABI;j->input=0;j->weights=0x10000;j->output=0x8000;j->params=0x4000;
 j->flags=2;j->timeout_cycles=49500000;j->timeout_us=1000000;j->stride=1;j->kernel=1;j->height=1;
 if(which==0){
  static const int32_t truth[]={-6,-4,-2,0,2,4,6,8};
  j->width=8;j->cin=j->cout=1;*count=8;
  for(unsigned x=0;x<8;x++)shadow[x*4]=(uint8_t)(int8_t)((int)x-3);
  shadow[j->weights]=2;memcpy(expected,truth,sizeof(truth));
 }else if(which==1){
  static const int8_t input[]={1,-2,3,0,-4,5,-6,0};
  j->width=2;j->cin=3;j->cout=9;*count=18;memcpy(shadow,input,sizeof(input));
  for(unsigned o=0;o<9;o++){
   int a=(int)o+1;shadow[j->weights+((o/8)*3+0)*8+o%8]=(uint8_t)(int8_t)a;
   shadow[j->weights+((o/8)*3+1)*8+o%8]=(uint8_t)(int8_t)-a;
   shadow[j->weights+((o/8)*3+2)*8+o%8]=(uint8_t)(int8_t)(2*a);
   expected[o]=9*a;expected[9+o]=-21*a;
  }
 }else if(which==2){
  static const int32_t truth[]={12,21,16,27,45,33,24,39,28};
  j->width=j->height=3;j->cin=j->cout=1;j->kernel=3;j->padding=1;*count=9;
  for(unsigned x=0;x<9;x++){shadow[x*4]=(uint8_t)(x+1);shadow[j->weights+x*8]=1;}
  memcpy(expected,truth,sizeof(truth));
 }else if(which==3){
  j->width=j->height=j->kernel=6;j->cin=32;j->cout=2;j->stride=2;*count=2;
  for(unsigned pixel=0;pixel<36;pixel++)for(unsigned c=0;c<32;c++)shadow[pixel*32+c]=127;
  for(unsigned tap=0;tap<1152;tap++){shadow[j->weights+tap*8]=127;shadow[j->weights+tap*8+1]=(uint8_t)(int8_t)(tap%2?-127:127);}
  expected[0]=18580608;expected[1]=0; /* Requires more than 16/24 accumulator bits. */
 }else return 0;
 memset(shadow+j->output,0xa5,*count*4);
 return pango_vision32_sizes(j,0x100000,sizes) && sizes[2]==*count*4;
}
int main(int argc,char **argv)
{
 int fd=-1,rc=2,self=argc==2 && !strcmp(argv[1],"--self-check");uint8_t *shadow=MAP_FAILED;
 struct pango_mac_info info={0};uint64_t cycles=0;uint32_t mac_cycles=0;
 if(argc!=1 && !self)return 2;
 if(self)shadow=calloc(1,0x100000);
 else{
  fd=open("/dev/pango-mac0",O_RDWR|O_CLOEXEC);if(fd<0)goto done;
  const unsigned required=PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED|PANGO_MAC_FEATURE_VISION32;
  if(ioctl(fd,PANGO_MAC_IOC_GET_INFO,&info) || info.abi_version!=1 ||
    info.device_id!=PANGO_MAC_PIKAFISH_ID || info.device_version!=PANGO_MAC_PIKAFISH_VERSION ||
    info.scratch_bytes!=0x100000 || info.max_timeout_us<1000000 || (info.features&required)!=required)goto done;
  shadow=mmap(0,info.scratch_bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
 }
 if(!shadow || shadow==MAP_FAILED)goto done;
 for(unsigned test=0;test<4;test++){
  struct pango_vision32_job job;int32_t expected[32];unsigned n;
  if(!prepare(test,shadow,&job,expected,&n))goto done;
  if(self)continue;
  if(ioctl(fd,PANGO_MAC_IOC_RUN_VISION32,&job) || (job.status&7u)!=2u || job.error || !job.cycles){
   fprintf(stderr,"V321_BOARD_PROBE_IO_FAIL case=%u errno=%d status=%u error=%u\n",test,errno,job.status,job.error);goto done;
  }
  for(unsigned i=0;i<n;i++){
   int32_t actual;memcpy(&actual,shadow+job.output+i*4,4);
   if(actual!=expected[i]){fprintf(stderr,"V321_BOARD_PROBE_DATA_FAIL case=%u index=%u\n",test,i);goto done;}
  }
  cycles+=job.cycles;mac_cycles+=job.mac_cycles;
 }
 if(self)puts("V321_PROBE_VECTORS_PREPARED_NOT_BOARD");
 else printf("V321_BOARD_RAW_I32_PASS cases=4 outputs=37 hardware_cycles=%llu mac_cycles=%u no_fallback=1\n",(unsigned long long)cycles,mac_cycles);
 rc=0;
done:
 if(shadow && shadow!=MAP_FAILED){if(self)free(shadow);else munmap(shadow,0x100000);}
 if(fd>=0)close(fd);
 if(rc)fputs("V321_BOARD_PROBE_FAILED no_fallback=1\n",stderr);
 return rc;
}
