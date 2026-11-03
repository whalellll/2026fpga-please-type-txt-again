#define _POSIX_C_SOURCE 200809L
#include "xqvoice_capture.h"
#include "xqvoice_frontend.h"
#include "pango_audio_uapi.h"
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned chunks,overflow,cancel_at,opens,closes;
int __wrap_open(const char *path,int flags,...){
    (void)flags;
    if(!strcmp(path,"/run/xqvoice-audio.lock"))return 82;
    assert(!strcmp(path,"/dev/test-audio"));opens++;return 81;
}
int __wrap_close(int fd){assert(fd==81 || fd==82);if(fd==81)closes++;return 0;}
int __wrap_flock(int fd,int mode){assert(fd==82);(void)mode;return 0;}
ssize_t __wrap_read(int fd,void *p,size_t bytes){
    unsigned char *out=p;assert(fd==81 && bytes==320);assert(chunks<400);
    /* Internal pause exercises provisional quiet-tail retention and resume. */
    int voiced=chunks<70 || (chunks>=90 && chunks<160);
    for(unsigned i=0;i<160;i++){
        int v=voiced?((i+chunks)%2?9000:-9000):0;
        out[i*2]=(unsigned char)v;out[i*2+1]=(unsigned char)((unsigned)v>>8);
    }
    chunks++;return 320;
}
int __wrap_ioctl(int fd,unsigned long request,...){
    va_list args;void *p;assert(fd==81);
    if(request==PANGO_AUDIO_IOC_CLEAR)return 0;
    va_start(args,request);p=va_arg(args,void*);va_end(args);
    if(request==PANGO_AUDIO_IOC_GET_INFO){
        struct pango_audio_info *i=p;memset(i,0,sizeof(*i));
        i->abi_version=PANGO_AUDIO_ABI_VERSION;i->device_id=PANGO_AUDIO_ID;
        i->device_version=PANGO_AUDIO_VERSION;i->sample_rate_hz=16000;i->channels=1;
        i->sample_format=PANGO_AUDIO_FORMAT_S16_LE;i->fifo_samples=512;return 0;
    }
    if(request==PANGO_AUDIO_IOC_GET_STATS){
        struct pango_audio_stats *s=p;memset(s,0,sizeof(*s));
        s->abi_version=PANGO_AUDIO_ABI_VERSION;s->fifo_overflows=overflow && chunks>4;return 0;
    }
    assert(request==PANGO_AUDIO_IOC_CLEAR);return 0;
}
static int cancelled(void *context){(void)context;return cancel_at && chunks>=cancel_at;}
static void stage(void *context,unsigned value){(void)context;assert(value<=2);}
static void put32(unsigned char *p,unsigned v){for(unsigned i=0;i<4;i++)p[i]=(unsigned char)(v>>(i*8));}
static void put16(unsigned char *p,unsigned v){p[0]=(unsigned char)v;p[1]=(unsigned char)(v>>8);}
int main(void){
    const unsigned sizes[]={400,401,719,720,721,8000,16000,32000,64240};
    for(unsigned c=0;c<sizeof(sizes)/sizeof(*sizes);c++){
        unsigned n=sizes[c];size_t len=44+n*2,ref_bytes=0;uint8_t *wav=calloc(1,len),*ref=NULL;
        assert(wav);memcpy(wav,"RIFF",4);put32(wav+4,(unsigned)len-8);memcpy(wav+8,"WAVEfmt ",8);
        put32(wav+16,16);put16(wav+20,1);put16(wav+22,1);put32(wav+24,16000);
        put32(wav+28,32000);put16(wav+32,2);put16(wav+34,16);memcpy(wav+36,"data",4);put32(wav+40,n*2);
        for(unsigned j=0;j<n;j++)put16(wav+44+j*2,(j*7993u+c*37u)&65535u);
        assert(!xqvoice_wav_features(wav,len,&ref,&ref_bytes));
        for(int stream=0;stream<2;stream++){
            uint8_t *actual=NULL;size_t bytes=0;xqvoice_stream_metrics m={0};
            assert(!xqvoice_replay_features(wav,len,&actual,&bytes,stream,0,&m));
            assert(bytes==ref_bytes && !memcmp(actual,ref,bytes));
            assert(m.frames==(n-400)/320+1 && m.streamed==(unsigned)stream && !m.paced);
            assert(m.started_us<=m.endpoint_us && m.endpoint_us<=m.features_done_us);
            free(actual);
        }
        if(n==8000u || n==32000u)for(int mode=0;mode<2;mode++){
            uint8_t *actual=NULL;size_t bytes=0;xqvoice_stream_metrics m={0};
            assert(!xqvoice_replay_features(wav,len,&actual,&bytes,mode,1,&m));
            assert(bytes==ref_bytes && !memcmp(actual,ref,bytes) && m.paced);
            assert(m.endpoint_us-m.started_us>=(uint64_t)n*1000000u/16000u);
            free(actual);
        }
        wav[20]=3;uint8_t *bad=NULL;size_t bytes=0;xqvoice_stream_metrics m={0};
        assert(xqvoice_replay_features(wav,len,&bad,&bytes,1,0,&m));assert(!bad);
        free(ref);free(wav);
    }
    uint8_t *batch=NULL,*stream=NULL;size_t a=0,b=0;
    xqvoice_capture_control control={cancelled,stage,NULL,320};
    chunks=0;assert(!setenv("XQVOICE_STREAM_FEATURES","0",1));
    assert(!xqvoice_capture_controlled("/dev/test-audio",&batch,&a,&control));
    chunks=0;assert(!setenv("XQVOICE_STREAM_FEATURES","1",1));
    assert(!xqvoice_capture_controlled("/dev/test-audio",&stream,&b,&control));
    assert(a==b && !memcmp(batch,stream,a));free(batch);free(stream);
    for(unsigned mode=0;mode<2;mode++) {
        xqvoice_stream_metrics m={0};stream=NULL;b=0;chunks=0;
        assert(!setenv("XQVOICE_STREAM_FEATURES",mode?"1":"0",1));
        assert(!xqvoice_capture_controlled_metrics("/dev/test-audio",&stream,&b,&control,&m));
        assert(m.frames && m.started_us<=m.last_voice_us && m.last_voice_us<=m.endpoint_us &&
               m.endpoint_us<=m.features_done_us && m.streamed==mode);
        free(stream);
    }
    assert(!setenv("XQVOICE_STREAM_FEATURES","1",1));
    for(unsigned fault=0;fault<2;fault++){
        stream=NULL;b=0;chunks=0;overflow=fault==0;cancel_at=fault==1?8:0;
        assert(xqvoice_capture_controlled("/dev/test-audio",&stream,&b,&control)==(fault==0?-22:-26));
        assert(!stream);
    }
    assert(opens==closes);
    puts("VOICE2_STREAM_FRONTEND_EXACT_BOUNDARIES_PAUSE_TRIM_CANCEL_OVERFLOW_PASS");return 0;
}
