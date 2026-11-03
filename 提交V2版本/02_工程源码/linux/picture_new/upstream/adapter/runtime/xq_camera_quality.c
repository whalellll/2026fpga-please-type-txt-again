#define _POSIX_C_SOURCE 200809L
#include "xq_camera.h"
#include "xq_camera_retry.h"
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static volatile sig_atomic_t stopped;
static void stop(int s){(void)s;stopped=1;}
static int cancel(void *p){(void)p;return stopped!=0;}
static void report(void *p,unsigned a,int result,uint32_t status)
{(void)p;printf("XQ_CAMERA_QUALITY_INIT attempt=%u result=%d status=%08x\n",a,result,status);fflush(stdout);}
int main(int argc,char **argv)
{
    xqc_linux camera;uint32_t *pixels=NULL;int rc=2,background;
    if(argc!=2 || (strcmp(argv[1],"legacy") && strcmp(argv[1],"background")))return 2;
    background=!strcmp(argv[1],"background");signal(SIGINT,stop);signal(SIGTERM,stop);
    pixels=malloc(XQV_FRAME_BYTES);if(!pixels)return 2;
    if(!xqc_linux_open(&camera,cancel,NULL))goto free_ram;
    if(xqc_stop(&camera.io))goto done;
    if(!background) {
        camera.io.background=0;camera.io.banks[0]=camera.maps[3];camera.io.banks[1]=camera.maps[4];
        if(xqc_stop(&camera.io))goto done;
        uint64_t start=camera.io.now_ms(camera.io.context);
        while(camera.io.camera[CAMERA_REG_STATUS/4]&CAMERA_STATUS_BACKGROUND_ACTIVE) {
            if(camera.io.poll(camera.io.context,1) || camera.io.now_ms(camera.io.context)-start>=2000)goto done;
        }
    }
    if(xqc_start_retry(&camera.io,20000,8,report,NULL))goto done;
    uint64_t start=camera.io.now_ms(camera.io.context);
    while(camera.io.now_ms(camera.io.context)-start<3000)
        if(camera.io.poll(camera.io.context,1))goto done;
    for(unsigned shot=0;shot<2;shot++) {
        xqv_frame frame;uint64_t rsum=0,gsum=0,bsum=0;unsigned lit=0,min=65535,max=0;
        if(xqc_capture(&camera.io,pixels,XQV_FRAME_BYTES,&frame))goto done;
        for(unsigned i=0;i<1280*720;i++) {
            unsigned v=(pixels[i/2]>>(16*(i%2)))&65535u;
            rsum+=(v>>11)&31;gsum+=(v>>5)&63;bsum+=v&31;
            if(v<min)min=v;
            if(v>max)max=v;
            if(((v>>11)&31)>4 || ((v>>5)&63)>8 || (v&31)>4)++lit;
        }
        printf("XQ_CAMERA_QUALITY mode=%s shot=%u frame=%u red_sum=%llu green_sum=%llu blue_sum=%llu lit=%u min=%u max=%u\n",
            argv[1],shot,frame.frame_id,(unsigned long long)rsum,(unsigned long long)gsum,(unsigned long long)bsum,lit,min,max);fflush(stdout);
        if(shot==1) {
            char path[100];snprintf(path,sizeof(path),"/run/xq-camera-quality-%s.rgb565",argv[1]);
            FILE *out=fopen(path,"wx");if(!out)goto done;
            for(unsigned y=0;y<720;y+=4) {
                uint32_t row[160];
                for(unsigned x=0;x<320;x+=2) {
                    unsigned index=y*1280+4*x,second=index+4;
                    row[x/2]=((pixels[index/2]>>(16*(index%2)))&65535u)|
                             (((pixels[second/2]>>(16*(second%2)))&65535u)<<16);
                }
                if(fwrite(row,1,sizeof(row),out)!=sizeof(row)){fclose(out);goto done;}
            }
            if(fclose(out))goto done;
        }
    }
    rc=0;
done:
    if(xqc_linux_close(&camera))rc=2;
free_ram:
    free(pixels);return rc;
}
