/* One finite preview of the production camera driver; no frame export. */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include "xq_camera.h"
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <signal.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/file.h>
static volatile sig_atomic_t cancelled;
static volatile uint32_t *sample_hid;
static volatile uint32_t hid_sink;
static void stop_signal(int n){(void)n;cancelled=1;}
static uint64_t now(void *unused){(void)unused;struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;return(uint64_t)t.tv_sec*1000+(unsigned)t.tv_nsec/1000000;}
static int poll_camera(void *unused,int waiting){(void)unused;if(waiting){const struct timespec t={0,1000000};nanosleep(&t,NULL);}if(sample_hid)hid_sink=sample_hid[6]^sample_hid[5]^sample_hid[6]^sample_hid[7]^sample_hid[3]^sample_hid[10]^sample_hid[2]^sample_hid[7];return cancelled;}
static void state(const char *phase,xqc_camera *c)
{
 printf("R19_CAMERA_%s control=%08x status=%08x frames=%u dropped=%u bad_lines=%u video_control=%08x video_status=%08x\n",
 phase,c->camera[2],c->camera[3],c->camera[4],c->camera[5],c->camera[6],c->fb[2],c->fb[3]);
}
int main(int argc,char **argv)
{
 int video=argc==2 && (!strcmp(argv[1],"--video-on") || !strcmp(argv[1],"--video-on-hid") || !strcmp(argv[1],"--video-bank1"));
 if(argc>2 || (argc==2 && !video))return 2;
 setvbuf(stdout,NULL,_IOLBF,0);signal(SIGTERM,stop_signal);signal(SIGINT,stop_signal);
 int lock=open("/run/xq-camera.lock",O_CREAT|O_RDWR|O_CLOEXEC,0600);
 if(lock<0 || flock(lock,LOCK_EX|LOCK_NB))return 2;
 int fd=open("/dev/mem",O_RDWR|O_SYNC|O_CLOEXEC);if(fd<0)return 2;
 volatile uint32_t *sys=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x1fe00000u);
 volatile uint32_t *cam=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x1fe12000u);
 volatile uint32_t *fb=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x1fe11000u);
 if(sys==MAP_FAILED || cam==MAP_FAILED || fb==MAP_FAILED)return 2;
 printf("R19_CAMERA_IDENT sys=%08x cpu=%u sys_hz=%u caps=%08x camera=%08x version=%08x\n",sys[0x300/4],sys[0x314/4],sys[0x308/4],sys[0x30c/4],cam[0],cam[1]);
 if(sys[0x300/4]!=0x53563300 || sys[0x314/4]!=60000000 || sys[0x308/4]!=49500000 ||
    cam[0]!=CAMERA_ID_VALUE || cam[1]!=CAMERA_VERSION_VALUE)return 3;
 xqc_camera c={.camera=cam,.fb=fb,.sys=sys+0x300/4,.now_ms=now,.poll=poll_camera};
 uint32_t saved=fb[2]&3u;
 if(video){fb[2]=!strcmp(argv[1],"--video-bank1")?3u:1u;const struct timespec t={0,80000000};nanosleep(&t,NULL);}
 if(argc==2 && !strcmp(argv[1],"--video-on-hid"))sample_hid=sys+0x400/4;
 printf("R19_CAMERA_MODE %s\n",argc==2?argv[1]:"video-off");state("BEFORE",&c);
 uint64_t start=now(NULL);int r=xqc_start(&c,5000);state("START_RETURN_BEFORE_CLEANUP",&c);
 printf("R19_CAMERA_START result=%d elapsed_ms=%llu\n",r,(unsigned long long)(now(NULL)-start));
 if(!r){uint64_t until=now(NULL)+2000;while(!cancelled && now(NULL)<until)(void)poll_camera(NULL,1);state("LIVE_END",&c);}
 int drained=xqc_stop(&c);state("STOP",&c);
 if(!drained && !c.poisoned){fb[2]=saved;__asm__ volatile("fence iorw,iorw":::"memory");}
 printf("R19_CAMERA_DONE start_result=%d stop_result=%d poisoned=%d read_pixels=0\n",r,drained,c.poisoned);
 munmap((void *)fb,4096);munmap((void *)cam,4096);munmap((void *)sys,4096);close(fd);close(lock);
 return drained || c.poisoned?4:r?1:0;
}
