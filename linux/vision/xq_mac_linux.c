#define _POSIX_C_SOURCE 200809L
#include "xq_mac.h"
#include <fcntl.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
static int submit(void *context,struct pango_mac_job *job)
{
    return ioctl(((xqm_linux *)context)->fd,PANGO_MAC_IOC_RUN,job)==0 &&
        (job->status&2u) && !(job->status&4u) && !job->error_code;
}
int xqm_linux_open(xqm_linux *c)
{
    struct pango_mac_info info;
    const unsigned required=PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED|
        PANGO_MAC_FEATURE_STAGEA_GATHER|PANGO_MAC_FEATURE_RESIDENT_MODEL;
    if(!c)return 0;
    memset(c,0,sizeof(*c));c->fd=-1;
    c->fd=open("/dev/pango-mac0",O_RDWR|O_CLOEXEC);if(c->fd<0)return 0;
    memset(&info,0,sizeof(info));
    if(ioctl(c->fd,PANGO_MAC_IOC_GET_INFO,&info) || info.abi_version!=1 || info.device_id!=PANGO_MAC_ID ||
       info.device_version!=PANGO_MAC_VERSION || info.scratch_bytes!=0x100000 || info.max_pixels<16 ||
       info.max_channels<256 || info.max_timeout_us<1000000 || (info.features&required)!=required)goto fail;
    c->io.shadow=mmap(NULL,info.scratch_bytes,PROT_READ|PROT_WRITE,MAP_SHARED,c->fd,0);
    if(c->io.shadow==MAP_FAILED){c->io.shadow=NULL;goto fail;}
    c->features=info.features;
    c->io.bytes=info.scratch_bytes;c->io.submit=submit;c->io.context=c;return 1;
fail:
    xqm_linux_close(c);return 0;
}
void xqm_linux_close(xqm_linux *c)
{
    if(!c)return;
    if(c->resident_free)c->resident_free(c->resident_cache);
    if(c->io.shadow)munmap(c->io.shadow,c->io.bytes);
    if(c->fd>=0)close(c->fd);
    memset(c,0,sizeof(*c));c->fd=-1;
}
