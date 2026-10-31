#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include "camera.h"
#include "clock_contract.h"

enum { WIDTH=640,HEIGHT=360 };
static void little32(uint32_t n)
{for(unsigned i=0;i<4;i++)putchar((int)((n>>(8*i))&255u));}
static void run(uint16_t n,uint16_t pixel)
{putchar(n&255);putchar(n>>8);putchar(pixel&255);putchar(pixel>>8);}
int main(int argc,char **argv)
{
 int fd=-1,rc=2,fixture=argc==2 && !strcmp(argv[1],"--fixture");
 volatile const uint32_t *fb=MAP_FAILED,*cam=MAP_FAILED,*sys=MAP_FAILED,*pixels=MAP_FAILED;
 uint16_t *sample=NULL;uint32_t status=0;
 if(argc!=1 && !fixture)return 2;
 sample=malloc(WIDTH*HEIGHT*2u);if(!sample)goto done;
 if(fixture){
  const uint16_t colors[]={0xf800,0x07e0,0x001f,0xffff,0x0000,0xffe0,0x07ff,0xf81f};
  for(unsigned y=0;y<HEIGHT;y++)for(unsigned x=0;x<WIDTH;x++)sample[y*WIDTH+x]=colors[x/80];
 }else{
  fd=open("/dev/mem",O_RDONLY|O_SYNC|O_CLOEXEC);if(fd<0)goto done;
  fb=mmap(0,4096,PROT_READ,MAP_SHARED,fd,0x1fe11000);
  cam=mmap(0,4096,PROT_READ,MAP_SHARED,fd,0x1fe12000);
  sys=mmap(0,4096,PROT_READ,MAP_SHARED,fd,0x1fe00000);
  if(fb==MAP_FAILED || cam==MAP_FAILED || sys==MAP_FAILED)goto done;
  if(sys[0x314/4]!=XINYI_CPU_HZ || fb[0]!=0x58514642 || fb[1]!=0x10000 ||
     fb[4]!=0x1b800000 || fb[5]!=0x1bc00000 || fb[6]!=3840 ||
     fb[7]!=((1080u<<16)|1920u) || fb[8]!=4147200 ||
     cam[0]!=CAMERA_ID_VALUE || cam[1]!=CAMERA_VERSION_VALUE ||
     cam[2]&CAMERA_CONTROL_ENABLE || cam[3]&(CAMERA_STATUS_WRITER_BUSY|CAMERA_STATUS_STOPPING) ||
     !(cam[3]&CAMERA_STATUS_IDLE))goto done;
  status=fb[3];if(!(status&2u) || status&((1u<<3)|(1u<<5)))goto done;
  uint32_t physical=status&4u?0x9bc00000u:0x9b800000u;
  pixels=mmap(0,4147200,PROT_READ,MAP_SHARED,fd,(off_t)physical);if(pixels==MAP_FAILED)goto done;
  for(unsigned y=0;y<HEIGHT;y++)for(unsigned x=0;x<WIDTH;x++){
   unsigned at=y*3u*1920u+x*3u;uint32_t word=pixels[at/2];
   sample[y*WIDTH+x]=(uint16_t)(word>>((at&1u)*16));
  }
  if((fb[3]&6u)!=(status&6u) || cam[2]&CAMERA_CONTROL_ENABLE)goto done;
 }
 if(fwrite("XYFBRL1\0",1,8,stdout)!=8)goto done;
 little32(WIDTH);little32(HEIGHT);
 for(unsigned i=0;i<WIDTH*HEIGHT;){
  unsigned n=1;while(i+n<WIDTH*HEIGHT && n<65535 && sample[i+n]==sample[i])n++;
  run((uint16_t)n,sample[i]);i+=n;
 }
 if(fflush(stdout) || ferror(stdout))goto done;
 rc=0;
done:
 if(pixels!=MAP_FAILED)munmap((void *)pixels,4147200);
 if(fb!=MAP_FAILED)munmap((void *)fb,4096);
 if(cam!=MAP_FAILED)munmap((void *)cam,4096);
 if(sys!=MAP_FAILED)munmap((void *)sys,4096);
 if(fd>=0)close(fd);
 free(sample);
 if(rc)fputs("XINYI_GUI_READBACK_REJECTED camera_must_be_idle=1\n",stderr);
 return rc;
}
