#define _POSIX_C_SOURCE 200809L
#include "xqvoice_accel.h"
#include "xqvoice_features.h"
/* Keep the original dense/rounding code as the independent board oracle. */
#include "xqvoice_model.c"
#include <time.h>

static uint64_t nanoseconds(void)
{struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000u+t.tv_nsec;}
static int compare_layers(const xqvoice_model_t *m,const struct pango_voice_infer *job)
{
    int8_t outputs[121];
    dense(job->input,40,m->weight1,m->bias1,64,m->shift1,1,outputs);
    dense(outputs,64,m->weight2,m->bias2,32,m->shift2,1,outputs+64);
    dense(outputs+64,32,m->weight3,m->bias3,25,m->shift3,0,outputs+96);
    return !memcmp(outputs,job->outputs,sizeof(outputs));
}
int main(int argc,char **argv)
{
    xqvoice_model_t model;xqvoice_accel_t accel;
    int16_t pcm[XQVOICE_MAX_SAMPLES];
    int8_t reference[XQVOICE_MAX_FRAMES*20];
    int8_t hardware_features[XQVOICE_MAX_FRAMES*20];
    char error[128];FILE *in;
    size_t samples,frames,f;unsigned repeat,index,bin;uint32_t mode=0;
    uint64_t cpu_total=0,hw_total=0;
    if(argc<3 || argc>4){fprintf(stderr,"usage: %s SD77.xqt input.s16le [repeats]\n",argv[0]);return 2;}
    repeat=argc==4?(unsigned)strtoul(argv[3],NULL,10):10;
    if(!repeat || repeat>1000)return 2;
    if(!xqvoice_model_load(argv[1],&model,error,sizeof(error))){fprintf(stderr,"%s\n",error);return 3;}
    in=fopen(argv[2],"rb");if(!in)return 4;
    samples=fread(pcm,sizeof(*pcm),XQVOICE_MAX_SAMPLES,in);
    if(samples<400 || fgetc(in)!=EOF || ferror(in)){fclose(in);return 4;}fclose(in);
    if(!xqvoice_accel_open(&accel,"/dev/pango-voice0",&model) || ioctl(accel.fd,PANGO_VOICE_IOC_MODE,&mode))return 5;
    for(index=0;index<repeat;index++){
        struct pango_voice_infer job;
        uint8_t cpu_token=0;uint16_t cpu_confidence=0;int cpu_ok;
        uint64_t begin=nanoseconds(),cpu_ns,hw_ns;
        frames=xqvoice_extract_features(pcm,samples,&model,reference,sizeof(reference));
        cpu_ok=xqvoice_model_infer_token(&model,reference,frames,&cpu_token,&cpu_confidence,error,sizeof(error));
        cpu_ns=nanoseconds()-begin;
        begin=nanoseconds();
        for(f=0;f<frames;f++){
            struct pango_voice_frame frame;
            memset(&frame,0,sizeof(frame));memcpy(frame.samples,pcm+f*160,800);frame.timeout_us=100000;
            if(ioctl(accel.fd,PANGO_VOICE_IOC_FRAME,&frame)){
                fprintf(stderr,"VOICE_BOARD_MISMATCH frame=%u\n",(unsigned)f);return 6;
            }
            memcpy(hardware_features+f*20,frame.features,20);
        }
        memset(&job,0,sizeof(job));job.timeout_us=100000;
        for(bin=0;bin<20;bin++){
            int sum=0,maximum=-128;
            for(f=0;f<frames;f++){int value=hardware_features[f*20+bin];sum+=value;if(value>maximum)maximum=value;}
            job.input[bin]=(int8_t)(sum/(int)frames);job.input[20+bin]=(int8_t)maximum;
        }
        if(ioctl(accel.fd,PANGO_VOICE_IOC_INFER,&job))return 7;
        hw_ns=nanoseconds()-begin;
        if(memcmp(hardware_features,reference,frames*20))return 6;
        /* Trace reads are correctness work outside the production timing. */
        job.flags=1;
        if(ioctl(accel.fd,PANGO_VOICE_IOC_INFER,&job))return 7;
        if(!compare_layers(&model,&job) || (cpu_ok && (job.token!=cpu_token || job.confidence!=cpu_confidence)) ||
           (!cpu_ok && job.token!=0))return 8;
        cpu_total+=cpu_ns;hw_total+=hw_ns;
        printf("VOICE_BOARD_SAMPLE index=%u frames=%u cpu_ns=%llu hardware_manual_ns=%llu class_cycles=%u token=%u confidence=%u\n",
               index,(unsigned)frames,(unsigned long long)cpu_ns,(unsigned long long)hw_ns,job.cycles,job.token,job.confidence);
    }
    printf("VOICE_BOARD_EXACT_PASS repeats=%u cpu_total_ns=%llu hardware_manual_total_ns=%llu scope=offline_same_pcm_including_ioctls\n",
           repeat,(unsigned long long)cpu_total,(unsigned long long)hw_total);
    xqvoice_accel_close(&accel);xqvoice_model_unload(&model);return 0;
}
