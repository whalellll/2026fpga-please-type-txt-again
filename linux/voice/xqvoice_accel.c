#include "xqvoice_accel.h"
#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <unistd.h>

int xqvoice_accel_open(xqvoice_accel_t *a,const char *path,const xqvoice_model_t *m)
{
    struct pango_voice_info info;
    uint32_t mode=1;
    memset(a,0,sizeof(*a));a->fd=-1;
    if(!m || m->image_bytes!=PANGO_VOICE_MODEL_BYTES){errno=EINVAL;return 0;}
    a->fd=open(path,O_RDWR);
    if(a->fd<0)return 0;
    memset(&info,0,sizeof(info));
    if(ioctl(a->fd,PANGO_VOICE_IOC_INFO,&info) || info.abi_version!=PANGO_VOICE_ABI ||
       info.device_id!=PANGO_VOICE_ID || info.device_version!=PANGO_VOICE_VERSION ||
       info.sample_rate!=16000 || info.window_samples!=400 || info.hop_samples!=160 ||
       info.queue_frames!=16 || info.model_bytes!=m->image_bytes ||
       ioctl(a->fd,PANGO_VOICE_IOC_MODEL,m->image) || ioctl(a->fd,PANGO_VOICE_IOC_MODE,&mode)){
        int saved=errno;close(a->fd);a->fd=-1;errno=saved?saved:EPROTO;return 0;
    }
    return 1;
}

int xqvoice_accel_accept(xqvoice_accel_t *a,const struct pango_voice_stream *s)
{
    unsigned i;
    if(s->feature_count>16 || s->level_count>16){errno=EPROTO;return 0;}
    a->overflows=s->overflows;
    for(i=0;i<s->feature_count;i++){
        const struct pango_voice_feature *f=&s->frames[i];
        if(f->end_sample<400 || (f->end_sample-400)%160){errno=EPROTO;return 0;}
        if(a->last_feature_end && (f->end_sample!=a->last_feature_end+160 ||
                                  f->sequence!=a->last_sequence+1))
            ++a->discontinuities;
        a->history[((f->end_sample-400)/160)%XQVOICE_ACCEL_HISTORY]=*f;
        a->last_feature_end=f->end_sample;a->last_sequence=f->sequence;
    }
    a->pending=*s;a->level_index=0;
    return 1;
}

int xqvoice_accel_level(xqvoice_accel_t *a,uint32_t *level,uint32_t *end_sample)
{
    while(a->level_index==a->pending.level_count){
        struct pango_voice_stream stream;
        memset(&stream,0,sizeof(stream));stream.abi_version=1;stream.timeout_us=10000;
        if(ioctl(a->fd,PANGO_VOICE_IOC_STREAM,&stream)<0)return 0;
        if(!xqvoice_accel_accept(a,&stream))return 0;
    }
    *level=a->pending.levels[a->level_index].mean_absolute;
    *end_sample=a->pending.levels[a->level_index++].end_sample;
    if(*end_sample!=a->last_end+160)++a->discontinuities;
    a->last_end=*end_sample;
    return 1;
}

size_t xqvoice_accel_features(const xqvoice_accel_t *a,uint32_t begin,uint32_t end,
                            int8_t *values,size_t bytes)
{
    uint32_t frame_end;
    size_t count=0,expected;
    if(end<begin || end-begin<400 || begin%160)return 0;
    expected=(end-begin-400)/160+1;
    if(expected>XQVOICE_MAX_FRAMES || bytes<expected*20)return 0;
    for(frame_end=begin+400;frame_end<=end;frame_end+=160){
        const struct pango_voice_feature *f=&a->history[((frame_end-400)/160)%XQVOICE_ACCEL_HISTORY];
        if(f->end_sample!=frame_end)return 0;
        memcpy(values+count*20,f->values,20);++count;
    }
    return count;
}

int xqvoice_accel_infer(xqvoice_accel_t *a,const int8_t *values,size_t frames,
                       uint8_t *token,uint16_t *confidence)
{
    struct pango_voice_infer job;
    unsigned bin;
    size_t frame;
    if(!frames || frames>XQVOICE_MAX_FRAMES){errno=EINVAL;return 0;}
    memset(&job,0,sizeof(job));job.timeout_us=100000;
    for(bin=0;bin<20;bin++){
        int32_t sum=0;
        int8_t maximum=-128;
        for(frame=0;frame<frames;frame++){
            int8_t value=values[frame*20+bin];sum+=value;
            if(value>maximum)maximum=value;
        }
        job.input[bin]=(int8_t)(sum/(int32_t)frames);job.input[20+bin]=maximum;
    }
    if(ioctl(a->fd,PANGO_VOICE_IOC_INFER,&job)<0)return 0;
    if(!job.token || (job.status&4)){errno=ERANGE;return 0;}
    *token=job.token;*confidence=job.confidence;return 1;
}

void xqvoice_accel_close(xqvoice_accel_t *a)
{
    if(a->fd>=0){uint32_t mode=0;(void)ioctl(a->fd,PANGO_VOICE_IOC_MODE,&mode);close(a->fd);a->fd=-1;}
}
