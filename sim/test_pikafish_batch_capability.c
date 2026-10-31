#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "pango_mac_uapi.h"

static int scenario;
static int fake_open(const char *path, int flags, ...)
{
    (void)flags;
    if (strcmp(path,"/dev/pango-mac0") || scenario==7) { errno=ENOENT; return -1; }
    return 42;
}
static int fake_close(int fd) { return fd==42 ? 0 : -1; }
static int fake_ioctl(int fd, unsigned long request, ...)
{
    va_list ap; void *out;
    if(fd!=42) return -1;
    va_start(ap,request);out=va_arg(ap,void *);va_end(ap);
    if(request==PANGO_MAC_IOC_GET_INFO) {
        struct pango_mac_info *p=out;
        memset(p,0,sizeof(*p));p->abi_version=1;p->device_id=0x50464e31u;
        p->device_version=0x10000;p->scratch_bytes=1048576;p->features=0x5e3;
        if(scenario==1)p->features&=~(1u<<10);
        if(scenario==3)p->device_id=0x4d41434bu;
        if(scenario==4)p->abi_version=2;
        if(scenario==5)p->features|=1u<<9;
        return 0;
    }
    if(request==PANGO_MAC_IOC_RUN_BATCH) {
        struct pango_mac_batch *b=out;
        if(b->count!=0 || b->abi_version!=1) { errno=EIO;return -1; }
        if(scenario==6)return 0;
        errno=scenario==2 ? ENOTTY : EINVAL;
        return -1;
    }
    errno=ENOTTY;return -1;
}
#define open fake_open
#define close fake_close
#define ioctl fake_ioctl
#define main capability_main
#include "../linux/mac_accel/pango_mac_batch_check.c"
#undef main

int main(void)
{
    for(scenario=0;scenario<8;scenario++) {
        int result=capability_main();
        if((scenario==0 && result!=0) || (scenario!=0 && result==0)) {
            fprintf(stderr,"BATCH_CAPABILITY_FAULT_FAIL case=%d rc=%d\n",scenario,result);return 1;
        }
    }
    puts("BATCH_CAPABILITY_FAULT_CASES_PASS cases=8");return 0;
}
