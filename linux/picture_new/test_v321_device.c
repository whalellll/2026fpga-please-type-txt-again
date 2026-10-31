#define _POSIX_C_SOURCE 200809L
#include "xq_mac.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>

extern int xqv_run(const xqm_transport *,struct pango_vision32_job *);
static struct pango_mac_info info;
static uint32_t shadow[0x100000/4];
static unsigned opens,closes,maps,unmaps,runs;
static int open_error,info_error,map_error,run_error,cancelled;
static unsigned status=2;
int __wrap_open(const char *path,int flags,...)
{
    assert(!strcmp(path,"/dev/pango-mac0"));
    assert(flags==(O_RDWR|O_CLOEXEC));opens++;
    if(open_error){errno=ENOENT;return -1;}return 71;
}
int __wrap_close(int fd){assert(fd==71);closes++;return 0;}
void *__wrap_mmap(void *address,size_t bytes,int prot,int flags,int fd,off_t offset)
{
    assert(!address && bytes==0x100000 && prot==(PROT_READ|PROT_WRITE));
    assert(flags==MAP_SHARED && fd==71 && !offset);maps++;
    if(map_error)return MAP_FAILED;
    return shadow;
}
int __wrap_munmap(void *address,size_t bytes)
{assert(address==shadow && bytes==0x100000);unmaps++;return 0;}
int __wrap_ioctl(int fd,unsigned long command,...)
{
    va_list args;va_start(args,command);void *out=va_arg(args,void *);va_end(args);
    assert(fd==71);
    if(command==PANGO_MAC_IOC_GET_INFO){
        if(info_error){errno=EIO;return -1;}
        memcpy(out,&info,sizeof(info));return 0;
    }
    assert(command==PANGO_MAC_IOC_RUN_VISION32);runs++;
    if(run_error){errno=ETIMEDOUT;return -1;}
    struct pango_vision32_job *j=out;j->status=status;j->error=0;return 0;
}
static int is_cancelled(void *context){assert(context);return cancelled;}
static void defaults(void)
{
    memset(&info,0,sizeof(info));
    info.abi_version=1;info.device_id=PANGO_MAC_PIKAFISH_ID;
    info.device_version=PANGO_MAC_PIKAFISH_VERSION;info.scratch_bytes=0x100000;
    info.features=PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED|PANGO_MAC_FEATURE_VISION32;
    info.max_timeout_us=1000000;
    open_error=info_error=map_error=run_error=cancelled=0;
}
int main(void)
{
    xqm_linux device={.fd=-1};
    for(unsigned bit=0;bit<3;bit++){
        defaults();unsigned required[]={PANGO_MAC_FEATURE_PRIVATE_SHADOW,PANGO_MAC_FEATURE_SERIALIZED,PANGO_MAC_FEATURE_VISION32};
        info.features&=~required[bit];assert(!xqm_linux_open(&device));assert(device.fd==-1 && !device.io.shadow);
    }
    for(unsigned bad=0;bad<8;bad++){
        defaults();
        if(bad==0)info.abi_version=2;
        if(bad==1)info.device_id=0;
        if(bad==2)info.device_version=0;
        if(bad==3)info.scratch_bytes=0x200000;
        if(bad==4)info.max_timeout_us=999999;
        if(bad==5)open_error=1;
        if(bad==6)info_error=1;
        if(bad==7)map_error=1;
        assert(!xqm_linux_open(&device));assert(device.fd==-1 && !device.io.shadow);
    }
    defaults();assert(xqm_linux_open(&device));
    assert(device.features==info.features && !device.conv_enabled && !device.io.submit);
    struct pango_vision32_job job={0};
    job.abi_version=1;job.width=job.height=job.cin=job.cout=job.kernel=job.stride=1;
    job.weights=0x1000;job.params=0x2000;job.output=0x3000;job.flags=2;job.timeout_cycles=16;
    assert(xqv_run(&device.io,&job));unsigned completed=runs;
    device.io.cancelled=is_cancelled;cancelled=1;
    assert(!xqv_run(&device.io,&job) && runs==completed);cancelled=0;
    xqm_transport copy=device.io;assert(!xqv_run(&copy,&job) && runs==completed);
    job.output=0;assert(!xqv_run(&device.io,&job) && runs==completed);job.output=0x3000;
    run_error=1;assert(!xqv_run(&device.io,&job));run_error=0;
    status=3;assert(!xqv_run(&device.io,&job));status=6;assert(!xqv_run(&device.io,&job));
    xqm_linux_close(&device);
    assert(device.fd==-1 && !device.io.shadow && !device.features);
    assert(opens==12 && closes==11 && maps==2 && unmaps==1);
    puts("V321_DEVICE_FEATURES_CANCEL_AND_FATAL_ERRORS_PASS no_devmem=1");return 0;
}
