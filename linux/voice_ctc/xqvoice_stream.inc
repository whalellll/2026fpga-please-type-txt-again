/* One producer drains PCM; one consumer computes immutable, complete frames.
   Only the producer touches the control protocol while it is running. */
#include <pthread.h>
#include <stdatomic.h>
typedef struct {
    pthread_mutex_t mutex;
    pthread_cond_t changed;
    const char *device;
    const xqvoice_capture_control *control;
    xqvoice_capture_state state;
    size_t available;
    int complete,rc;
    atomic_int abort;
    const int16_t *replay;
    size_t replay_samples;
    int paced;
    xqvoice_stream_metrics *metrics;
} CaptureStream;
static int replay_wait_until(uint64_t deadline,CaptureStream *s) {
    struct timespec target={(time_t)(deadline/1000000u),(long)(deadline%1000000u)*1000};
    int rc;
    do {
        if(s && atomic_load_explicit(&s->abort,memory_order_relaxed))return -26;
        rc=clock_nanosleep(CLOCK_MONOTONIC,TIMER_ABSTIME,&target,NULL);
    }while(rc==EINTR);
    return rc?-23:0;
}
static void stream_publish(CaptureStream *s,int complete,int rc) {
    size_t safe=s->state.count;
    /* Endpoint removes quiet audio after the first 120ms. Do not compute
       frames using that provisional tail, even during an internal pause. */
    if(s->state.active && s->state.done!=2 && s->state.quiet>12u)
        safe-=(s->state.quiet-12u)*160u;
    pthread_mutex_lock(&s->mutex);
    int changed=s->state.active && safe>s->available;
    if(changed)s->available=safe;
    s->complete=complete;s->rc=rc;
    if(changed || complete)pthread_cond_signal(&s->changed);
    pthread_mutex_unlock(&s->mutex);
}
static void *stream_reader(void *context) {
    CaptureStream *s=context;const xqvoice_capture_control *c=s->control;
    int fd=-1,lock=-1,rc=-25;size_t used=0;uint8_t chunk[320];
    struct pango_audio_info info;struct pango_audio_stats stats;
    uint64_t deadline=0,capture_started=xqvp_now();struct timespec idle={0,500000};
#if XINYI_BATTLE_R17
    uint64_t utterance_candidate=0;
#endif
    if(c->cancel && c->cancel(c->context)){rc=-26;goto done;}
    lock=open("/run/xqvoice-audio.lock",O_CREAT|O_RDWR|O_CLOEXEC,0600);
    if(lock<0 || flock(lock,LOCK_EX|LOCK_NB))goto done;
    rc=-20;fd=open(s->device,O_RDONLY|O_NONBLOCK|O_CLOEXEC);if(fd<0)goto done;
    memset(&info,0,sizeof(info));
    if(ioctl(fd,PANGO_AUDIO_IOC_GET_INFO,&info)<0 || info.abi_version!=PANGO_AUDIO_ABI_VERSION ||
       info.device_id!=PANGO_AUDIO_ID || info.device_version!=PANGO_AUDIO_VERSION || info.sample_rate_hz!=16000 ||
       info.channels!=1 || info.sample_format!=PANGO_AUDIO_FORMAT_S16_LE || info.fifo_samples!=512u)goto done;
    if(ioctl(fd,PANGO_AUDIO_IOC_CLEAR)<0)goto done;
    deadline=now_ms();if(deadline==UINT64_MAX){rc=-23;goto done;}deadline+=10000u;
    capture_stage(c,XQV_CAPTURE_LISTENING);
    for(;;) {
        uint64_t tick;ssize_t n;
        if(atomic_load_explicit(&s->abort,memory_order_relaxed) || (c->cancel && c->cancel(c->context))){rc=-26;goto done;}
        tick=now_ms();if(tick==UINT64_MAX || ((!s->state.listen || s->state.active) && tick>=deadline)){rc=-23;goto done;}
        if(manual_stop){rc=xqvoice_capture_finish(&s->state);if(rc<0)goto done;break;}
        n=read(fd,chunk+used,sizeof(chunk)-used);
        if(n>0)used+=(size_t)n;
        else if(n<0 && (errno==EAGAIN || errno==EWOULDBLOCK)){nanosleep(&idle,NULL);continue;}
        else if(n<0 && errno==EINTR)continue;
        else {rc=-21;goto done;}
        if(used==sizeof(chunk)) {
            int16_t decoded[160];int was_active=s->state.active;
            for(unsigned i=0;i<160;i++){unsigned v=(unsigned)chunk[2u*i]|((unsigned)chunk[2u*i+1u]<<8);decoded[i]=(int16_t)(v<32768u?(int)v:(int)v-65536);}
            memset(&stats,0,sizeof(stats));
            if(ioctl(fd,PANGO_AUDIO_IOC_GET_STATS,&stats)<0 || stats.abi_version!=PANGO_AUDIO_ABI_VERSION || stats.fifo_overflows){rc=-22;goto done;}
            rc=xqvoice_capture_feed(&s->state,decoded);used=0;
#if XINYI_BATTLE_R17
            capture_utterance_start(s->metrics,&s->state,was_active,&utterance_candidate,stream_wall_us());
#endif
            if(s->metrics && s->state.active && !s->state.quiet)s->metrics->last_voice_us=stream_wall_us();
            if(!was_active && s->state.active){deadline=tick+10000u;capture_stage(c,XQV_CAPTURE_SPEECH);}
            if(rc<0)goto done;
            stream_publish(s,0,0);if(rc==2)break;
        }
    }
    if(s->state.done!=2){rc=-23;goto done;}
    memset(&stats,0,sizeof(stats));
    if(ioctl(fd,PANGO_AUDIO_IOC_GET_STATS,&stats)<0 || stats.abi_version!=PANGO_AUDIO_ABI_VERSION || stats.fifo_overflows){rc=-22;goto done;}
    rc=0;
done:
    if(rc)atomic_store_explicit(&s->abort,1,memory_order_relaxed);
    if(fd>=0)close(fd);
    if(lock>=0)close(lock);
    xqvp_add(XQVP_CAPTURE,xqvp_now()-capture_started);xqvp_capture_ended();
    if(s->metrics)s->metrics->endpoint_us=stream_wall_us();
    if(!rc)capture_stage(c,XQV_CAPTURE_INFER);
    stream_publish(s,1,rc);return NULL;
}
static void *stream_replay_reader(void *context) {
    CaptureStream *s=context;size_t at=0;int rc=0;
    uint64_t began=stream_wall_us();
    if(s->metrics)s->metrics->started_us=began;
    while(at<s->replay_samples){
        size_t n=s->replay_samples-at;if(n>160u)n=160u;
        if(atomic_load_explicit(&s->abort,memory_order_relaxed)){rc=-26;break;}
        if(s->paced && (rc=replay_wait_until(began+(uint64_t)(at+n)*1000000u/16000u,s)))break;
        memcpy(s->state.samples+at,s->replay+at,n*sizeof(*s->replay));
        at+=n;s->state.count=at;stream_publish(s,0,0);
    }
    s->state.done=rc?rc:2;
    if(s->metrics)s->metrics->endpoint_us=s->metrics->last_voice_us=stream_wall_us();
    xqvp_capture_ended();stream_publish(s,1,rc);return NULL;
}
static int stream_features(const char *device,uint8_t **input,size_t *bytes,const xqvoice_capture_control *control,
                           int listen,xqvoice_stream_metrics *metrics,const int16_t *replay,size_t replay_samples,int paced) {
    CaptureStream s;pthread_t reader;struct sigaction action,previous;
    int16_t *samples=NULL;uint8_t *out=NULL;unsigned frames=0;int rc=-28,feature_error=0;
    if(!control || !control->hop_samples || control->hop_samples>400u)return -27;
    memset(&s,0,sizeof(s));s.device=device;s.control=control;s.replay=replay;s.replay_samples=replay_samples;s.paced=paced;s.metrics=metrics;atomic_init(&s.abort,0);
    if(metrics){memset(metrics,0,sizeof(*metrics));metrics->started_us=stream_wall_us();metrics->streamed=1;metrics->paced=(unsigned)paced;}
    if(pthread_mutex_init(&s.mutex,NULL))return -28;
    if(pthread_cond_init(&s.changed,NULL)){pthread_mutex_destroy(&s.mutex);return -28;}
    samples=malloc(64240u*sizeof(*samples));out=malloc(4u+400u*40u);
    if(!samples || !out)goto destroy;
    xqvoice_capture_init(&s.state,samples,replay?64240u:64000u);s.state.listen=listen;s.state.active=replay!=NULL;
    memset(&action,0,sizeof(action));action.sa_handler=stop_capture;sigemptyset(&action.sa_mask);manual_stop=0;
    if(sigaction(SIGUSR1,&action,&previous)){rc=-24;goto destroy;}
    if(pthread_create(&reader,NULL,replay?stream_replay_reader:stream_reader,&s)){sigaction(SIGUSR1,&previous,NULL);goto destroy;}
    for(;;) {
        size_t safe;int complete;
        pthread_mutex_lock(&s.mutex);
        while(!s.complete && (atomic_load_explicit(&s.abort,memory_order_relaxed) || (size_t)frames*control->hop_samples+400u>s.available))
            pthread_cond_wait(&s.changed,&s.mutex);
        safe=s.available;complete=s.complete;pthread_mutex_unlock(&s.mutex);
        if(metrics && safe>=400u){
            unsigned ready=(unsigned)((safe-400u)/control->hop_samples+1u);
            if(ready>=frames && ready-frames>metrics->max_backlog_frames)metrics->max_backlog_frames=ready-frames;
        }
        while(!atomic_load_explicit(&s.abort,memory_order_relaxed) && (size_t)frames*control->hop_samples+400u<=safe) {
            unsigned one=0;uint64_t began=xqvp_now();
            if(frames>=400u)feature_error=-27;
            else {
                int f=xqvoice_frontend(samples+(size_t)frames*control->hop_samples,400u,(int8_t *)(out+4u+frames*40u),40u,&one);
                if(f || one!=1u)feature_error=-27;else frames++;
            }
            xqvp_add(XQVP_FEATURE,xqvp_now()-began);
            if(feature_error)atomic_store_explicit(&s.abort,1,memory_order_relaxed);
        }
        if(complete)break;
    }
    pthread_join(reader,NULL);sigaction(SIGUSR1,&previous,NULL);rc=feature_error?feature_error:s.rc;
    if(!rc) {
        unsigned expected=s.state.count>=400u?(unsigned)((s.state.count-400u)/control->hop_samples+1u):0;
        if(frames!=expected || !frames)rc=-27;
        else {
            out[0]=(uint8_t)frames;out[1]=(uint8_t)(frames>>8);out[2]=(uint8_t)(frames>>16);out[3]=(uint8_t)(frames>>24);
            *input=out;*bytes=4u+frames*40u;out=NULL;
            if(metrics){metrics->features_done_us=stream_wall_us();metrics->frames=frames;}
        }
    }
destroy:
    pthread_cond_destroy(&s.changed);pthread_mutex_destroy(&s.mutex);free(samples);free(out);return rc;
}
