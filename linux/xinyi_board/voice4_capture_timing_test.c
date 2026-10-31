/* Synthetic live capture only: device calls and wall clock are explicit mocks.
 * A rejected one-block blip precedes the real utterance after70 quiet blocks. */
#define _POSIX_C_SOURCE 200809L
#include "xqvoice_capture.h"
#include "pango_audio_uapi.h"
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
static unsigned chunks,opens,closes;
int __wrap_open(const char *path,int flags,...)
{
    (void)flags;
    if(!strcmp(path,"/run/xqvoice-audio.lock"))return 82;
    assert(!strcmp(path,"/dev/test-audio"));opens++;return 81;
}
int __wrap_close(int fd){assert(fd==81 || fd==82);if(fd==81)closes++;return 0;}
int __wrap_flock(int fd,int mode){assert(fd==82);(void)mode;return 0;}
int __wrap_clock_gettime(clockid_t id,struct timespec *t)
{
    assert(id==CLOCK_MONOTONIC);
    uint64_t us=1000000u+(uint64_t)chunks*10000u;
    t->tv_sec=(time_t)(us/1000000u);t->tv_nsec=(long)(us%1000000u)*1000;return 0;
}
ssize_t __wrap_read(int fd,void *p,size_t bytes)
{
    unsigned char *out=p;assert(fd==81 && bytes==320 && chunks<300);
    int voiced=chunks==5 || (chunks>=70 && chunks<170);
    for(unsigned i=0;i<160;i++){
        int v=voiced?(i%2?9000:-9000):0;
        out[2*i]=(unsigned char)v;out[2*i+1]=(unsigned char)((unsigned)v>>8);
    }
    chunks++;return 320;
}
int __wrap_ioctl(int fd,unsigned long request,...)
{
    assert(fd==81);
    if(request==PANGO_AUDIO_IOC_CLEAR)return 0;
    va_list args;va_start(args,request);void *p=va_arg(args,void*);va_end(args);
    if(request==PANGO_AUDIO_IOC_GET_INFO){
        struct pango_audio_info *i=p;memset(i,0,sizeof(*i));
        i->abi_version=PANGO_AUDIO_ABI_VERSION;i->device_id=PANGO_AUDIO_ID;
        i->device_version=PANGO_AUDIO_VERSION;i->sample_rate_hz=16000;i->channels=1;
        i->sample_format=PANGO_AUDIO_FORMAT_S16_LE;i->fifo_samples=512;return 0;
    }
    assert(request==PANGO_AUDIO_IOC_GET_STATS);
    struct pango_audio_stats *s=p;memset(s,0,sizeof(*s));s->abi_version=PANGO_AUDIO_ABI_VERSION;return 0;
}
static void stage(void *p,unsigned value){(void)p;assert(value<=2);}
int main(void)
{
    uint8_t *previous=NULL;size_t previous_bytes=0;
    for(int stream=0;stream<2;stream++){
        chunks=0;assert(!setenv("XQVOICE_STREAM_FEATURES",stream?"1":"0",1));
        xqvoice_capture_control c={NULL,stage,NULL,320};xqvoice_stream_metrics m={0};
        uint8_t *data=NULL;size_t bytes=0;
        assert(!xqvoice_capture_controlled_metrics("/dev/test-audio",&data,&bytes,&c,&m));
        assert(data && bytes && m.frames);
        assert(m.started_us==1000000u && m.utterance_start_us==1710000u);
        assert(m.utterance_start_us>m.started_us && m.last_voice_us>=m.utterance_start_us);
        assert(m.endpoint_us>=m.last_voice_us && m.features_done_us>=m.endpoint_us);
        if(previous){assert(previous_bytes==bytes && !memcmp(previous,data,bytes));free(previous);}
        previous=data;previous_bytes=bytes;
    }
    free(previous);assert(opens==2 && closes==2);
    puts("VOICE4_VAD_ONSET_REJECTED_BLIP_QUIET_WAIT_BATCH_STREAM_FEATURES_EQUAL_PASS");return 0;
}
