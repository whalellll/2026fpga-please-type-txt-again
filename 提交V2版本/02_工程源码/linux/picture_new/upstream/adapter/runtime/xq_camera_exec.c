#define _POSIX_C_SOURCE 200809L
#include "xq_camera.h"
#include "xq_camera_retry.h"
#include <signal.h>
#include <stdio.h>
#include <unistd.h>
static volatile sig_atomic_t stopped;
static void stop(int signal){(void)signal;stopped=1;}
static int cancel(void *p){(void)p;return stopped!=0;}
static void report(void *p,unsigned attempt,int result,uint32_t status)
{(void)p;printf("XQ_CAMERA_RECOVERY attempt=%u result=%d status=%08x\n",attempt,result,status);fflush(stdout);}
int main(int argc,char **argv)
{
    xqc_linux camera;char *args[]={"xiangqi-pikafish-gui",NULL};
    (void)argc;(void)argv;signal(SIGINT,stop);signal(SIGTERM,stop);
    if(!xqc_linux_open(&camera,cancel,NULL)){perror("XQ_CAMERA_OWNER_FAIL");return 1;}
    int result=xqc_start_retry(&camera.io,20000,8,report,NULL);
    if(!result && !stopped) {
        /* O_CLOEXEC releases the camera owner atomically, keeping the warm
         * private-bank stream for the GUI's normal exclusive open. */
        fflush(NULL);execv("/usr/bin/xiangqi-pikafish-gui",args);perror("XQ_CAMERA_EXEC_FAIL");
    }
    xqc_linux_close(&camera);return 1;
}
