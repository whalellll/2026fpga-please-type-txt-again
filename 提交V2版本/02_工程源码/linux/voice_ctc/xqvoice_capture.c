#define _POSIX_C_SOURCE 200809L
#include "xqvoice_capture.h"
#include "xqvoice_frontend.h"
#include "xqvoice_profile.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
void xqvoice_capture_init(xqvoice_capture_state *s,int16_t *samples,size_t capacity) {
    memset(s,0,sizeof(*s));s->samples=samples;s->capacity=capacity;
}
int xqvoice_capture_feed(xqvoice_capture_state *s,const int16_t chunk[160]) {
    uint32_t sum=0,level;int32_t dc=0;unsigned i;
    if(s->done)return s->done;
    /* VAD measures AC speech energy. Preserve original PCM for the frontend. */
    for(i=0;i<160;i++)dc+=chunk[i];
    dc/=160;
    for(i=0;i<160;i++){int32_t v=(int32_t)chunk[i]-dc;sum+=(uint32_t)(v<0?-v:v);}
    level=sum/160u;s->chunks++;
    if(!s->active) {
        memcpy(s->ring[s->ring_next],chunk,320);s->ring_next=(s->ring_next+1)%20u;
        if(s->ring_count<20u)s->ring_count++;
        s->start_run=level>=100u?s->start_run+1u:0;
        if(s->start_run>=3u) {
            unsigned first=(s->ring_next+20u-s->ring_count)%20u;
            if(s->capacity<s->ring_count*160u){s->done=-2;return s->done;}
            for(i=0;i<s->ring_count;i++)memcpy(s->samples+i*160u,s->ring[(first+i)%20u],320);
            s->count=s->ring_count*160u;s->voiced=s->start_run;s->active=1;
        } else if(!s->listen && s->chunks>=600u)s->done=-1;
        if(s->listen && !s->active)s->chunks=0; /* No timeout or accumulating counter in quiet idle. */
        return s->done?s->done:s->active;
    }
    if(s->count+160u>s->capacity){s->done=-2;return s->done;}
    memcpy(s->samples+s->count,chunk,320);s->count+=160u;
    if(level>=60u){s->voiced++;s->quiet=0;}else s->quiet++;
    if(s->quiet>=XQV_END_SILENCE_CHUNKS) {
        s->count-=(XQV_END_SILENCE_CHUNKS-12u)*160u;
        s->done=s->voiced>=30u && s->count>=9600u?2:-3;
    }
    return s->done?s->done:1;
}
int xqvoice_capture_finish(xqvoice_capture_state *s) {
    if(s->done)return s->done;
    s->done=!s->active?-1:s->voiced<30u || s->count<9600u?-3:2;
    return s->done;
}
#if defined(__linux__)
#include "pango_audio_uapi.h"
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <sys/file.h>
#include <time.h>
#include <signal.h>
#include <stdatomic.h>
#ifndef XQV_HOP_SAMPLES
#define XQV_HOP_SAMPLES 160u
#endif
_Static_assert(ATOMIC_INT_LOCK_FREE==2,"Capture signal flag must be lock-free");
static atomic_int manual_stop;
static void stop_capture(int signal_number) { (void)signal_number;manual_stop=1; }
static uint64_t now_ms(void) {
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t))return UINT64_MAX;
    return (uint64_t)t.tv_sec*1000u+(uint64_t)t.tv_nsec/1000000u;
}
static uint64_t stream_wall_us(void) {
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;
    return (uint64_t)t.tv_sec*1000000u+(uint64_t)t.tv_nsec/1000u;
}
static void capture_stage(const xqvoice_capture_control *control,unsigned phase) {
    if(control && control->stage)control->stage(control->context,phase);
    else {puts(phase==XQV_CAPTURE_LISTENING?"XQVOICE_STAGE LISTENING":phase==XQV_CAPTURE_SPEECH?"XQVOICE_STAGE SPEECH":"XQVOICE_STAGE INFERENCING");fflush(stdout);}
}
static int capture_features(const char *device,uint8_t **input,size_t *bytes,int listen,const xqvoice_capture_control *control,xqvoice_stream_metrics *metrics) {
    struct pango_audio_info info;struct pango_audio_stats stats;
    xqvoice_capture_state state;int fd=-1,lock=-1,rc=-25;int16_t *samples=NULL;uint8_t *out=NULL,chunk[320];
    unsigned frames=0;size_t used=0;uint64_t deadline;struct timespec idle={0,500000};
    struct sigaction stop_action,previous_stop;int stop_installed=0;
    uint64_t capture_started=xqvp_now(),feature_started;
    if(metrics){memset(metrics,0,sizeof(*metrics));metrics->started_us=stream_wall_us();metrics->paced=1;}
    if(control && (!control->hop_samples || control->hop_samples>400u))return -27;
    if(control && control->cancel && control->cancel(control->context))return -26;
    lock=open("/run/xqvoice-audio.lock",O_CREAT|O_RDWR|O_CLOEXEC,0600);
    if(lock<0 || flock(lock,LOCK_EX|LOCK_NB))goto done;
    rc=-20;fd=open(device,O_RDONLY|O_NONBLOCK|O_CLOEXEC);
    if(fd<0)goto done;
    memset(&info,0,sizeof(info));
    if(ioctl(fd,PANGO_AUDIO_IOC_GET_INFO,&info)<0 || info.abi_version!=PANGO_AUDIO_ABI_VERSION ||
       info.device_id!=PANGO_AUDIO_ID || info.device_version!=PANGO_AUDIO_VERSION || info.sample_rate_hz!=16000 ||
       info.channels!=1 || info.sample_format!=PANGO_AUDIO_FORMAT_S16_LE || info.fifo_samples!=512u)goto done;
    if(ioctl(fd,PANGO_AUDIO_IOC_CLEAR)<0)goto done;
    samples=(int16_t*)malloc(64000u*sizeof(int16_t));out=(uint8_t*)malloc(4u+400u*40u);
    if(!samples || !out)goto done;
    xqvoice_capture_init(&state,samples,64000u);state.listen=listen;deadline=now_ms();
    if(deadline==UINT64_MAX){rc=-23;goto done;}
    deadline+=10000u;
    memset(&stop_action,0,sizeof(stop_action));stop_action.sa_handler=stop_capture;
    sigemptyset(&stop_action.sa_mask);manual_stop=0;
    if(sigaction(SIGUSR1,&stop_action,&previous_stop)){rc=-24;goto done;}
    stop_installed=1;
    if(listen)capture_stage(control,XQV_CAPTURE_LISTENING);
    else {puts("XQVOICE_STAGE CAPTURING");fflush(stdout);}
    for(;;) {
        if(control && control->cancel && control->cancel(control->context)){rc=-26;goto done;}
        uint64_t tick=now_ms();
        if(tick==UINT64_MAX || ((!listen || state.active) && tick>=deadline)){rc=-23;goto done;}
        if(manual_stop){rc=xqvoice_capture_finish(&state);if(rc<0)goto done;break;}
        ssize_t n=read(fd,chunk+used,sizeof(chunk)-used);
        if(n>0)used+=(size_t)n;
        else if(n<0 && (errno==EAGAIN || errno==EWOULDBLOCK)){nanosleep(&idle,NULL);continue;}
        else if(n<0 && errno==EINTR)continue;
        else {rc=-21;goto done;}
        if(used==sizeof(chunk)) {
            int16_t decoded[160];unsigned i;int was_active=state.active;
            for(i=0;i<160;i++){unsigned v=(unsigned)chunk[2*i]|((unsigned)chunk[2*i+1]<<8);decoded[i]=(int16_t)(v<32768u?(int)v:(int)v-65536);}
            memset(&stats,0,sizeof(stats));
            if(ioctl(fd,PANGO_AUDIO_IOC_GET_STATS,&stats)<0 || stats.abi_version!=PANGO_AUDIO_ABI_VERSION || stats.fifo_overflows){rc=-22;goto done;}
            rc=xqvoice_capture_feed(&state,decoded);used=0;
            if(metrics && state.active && !state.quiet)metrics->last_voice_us=stream_wall_us();
            if(listen && !was_active && state.active) {
                deadline=tick+10000u;
                capture_stage(control,XQV_CAPTURE_SPEECH);
            }
            if(rc<0)goto done;
            if(rc==2)break;
        }
    }
    if(state.done!=2){rc=-23;goto done;}
    memset(&stats,0,sizeof(stats));
    if(ioctl(fd,PANGO_AUDIO_IOC_GET_STATS,&stats)<0 || stats.abi_version!=PANGO_AUDIO_ABI_VERSION || stats.fifo_overflows){rc=-22;goto done;}
    close(fd);fd=-1; /* Finish capture before any feature extraction/inference. */
    close(lock);lock=-1;
    xqvp_add(XQVP_CAPTURE,xqvp_now()-capture_started);capture_started=0;
    xqvp_capture_ended();
    if(metrics)metrics->endpoint_us=stream_wall_us();
    capture_stage(control,XQV_CAPTURE_INFER);
    feature_started=xqvp_now();
    if(control) {
        unsigned f;
        frames=(unsigned)((state.count-400u)/control->hop_samples+1u);
        if(frames>400u){rc=-27;goto done;}
        for(f=0;f<frames;f++) {
            unsigned one=0;
            if(control->cancel && control->cancel(control->context)){rc=-26;goto done;}
            rc=xqvoice_frontend(samples+(size_t)f*control->hop_samples,400u,(int8_t*)(out+4u+f*40u),40u,&one);
            if(rc || one!=1){rc=-27;goto done;}
        }
    }else rc=xqvoice_frontend(samples,state.count,(int8_t*)(out+4),400u*40u,&frames);
    xqvp_add(XQVP_FEATURE,xqvp_now()-feature_started);
    if(rc)goto done;
    out[0]=(uint8_t)frames;out[1]=(uint8_t)(frames>>8);out[2]=(uint8_t)(frames>>16);out[3]=(uint8_t)(frames>>24);
    *input=out;*bytes=4u+frames*40u;out=NULL;rc=0;
    if(metrics){metrics->features_done_us=stream_wall_us();metrics->frames=metrics->max_backlog_frames=frames;}
done:
    if(capture_started)xqvp_add(XQVP_CAPTURE,xqvp_now()-capture_started);
    if(stop_installed)(void)sigaction(SIGUSR1,&previous_stop,NULL);
    if(fd>=0)close(fd);
    if(lock>=0)close(lock);
    free(samples);free(out);return rc;
}
#include "xqvoice_stream.inc"
int xqvoice_capture_features(const char *device,uint8_t **input,size_t *bytes) {
    return xqvoice_live_features(device,input,bytes,0,NULL);
}
int xqvoice_listen_features(const char *device,uint8_t **input,size_t *bytes) {
    return xqvoice_live_features(device,input,bytes,1,NULL);
}
int xqvoice_capture_controlled(const char *device,uint8_t **input,size_t *bytes,const xqvoice_capture_control *control) {
    return xqvoice_capture_controlled_metrics(device,input,bytes,control,NULL);
}
int xqvoice_capture_controlled_metrics(const char *device,uint8_t **input,size_t *bytes,
        const xqvoice_capture_control *control,xqvoice_stream_metrics *metrics) {
    const char *stream=getenv("XQVOICE_STREAM_FEATURES");
    if(stream && !strcmp(stream,"0"))return capture_features(device,input,bytes,1,control,metrics);
    return stream_features(device,input,bytes,control,1,metrics,NULL,0,1);
}
int xqvoice_live_features(const char *device,uint8_t **input,size_t *bytes,int listen,xqvoice_stream_metrics *metrics) {
    const char *stream=getenv("XQVOICE_STREAM_FEATURES");
    xqvoice_capture_control control={NULL,NULL,NULL,XQV_HOP_SAMPLES};
    if(stream && !strcmp(stream,"0"))return capture_features(device,input,bytes,listen,&control,metrics);
    return stream_features(device,input,bytes,&control,listen,metrics,NULL,0,1);
}
int xqvoice_replay_features(const uint8_t *wav,size_t size,uint8_t **input,size_t *bytes,
                          int stream,int paced,xqvoice_stream_metrics *metrics) {
    int16_t *pcm=NULL;size_t samples=0;int rc;unsigned frames=0;uint8_t *out;
    xqvoice_capture_control control={NULL,NULL,NULL,XQV_HOP_SAMPLES};
    if(!input || !bytes || !metrics || (stream!=0 && stream!=1) || (paced!=0 && paced!=1))return -27;
    memset(metrics,0,sizeof(*metrics));
    rc=xqvoice_wav_pcm(wav,size,&pcm,&samples);if(rc)return rc;
    if(stream){rc=stream_features(NULL,input,bytes,&control,0,metrics,pcm,samples,paced);free(pcm);return rc;}
    metrics->started_us=stream_wall_us();metrics->paced=(unsigned)paced;
    if(paced && replay_wait_until(metrics->started_us+(uint64_t)samples*1000000u/16000u,NULL)){
        free(pcm);return -23;
    }
    metrics->endpoint_us=metrics->last_voice_us=stream_wall_us();xqvp_capture_ended();
    out=malloc(4u+400u*40u);if(!out){free(pcm);return -25;}
    uint64_t stamp=xqvp_now();
    rc=xqvoice_frontend(pcm,samples,(int8_t*)(out+4),400u*40u,&frames);
    xqvp_add(XQVP_FEATURE,xqvp_now()-stamp);free(pcm);
    if(rc){free(out);return rc;}
    out[0]=(uint8_t)frames;out[1]=(uint8_t)(frames>>8);out[2]=(uint8_t)(frames>>16);out[3]=(uint8_t)(frames>>24);
    *input=out;*bytes=4u+frames*40u;
    metrics->features_done_us=stream_wall_us();metrics->frames=metrics->max_backlog_frames=frames;
    return 0;
}
#else
int xqvoice_capture_features(const char *d,uint8_t **i,size_t *b){(void)d;(void)i;(void)b;return -99;}
int xqvoice_listen_features(const char *d,uint8_t **i,size_t *b){(void)d;(void)i;(void)b;return -99;}
int xqvoice_capture_controlled(const char *d,uint8_t **i,size_t *b,const xqvoice_capture_control *c){(void)d;(void)i;(void)b;(void)c;return -99;}
int xqvoice_capture_controlled_metrics(const char *d,uint8_t **i,size_t *b,const xqvoice_capture_control *c,xqvoice_stream_metrics *m){(void)d;(void)i;(void)b;(void)c;(void)m;return -99;}
#endif
