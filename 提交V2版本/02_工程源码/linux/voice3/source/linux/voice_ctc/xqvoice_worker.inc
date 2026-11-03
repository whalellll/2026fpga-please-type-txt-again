/* Private resident protocol. One outstanding request; no microphone while idle. */
#if defined(__linux__)
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdarg.h>
#include <unistd.h>
#include <stdatomic.h>
typedef struct {char kind;uint32_t id;char path[1024];} WorkerCommand;
typedef struct {
    char bytes[2200];size_t used;
    uint32_t active,last;
    int cancelled,quit,protocol_error;
} WorkerControl;
_Static_assert(ATOMIC_INT_LOCK_FREE==2,"Worker signal flag must be lock-free");
static atomic_int worker_stop;
static void worker_signal(int signum){(void)signum;worker_stop=1;}
static int worker_emit(WorkerControl *w,const char *format,...) {
    va_list args;int rc;
    va_start(args,format);rc=vprintf(format,args);va_end(args);
    if(rc<0 || fflush(stdout)){w->quit=1;return -1;}return 0;
}
static int unhex(const char *s,char *out,size_t capacity) {
    size_t n=strlen(s),i;
    if(!n || (n&1u) || n/2u>=capacity)return 0;
    for(i=0;i<n;i+=2u) {
        unsigned value=0,j;
        for(j=0;j<2;j++) {
            unsigned c=(unsigned char)s[i+j],v;
            if(c>='0' && c<='9')v=c-'0';
            else if(c>='a' && c<='f')v=c-'a'+10u;
            else if(c>='A' && c<='F')v=c-'A'+10u;
            else return 0;
            value=value*16u+v;
        }
        if(!value)return 0;
        out[i/2u]=(char)value;
    }
    out[n/2u]=0;return 1;
}
static int worker_command(char *line,WorkerCommand *command) {
    char *state=NULL,*prefix=strtok_r(line," ",&state),*kind=strtok_r(NULL," ",&state);
    char *id=strtok_r(NULL," ",&state),*path=strtok_r(NULL," ",&state),*end;
    unsigned long long value;
    if(!prefix || strcmp(prefix,"XQW1") || !kind || strlen(kind)!=1u || !strchr("LWVCQ",kind[0]) ||
       !id || !*id || strlen(id)>10u || !path || strtok_r(NULL," ",&state))return 0;
    for(end=id;*end;end++)if(*end<'0' || *end>'9')return 0;
    errno=0;value=strtoull(id,&end,10);
    if(errno || *end || value>UINT32_MAX)return 0;
    command->kind=kind[0];command->id=(uint32_t)value;command->path[0]=0;
    if(command->kind=='Q')return !value && !strcmp(path,"-");
    if(!value)return 0;
    if(command->kind=='C')return !strcmp(path,"-");
    return unhex(path,command->path,sizeof(command->path));
}
/* 1 complete, 0 would block, -1 EOF/fatal. Partial frames remain bounded. */
static int worker_next(WorkerControl *w,WorkerCommand *command) {
    for(;;) {
        char *end=memchr(w->bytes,'\n',w->used);
        if(end) {
            size_t n=(size_t)(end-w->bytes);char line[2200];
            if(memchr(w->bytes,0,n)){w->protocol_error=w->quit=1;return -1;}
            memcpy(line,w->bytes,n);line[n]=0;
            memmove(w->bytes,w->bytes+n+1,w->used-n-1);w->used-=n+1;
            if(!worker_command(line,command)){w->protocol_error=w->quit=1;return -1;}
            return 1;
        }
        if(w->used==sizeof(w->bytes)-1u){w->protocol_error=w->quit=1;return -1;}
        {
            ssize_t n=read(STDIN_FILENO,w->bytes+w->used,sizeof(w->bytes)-1u-w->used);
            if(n>0){w->used+=(size_t)n;continue;}
            if(!n){w->quit=1;return -1;}
            if(errno==EINTR){if(worker_stop){w->quit=1;return -1;}continue;}
            if(errno==EAGAIN || errno==EWOULDBLOCK)return 0;
            w->quit=1;return -1;
        }
    }
}
static int worker_cancel(void *context) {
    WorkerControl *w=context;WorkerCommand command;int result;
    if(worker_stop)w->quit=1;
    while(!w->quit && (result=worker_next(w,&command))>0) {
        if(command.kind=='Q')w->quit=1;
        else if(command.kind=='C'){if(command.id==w->active)w->cancelled=1;}
        else {w->protocol_error=w->quit=1;}
    }
    return w->cancelled || w->quit;
}
static void worker_stage(void *context,unsigned phase) {
    WorkerControl *w=context;
    worker_emit(w,"XQW1 STAGE %u %s\n",w->active,
        phase==XQV_CAPTURE_LISTENING?"LISTENING":phase==XQV_CAPTURE_SPEECH?"CAPTURING":"INFERENCING");
}
static int worker_main(int argc,char **argv) {
    WorkerControl control={0};uint8_t *model=NULL;size_t model_bytes=0;
    unsigned long loads=0,opens=0;int code=0,flags;
    uint64_t startup=timestamp_us();const char *trace_path;
    if(argc!=5)return 1;
    if(!strcmp(argv[3],"cpu"))backend=0;
    else if(!strcmp(argv[3],"mac"))backend=1;
    else if(!strcmp(argv[3],"mac-verify"))backend=2;
    else return 1;
    trace_path=argv[4];setvbuf(stdout,NULL,_IOLBF,0);
    (void)signal(SIGPIPE,SIG_IGN);(void)signal(SIGTERM,worker_signal);(void)signal(SIGINT,worker_signal);
    (void)signal(SIGUSR1,SIG_IGN);worker_stop=0;xqvp_init();
    model=read_file(argv[2],&model_bytes);loads++;
    if(!model){code=3;goto failed_start;}
    code=validate_model(model,model_bytes);if(code)goto failed_start;
    trusted_model=model;trusted_model_size=model_bytes;
    if(backend){code=xqvoice_mac_open();if(code){code=6;goto failed_start;}opens++;}
    flags=fcntl(STDIN_FILENO,F_GETFL,0);
    if(flags<0 || fcntl(STDIN_FILENO,F_SETFL,flags|O_NONBLOCK)){code=90;goto failed_start;}
    worker_emit(&control,"XQW1 READY pid=%ld model_loads=%lu model_checks=%lu mac_opens=%lu startup_us=%llu\n",
        (long)getpid(),loads,model_validation_count,opens,(unsigned long long)(timestamp_us()-startup));
    request_cancel=worker_cancel;request_cancel_context=&control;
    while(!control.quit && !worker_stop) {
        WorkerCommand command;int next=worker_next(&control,&command);
        uint8_t *input=NULL;size_t input_bytes=0;char text[32]={0},hex[65];FILE *trace=NULL;
        uint64_t began,cnn_begin=0,decode_begin=0,finished=0,stamp;
        xqvoice_stream_metrics metrics={0};unsigned tail_valid;
        unsigned long long jobs_before,cycles_before;
        if(next<0)break;
        if(!next){struct pollfd p={STDIN_FILENO,POLLIN,0};(void)poll(&p,1,100);continue;}
        if(command.kind=='Q')break;
        if(command.kind=='C')continue; /* A late cancellation cannot cancel another request. */
        if(command.id<=control.last){control.protocol_error=1;code=91;break;}
        control.last=control.active=command.id;control.cancelled=0;
        began=timestamp_us();xqvp_reset();final_frames=0;
        jobs_before=xqvoice_mac_jobs();cycles_before=xqvoice_mac_cycles();
        if(worker_cancel(&control))code=26;
        else if(command.kind=='L') {
            xqvoice_capture_control capture={worker_cancel,worker_stage,&control,XQV_HOP_SAMPLES};
            code=xqvoice_capture_controlled_metrics(command.path,&input,&input_bytes,&capture,&metrics);
            if(code==-26)code=26;
        }else {
            worker_stage(&control,XQV_CAPTURE_INFER);
            input=read_file(command.path,&input_bytes);code=input?0:3;
            if(!code && command.kind=='W') {
                uint8_t *features=NULL;size_t bytes=0;stamp=xqvp_now();
                code=xqvoice_wav_features(input,input_bytes,&features,&bytes);
                xqvp_add(XQVP_FEATURE,xqvp_now()-stamp);free(input);input=features;input_bytes=bytes;
                if(code)code=5;
            }
        }
        if(!code && worker_cancel(&control))code=26;
        if(!code) {
            trace=fopen(trace_path,"wb");if(!trace)code=4;
        }
        if(!code) {
            cnn_begin=timestamp_us();stamp=xqvp_now();
            code=run(model,model_bytes,input,input_bytes,strcmp(trace_path,"/dev/null")?trace:NULL);
            xqvp_add(XQVP_CNN,xqvp_now()-stamp);decode_begin=timestamp_us();
        }
        if(trace && fclose(trace) && !code)code=21;
        free(input);
        if(!code && !worker_cancel(&control)) {
            stamp=xqvp_now();if(xqvoice_decode(final_logits,final_frames,text)<0)code=25;
            xqvp_add(XQVP_DECODE,xqvp_now()-stamp);
        }
        if(worker_cancel(&control))code=26;
        finished=timestamp_us();
        if(!code && *text) {
            size_t i,n=strlen(text);static const char digits[]="0123456789abcdef";
            for(i=0;i<n;i++){hex[i*2u]=digits[(unsigned char)text[i]>>4];hex[i*2u+1]=digits[(unsigned char)text[i]&15u];}
            hex[n*2u]=0;
        }else strcpy(hex,"-");
        tail_valid=command.kind=='L' && (code==0 || code==25) && metrics.frames &&
            began && metrics.last_voice_us>=began && metrics.endpoint_us>=metrics.last_voice_us &&
            metrics.features_done_us>=metrics.endpoint_us && finished>=metrics.features_done_us;
        worker_emit(&control,"XQW1 RESULT %u %d %s frames=%u model_loads=%lu model_checks=%lu mac_opens=%lu jobs=%llu cycles=%llu request_us=%llu cnn_us=%llu decode_us=%llu tail_valid=%u endpoint_to_result_us=%llu last_voice_to_result_us=%llu feature_tail_us=%llu\n",
            control.active,code,hex,final_frames,loads,model_validation_count,opens,
            xqvoice_mac_jobs()-jobs_before,xqvoice_mac_cycles()-cycles_before,
            (unsigned long long)(finished-began),(unsigned long long)(decode_begin?decode_begin-cnn_begin:0),
            (unsigned long long)(decode_begin?finished-decode_begin:0),tail_valid,
            (unsigned long long)(tail_valid?finished-metrics.endpoint_us:0),
            (unsigned long long)(tail_valid?finished-metrics.last_voice_us:0),
            (unsigned long long)(tail_valid?metrics.features_done_us-metrics.endpoint_us:0));
        xqvp_mac(xqvoice_mac_jobs()-jobs_before,xqvoice_mac_cycles()-cycles_before);xqvp_emit(code);
        worker_emit(&control,"XQW1 IDLE %u\n",control.active);control.active=0;
        if(code==22 || code==23)break; /* Fail closed; parent may restart this worker. */
        code=0;
    }
    if(control.protocol_error){worker_emit(&control,"XQW1 ERROR 0 90\n");code=90;}
    worker_emit(&control,"XQW1 BYE\n");
    request_cancel=NULL;request_cancel_context=NULL;trusted_model=NULL;trusted_model_size=0;
    xqvoice_mac_close();free(model);return code;
failed_start:
    worker_emit(&control,"XQW1 ERROR 0 %d\n",code);
    trusted_model=NULL;trusted_model_size=0;xqvoice_mac_close();free(model);return code;
}
#else
static int worker_main(int argc,char **argv){(void)argc;(void)argv;return 99;}
#endif
