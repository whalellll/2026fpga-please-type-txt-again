/* Finite read-only observer of actual HID release to stable scanout.
 * No MMIO writes, camera capture, input injection, or GUI instrumentation. */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <time.h>
#include <signal.h>
#include <unistd.h>
enum { N=32 };
typedef struct {unsigned x,y,pixel[4];} point;
static point points[N];
static volatile sig_atomic_t stopped;
static void stop(int n){(void)n;stopped=1;}
static uint64_t ms(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))exit(9);return(uint64_t)t.tv_sec*1000+(unsigned)t.tv_nsec/1000000;}
static int page(volatile uint32_t *v,volatile uint32_t *a,volatile uint32_t *b)
{
 uint32_t status=v[3];if((status&42u)!=2u)return -1;
 volatile uint32_t *fb=(status&4u)?b:a;unsigned match=15;
 for(unsigned i=0;i<N;i++){
  unsigned at=points[i].y*1920+points[i].x;
  unsigned pixel=fb[at/2]>>((at&1u)*16)&65535u;
  for(unsigned p=0;p<4;p++)if(pixel!=points[i].pixel[p])match&=~(1u<<p);
 }
 if(v[3]!=status || !match || (match&(match-1)))return -1;
 for(unsigned p=0;p<4;p++)if(match==(1u<<p))return (int)p;
 return -1;
}
static int home_hit(unsigned x,unsigned y)
{
 if(x<760 || x>=1160)return -1;
 for(unsigned i=0;i<4;i++)if(y>=340+128*i && y<432+128*i)return (int)i;
 return -1;
}
int main(int argc,char **argv)
{
 if(argc!=3)return 2;unsigned seconds=(unsigned)strtoul(argv[2],NULL,10);
 if(seconds<10 || seconds>180)return 2;
 FILE *f=fopen(argv[1],"r");if(!f)return 2;
 for(unsigned i=0;i<N;i++)if(fscanf(f,"%u %u %x %x %x %x",&points[i].x,&points[i].y,&points[i].pixel[0],&points[i].pixel[1],&points[i].pixel[2],&points[i].pixel[3])!=6 || points[i].x>=1920 || points[i].y>=1080)return 2;
 char extra;if(fscanf(f," %c",&extra)!=EOF)return 2;fclose(f);
 setvbuf(stdout,NULL,_IOLBF,0);signal(SIGTERM,stop);signal(SIGINT,stop);
 int fd=open("/dev/mem",O_RDONLY|O_SYNC);if(fd<0)return 3;
 volatile uint32_t *s=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,0x1fe00000u);
 volatile uint32_t *v=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,0x1fe11000u);
 if(s==MAP_FAILED || v==MAP_FAILED)return 3;
 if(s[0x300/4]!=0x53563300 || s[0x314/4]!=60000000 || s[0x308/4]!=49500000 || s[0x400/4]!=0x43483935 || v[4]!=0x1b800000 || v[5]!=0x1bc00000 || v[6]!=3840)return 4;
 volatile uint32_t *a=mmap(NULL,4147200,PROT_READ,MAP_SHARED,fd,(off_t)0x9b800000u);
 volatile uint32_t *b=mmap(NULL,4147200,PROT_READ,MAP_SHARED,fd,(off_t)0x9bc00000u);
 if(a==MAP_FAILED || b==MAP_FAILED)return 3;
 volatile uint32_t *h=s+0x400/4;
 uint32_t down=h[2]&1u,counts=h[10],found_frame=0;uint64_t began=ms(),released=0;
 int old=page(v,a,b),source=-1,candidate=-1,clicks=0,completes=0;
 uint32_t xy0=h[3],hover_frame=0;int hover=home_hit(xy0&2047u,(xy0>>11)&2047u),hover_candidate=0,hover_count=0;
 uint64_t hover_at=0;
 printf("R19_UI_READY seconds=%u initial_page=%d sample_ms=10 threshold_ms=1000 read_only=1\n",seconds,old);
 while(!stopped && ms()-began<(uint64_t)seconds*1000 && clicks<16){
  uint32_t before=h[7],xy=h[3],c=h[10],buttons=h[2],after=h[7];uint64_t now=ms();
  if(before==after){
   unsigned x=xy&2047u,y=(xy>>11)&2047u,d=buttons&1u;
   int hit=old==0 && (buttons&16u)?home_hit(x,y):-1;
   if(hit!=hover){
    hover=hit;hover_at=hit>=0?now:0;hover_candidate=0;
    if(hit>=0 && hover_count<16)printf("R19_UI_ENTER button=%d elapsed_ms=%llu\n",hit,(unsigned long long)(now-began));
   }
   if(hover_at && hover_count<16){
    uint32_t status=v[3];volatile uint32_t *fb=(status&4u)?b:a;
    unsigned at=(340u+128u*(unsigned)hover)*1920u+900u;
    unsigned pixel=fb[at/2]>>((at&1u)*16)&65535u;
    if((status&42u)==2u && pixel==(((186u>>3)<<11)|((145u>>2)<<5)|(88u>>3)) && status==v[3]){
     if(!hover_candidate){hover_frame=v[9];hover_candidate=1;}
     else if((uint32_t)(v[9]-hover_frame)>=2){
      unsigned latency=(unsigned)(ms()-hover_at);hover_count++;
      printf("R19_UI_HIGHLIGHT button=%d latency_ms=%u pass_1000ms=%u\n",hover,latency,latency<=1000);hover_at=0;
     }
    }else hover_candidate=0;
   }
   if((buttons&16u) && x<1920 && y<1080 && !d && (down || (uint16_t)c!=(uint16_t)counts)){
    clicks++;source=page(v,a,b);released=now;candidate=-1;
    printf("R19_UI_RELEASE number=%d from=%d x=%u y=%u elapsed_ms=%llu\n",clicks,source,x,y,(unsigned long long)(now-began));
   }
   down=d;counts=c;
  }
  int p=page(v,a,b);
  if(released && p>=0 && p!=source){
   if(candidate!=p){candidate=p;found_frame=v[9];}
   else if((uint32_t)(v[9]-found_frame)>=2){
    unsigned latency=(unsigned)(ms()-released);completes++;
    printf("R19_UI_VISIBLE number=%d to=%d latency_ms=%u pass_1000ms=%u frame=%u\n",clicks,p,latency,latency<=1000,v[9]);released=0;
   }
  }else candidate=-1;
  if(p>=0 && p!=old){old=p;printf("R19_UI_PAGE page=%d elapsed_ms=%llu\n",p,(unsigned long long)(ms()-began));}
  if(released && now-released>10000){printf("R19_UI_NO_PAGE_CHANGE number=%d\n",clicks);released=0;}
  const struct timespec pause={0,10000000};nanosleep(&pause,NULL);
 }
 printf("R19_UI_DONE clicks=%d page_changes=%d stopped=%d\n",clicks,completes,(int)stopped);
 munmap((void *)b,4147200);munmap((void *)a,4147200);munmap((void *)v,4096);munmap((void *)s,4096);close(fd);return 0;
}
