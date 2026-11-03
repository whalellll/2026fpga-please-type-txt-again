#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L
#include "xqvoice_session.h"
#include <sys/wait.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <time.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#include <sys/socket.h>
#include <sys/syscall.h>

static uint64_t now_ms(void) {
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t))return UINT64_MAX;
    return (uint64_t)t.tv_sec*1000u+(uint64_t)t.tv_nsec/1000000u;
}
static const char *setting(const char *key,const char *fallback) {
    const char *v=getenv(key);return v&&*v?v:fallback;
}
int xqvoice_phrase(const char *text,xqvoice_command_t *command) {
    static const char *const pieces[9]={"车","马","炮","兵","卒","帅","将","仕","相"};
    static const char *const digits[9]={"一","二","三","四","五","六","七","八","九"};
    static const char *const actions[3]={"进","退","平"};
    unsigned i,j;uint8_t tokens[4]={0};
    if(!text || !command || strlen(text)!=12u)return 0;
    for(i=0;i<4;i++) {
        unsigned count=i==0?9u:i==2?3u:9u;
        const char *const *set=i==0?pieces:i==2?actions:digits;
        for(j=0;j<count;j++)if(!memcmp(text+i*3u,set[j],3))break;
        if(j==count) {
            if(i==0 && !memcmp(text,"士",3))j=7;
            else if(i==0 && !memcmp(text,"象",3))j=8;
            else return 0;
        }
        tokens[i]=(uint8_t)(j+(i==0?1u:i==2?19u:10u));
    }
    memset(command,0,sizeof(*command));command->type=XQVOICE_COMMAND_MOVE;
    command->piece=(xqvoice_piece_t)tokens[0];command->source_file=tokens[1]-9;
    command->action=(xqvoice_action_t)(tokens[2]-18);command->target=tokens[3]-9;
    command->token_count=4;memcpy(command->tokens,tokens,4);return 1;
}
static int same_board(xqvoice_session *s,const xq_search_board_t *board,uint32_t revision,int ready) {
    return ready && board && s->revision==revision && !memcmp(board,&s->snapshot,sizeof(*board));
}
static int legal_candidate(xqvoice_session *s,const xq_search_board_t *board,xq_search_move_t *move) {
    if((board->side==0 && (s->command.piece==XQVOICE_PIECE_JIANG || s->command.piece==XQVOICE_PIECE_ZU)) ||
       (board->side!=0 && (s->command.piece==XQVOICE_PIECE_SHUAI || s->command.piece==XQVOICE_PIECE_BING)))return 0;
    return xqvoice_resolve_move(board,&s->command,move);
}
int xqvoice_button_at(int x,int y){(void)x;(void)y;return 0;}
void xqvoice_session_defer(xqvoice_session *s,unsigned milliseconds) {
    uint64_t now=now_ms();s->next_start_ms=now==UINT64_MAX?0:now+milliseconds;
}
static void publish_result(xqvoice_session *s,int result,const char *heard,const char *text) {
    int changed=result==XQV_RESULT_COMMAND || s->result!=result ||
        strcmp(s->heard_text,heard) || strcmp(s->result_text,text);
    s->result=result;snprintf(s->heard_text,sizeof(s->heard_text),"%s",heard);
    snprintf(s->result_text,sizeof(s->result_text),"%s",text);
    if(changed)++s->result_generation;
}
static void rejected(xqvoice_session *s,const char *error,unsigned delay,int result,
                     const char *heard,const char *text) {
    s->state=XQV_ERROR;s->error=error;s->request=0;s->need_send=0;
    publish_result(s,result,heard,text);
    memset(&s->displayed_command,0,sizeof(s->displayed_command));xqvoice_session_defer(s,delay);
}
static void failed(xqvoice_session *s,const char *error,unsigned delay) {
    rejected(s,error,delay,XQV_RESULT_UNAVAILABLE,"","识别暂不可用，正在重试");
}
static void quiet_rearm(xqvoice_session *s) {
    s->state=XQV_IDLE;s->request=s->need_send=0;s->error=NULL;
    memset(&s->command,0,sizeof(s->command));
    if(s->quiet_rejections<UINT32_MAX)++s->quiet_rejections;
    /* Keep the last meaningful transcript/outcome; a short VAD reject is
       not a new user-facing recognition failure. Do not change thresholds. */
    xqvoice_session_defer(s,300);
}
void xqvoice_session_init(xqvoice_session *s) {
    memset(s,0,sizeof(*s));s->fd=s->command_fd=-1;s->pid=-1;s->state=XQV_IDLE;
}
static void drop_worker(xqvoice_session *s,int terminate) {
    if(s->command_fd>=0){close(s->command_fd);s->command_fd=-1;}
    if(s->fd>=0){close(s->fd);s->fd=-1;}
    if(s->pid>0 && terminate){kill(s->pid,SIGKILL);while(waitpid(s->pid,NULL,0)<0 && errno==EINTR){}s->pid=-1;}
    s->worker_ready=s->worker_busy=s->need_send=s->reply_received=0;s->worker_request=0;
    s->transmit_used=s->transmit_sent=s->output_bytes=0;
}
static int flush_worker(xqvoice_session *s) {
    while(s->transmit_sent<s->transmit_used) {
        ssize_t n=send(s->command_fd,s->transmit+s->transmit_sent,s->transmit_used-s->transmit_sent,MSG_NOSIGNAL|MSG_DONTWAIT);
        if(n>0){s->transmit_sent+=(size_t)n;continue;}
        if(n<0 && errno==EINTR)continue;
        if(n<0 && (errno==EAGAIN || errno==EWOULDBLOCK))return 1;
        return 0;
    }
    s->transmit_used=s->transmit_sent=0;return 1;
}
static int queue_worker(xqvoice_session *s,char kind,uint32_t id,const char *path) {
    char line[2200],hex[2049];size_t n=path?strlen(path):0,i;int bytes;
    static const char digits[]="0123456789abcdef";
    if(n>1023u)return 0;
    for(i=0;i<n;i++){hex[i*2u]=digits[(unsigned char)path[i]>>4];hex[i*2u+1u]=digits[(unsigned char)path[i]&15u];}
    hex[n*2u]=0;
    bytes=snprintf(line,sizeof(line),"XQW1 %c %u %s\n",kind,id,n?hex:"-");
    if(bytes<0 || (size_t)bytes>=sizeof(line) || s->transmit_used+(size_t)bytes>sizeof(s->transmit))return 0;
    memcpy(s->transmit+s->transmit_used,line,(size_t)bytes);s->transmit_used+=(size_t)bytes;
    return flush_worker(s);
}
static int spawn_worker(xqvoice_session *s) {
    int command[2],output[2],flags;pid_t pid;
    const char *runtime=setting("XQVOICE_RUNTIME","/opt/xqvoice/xqvoice-probe");
    const char *model=setting("XQVOICE_MODEL","/opt/xqvoice/xqvoice_int8.bin");
    if(access(runtime,X_OK) || access(model,R_OK))return 0;
    if(socketpair(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0,command))return 0;
    if(socketpair(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0,output)){close(command[0]);close(command[1]);return 0;}
    flags=fcntl(output[0],F_GETFL,0);
    if(flags<0 || fcntl(output[0],F_SETFL,flags|O_NONBLOCK)<0)goto no_child;
    pid=fork();if(pid<0)goto no_child;
    if(!pid) {
        int fd;
        /* stdout is the private XQW1 protocol. Hardware diagnostics remain on
           the parent's stderr and cannot be mistaken for protocol frames. */
        if(dup2(command[1],STDIN_FILENO)<0 || dup2(output[1],STDOUT_FILENO)<0)_exit(126);
#ifdef SYS_close_range
        if(syscall(SYS_close_range,3u,~0u,0u)<0)
#endif
            for(fd=3;fd<256;fd++)close(fd);
        execl(runtime,runtime,"--worker",model,setting("XQVOICE_BACKEND","mac"),"/dev/null",(char *)NULL);_exit(127);
    }
    close(command[1]);close(output[1]);s->command_fd=command[0];s->fd=output[0];s->pid=pid;
    s->worker_ready=0;s->output_bytes=0;s->transmit_used=s->transmit_sent=0;++s->worker_starts;return 1;
no_child:
    close(command[0]);close(command[1]);close(output[0]);close(output[1]);return 0;
}
static int send_request(xqvoice_session *s) {
    if(!s->need_send || !s->worker_ready || s->worker_busy)return 1;
    s->worker_request=s->request;s->worker_busy=1;s->reply_received=0;s->need_send=0;
    return queue_worker(s,s->input_kind,s->request,s->input_path);
}
int xqvoice_session_start(xqvoice_session *s,const xq_search_board_t *board,uint32_t revision,int ready) {
    const char *replay=getenv("XQVOICE_REPLAY_WAV");
    const char *path=replay&&*replay?replay:setting("XQVOICE_AUDIO_DEVICE","/dev/pango-audio0");uint64_t now=now_ms();
    if(!ready || !board || board->side || s->worker_busy || s->need_send || s->state==XQV_RECORDING || s->state==XQV_READY || s->state==XQV_CANCELLING)return 0;
    if(now==UINT64_MAX || strlen(path)>=sizeof(s->input_path)){failed(s,"clock/path unavailable",5000);return 0;}
    if(s->next_request==UINT32_MAX){drop_worker(s,1);s->next_request=0;}
    if(s->pid<=0 && !spawn_worker(s)){failed(s,"worker unavailable",5000);return 0;}
    s->request=++s->next_request;s->timing_request=s->request;s->revision=revision;s->snapshot=*board;
    s->request_started_ms=now;s->deadline_ms=now+30000u;s->phase=replay&&*replay?XQV_PHASE_INFER:XQV_PHASE_LISTEN;
    memset(&s->reply_timing,0,sizeof(s->reply_timing));
    s->listening_ready=0;s->reply_received=0;s->error=NULL;s->state=XQV_RECORDING;s->need_send=1;
    strcpy(s->input_path,path);s->input_kind=replay&&*replay?'W':'L';memset(&s->command,0,sizeof(s->command));
    if(!send_request(s)){drop_worker(s,1);failed(s,"worker send",5000);return 0;}return 1;
}
void xqvoice_session_cancel(xqvoice_session *s) {
    s->retry=0;s->request=0;s->need_send=0;s->error=NULL;s->stop_requested=s->stop_delivered=0;
    memset(&s->command,0,sizeof(s->command));xqvoice_session_defer(s,300);
    if(s->worker_busy) {
        if(s->state!=XQV_CANCELLING) {
            if(!queue_worker(s,'C',s->worker_request,NULL)){drop_worker(s,1);s->state=XQV_IDLE;return;}
            s->cancel_deadline_ms=now_ms()+1500u;
        }
        s->state=XQV_CANCELLING;
    }else s->state=XQV_IDLE;
}
int xqvoice_session_stop_recording(xqvoice_session *s){(void)s;return 0;}
void xqvoice_session_retry(xqvoice_session *s,const xq_search_board_t *board,uint32_t revision,int ready) {
    xqvoice_session_cancel(s);if(!s->worker_busy){s->next_start_ms=0;(void)xqvoice_session_start(s,board,revision,ready);}
}
static int decode_hex_text(const char *hex,char text[32]) {
    size_t n=strlen(hex),i;
    if(!strcmp(hex,"-")){text[0]=0;return 1;}
    if((n&1u) || n>62u)return 0;
    for(i=0;i<n;i+=2u) {
        unsigned a,b;char x=hex[i],y=hex[i+1];
        if(x>='0' && x<='9')a=(unsigned)(x-'0');else if(x>='a' && x<='f')a=(unsigned)(x-'a'+10);else return 0;
        if(y>='0' && y<='9')b=(unsigned)(y-'0');else if(y>='a' && y<='f')b=(unsigned)(y-'a'+10);else return 0;
        if(!a && !b)return 0;
        text[i/2u]=(char)(a*16u+b);
    }
    text[n/2u]=0;return 1;
}
static int read_metric(const char *text,const char *key,uint64_t *out) {
    size_t n=strlen(key);const char *at=text;int found=0;
    while((at=strstr(at,key))!=NULL) {
        if((at==text || at[-1]==' ') && at[n]=='=') {
            char *end;unsigned long long value;const char *digits=at+n+1;
            if(found || *digits<'0' || *digits>'9')return 0;
            errno=0;value=strtoull(digits,&end,10);
            if(errno || (end[0] && end[0]!=' '))return 0;
            *out=(uint64_t)value;found=1;
        }
        at+=n;
    }
    return found;
}
static xqvoice_timing worker_timing(const char *text) {
    xqvoice_timing t={0};uint64_t valid=0;
    if(!read_metric(text,"request_us",&t.request_us) ||
       !read_metric(text,"cnn_us",&t.cnn_us) || !read_metric(text,"decode_us",&t.decode_us) ||
       !read_metric(text,"tail_valid",&valid) || valid!=1 ||
       !read_metric(text,"endpoint_to_result_us",&t.endpoint_to_result_us) ||
       !read_metric(text,"last_voice_to_result_us",&t.last_voice_to_result_us) ||
       !read_metric(text,"feature_tail_us",&t.feature_tail_us))return t;
    t.valid=t.request_us>=t.last_voice_to_result_us &&
        t.last_voice_to_result_us>=t.endpoint_to_result_us &&
        t.endpoint_to_result_us>=t.feature_tail_us && t.endpoint_to_result_us>=t.cnn_us &&
        t.endpoint_to_result_us-t.cnn_us>=t.decode_us;
    return t;
}
static int worker_line(xqvoice_session *s,const char *line,const xq_search_board_t *board,uint32_t revision,int ready) {
    unsigned id;int code,n=0;char word[65];
    if(!strncmp(line,"XQVOICE_PROFILE_V1 ",19))return 1; /* Optional per-request metrics, bounded by line buffer. */
    if(!strncmp(line,"XQW1 READY ",11)) {
        if(s->worker_ready || s->worker_busy)return 0;
        s->worker_ready=1;return send_request(s);
    }
    if(!strcmp(line,"XQW1 BYE"))return 1;
    if(sscanf(line,"XQW1 STAGE %u %64s%n",&id,word,&n)==2 && !line[n]) {
        if(!s->worker_busy || id!=s->worker_request)return id<=s->next_request;
        if(s->state!=XQV_RECORDING || id!=s->request)return 1;
        if(!strcmp(word,"LISTENING")){s->phase=XQV_PHASE_LISTEN;s->listening_ready=1;s->deadline_ms=UINT64_MAX;}
        else if(!strcmp(word,"CAPTURING")){s->phase=XQV_PHASE_CAPTURE;s->deadline_ms=now_ms()+30000u;}
        else if(!strcmp(word,"INFERENCING")){s->phase=XQV_PHASE_INFER;s->deadline_ms=now_ms()+30000u;}
        else return 0;
        return 1;
    }
    if(sscanf(line,"XQW1 RESULT %u %d %64s%n",&id,&code,word,&n)==3 && (!line[n] || line[n]==' ')) {
        if(!s->worker_busy || id!=s->worker_request)return id<=s->next_request;
        if(s->reply_received || !decode_hex_text(word,s->reply_text))return 0;
        s->reply_code=code;s->reply_timing=worker_timing(line+n);s->reply_received=1;return 1;
    }
    if(sscanf(line,"XQW1 IDLE %u%n",&id,&n)==1 && !line[n]) {
        xq_search_move_t move;
        if(!s->worker_busy || id!=s->worker_request)return id<=s->next_request;
        if(!s->reply_received)return 0;
        s->worker_busy=0;s->worker_request=0;
        if(s->state==XQV_CANCELLING || !s->request){s->state=XQV_IDLE;return 1;}
        if(!same_board(s,board,revision,ready)){s->request=0;s->state=XQV_IDLE;return 1;}
        s->timing=s->reply_timing;
        if(s->input_kind!='L' || (s->reply_code && s->reply_code!=25))s->timing.valid=0;
        if(s->input_kind=='L' && (s->reply_code==-1 || s->reply_code==-3)) {
            quiet_rearm(s);return 1;
        }
        if(s->reply_code==-2) {
            rejected(s,"capture too long",300,XQV_RESULT_TOO_LONG,"","说话太长，请分句重说");return 1;
        }
        if(s->reply_code==25) {
            /* Complete, valid capture with no CTC command is a recognition
               outcome; it does not imply an unavailable device. */
            rejected(s,"no decoded command",300,XQV_RESULT_UNRECOGNIZED,"","无法识别，请重说");return 1;
        }
        if(s->reply_code){failed(s,"recognition device/runtime failed",5000);return 1;}
        if(!xqvoice_phrase(s->reply_text,&s->command)) {
            rejected(s,"no complete command",300,XQV_RESULT_UNRECOGNIZED,s->reply_text,"无法识别，请重说");return 1;
        }
        s->command.sequence=s->request;
        if(legal_candidate(s,board,&move)!=1){
            rejected(s,"illegal or ambiguous",300,XQV_RESULT_ILLEGAL,s->reply_text,"不合法，请重说");return 1;
        }
        strcpy(s->pending_phrase,s->reply_text);s->state=XQV_READY;return 1;
    }
    return 0;
}
int xqvoice_session_poll(xqvoice_session *s,const xq_search_board_t *board,uint32_t revision,int ready) {
    int before=s->state,status=0,eof=0;uint64_t now;pid_t ended;
    if((s->state==XQV_RECORDING || s->state==XQV_READY) && !same_board(s,board,revision,ready))xqvoice_session_cancel(s);
    if(s->pid<=0)return before!=s->state;
    now=now_ms();
    if(now==UINT64_MAX){drop_worker(s,1);failed(s,"clock unavailable",5000);return 1;}
    if(s->state==XQV_CANCELLING && now>=s->cancel_deadline_ms){drop_worker(s,1);s->state=XQV_IDLE;return 1;}
    if(s->state==XQV_RECORDING && now>=s->deadline_ms){drop_worker(s,1);failed(s,"timeout",5000);return 1;}
    if(!flush_worker(s)){drop_worker(s,1);failed(s,"worker send",5000);return 1;}
    if(s->fd>=0)for(;;) {
        char chunk[1024];ssize_t bytes=read(s->fd,chunk,sizeof(chunk));
        if(bytes>0)for(ssize_t i=0;i<bytes;i++) {
            if(chunk[i]=='\n') {
                s->output[s->output_bytes]=0;
                if(!worker_line(s,s->output,board,revision,ready)){drop_worker(s,1);failed(s,"worker protocol",5000);return 1;}
                s->output_bytes=0;
            }else {
                if(!chunk[i] || s->output_bytes+1u>=sizeof(s->output)){drop_worker(s,1);failed(s,"worker output overflow",5000);return 1;}
                s->output[s->output_bytes++]=chunk[i];
            }
        }else if(!bytes){eof=1;break;}
        else if(errno==EINTR)continue;
        else if(errno==EAGAIN || errno==EWOULDBLOCK)break;
        else {eof=1;break;}
    }
    ended=waitpid(s->pid,&status,WNOHANG);
    if(ended==s->pid || (ended<0 && errno==ECHILD) || eof) {
        int active=s->worker_busy || s->need_send || s->state==XQV_RECORDING;
        if(ended==s->pid || ended<0)s->pid=-1;
        drop_worker(s,1);
        if(active)failed(s,"worker exited",5000);
        else if(s->state==XQV_CANCELLING)s->state=XQV_IDLE;
    }
    return before!=s->state;
}
int xqvoice_session_pause(xqvoice_session *s) {
    struct timespec delay={0,1000000};xqvoice_session_cancel(s);
    for(unsigned i=0;s->worker_busy && i<1600;i++){(void)xqvoice_session_poll(s,NULL,0,0);nanosleep(&delay,NULL);}
    if(s->worker_busy){drop_worker(s,1);s->state=XQV_IDLE;}
    return !s->worker_busy;
}
void xqvoice_session_close(xqvoice_session *s) {
    struct timespec delay={0,1000000};int status;
    s->request=s->need_send=0;
    if(s->pid>0 && s->command_fd>=0)(void)queue_worker(s,'Q',0,NULL);
    for(unsigned i=0;s->pid>0 && i<1500;i++) {
        if(waitpid(s->pid,&status,WNOHANG)==s->pid){s->pid=-1;break;}
        nanosleep(&delay,NULL);
    }
    drop_worker(s,1);s->state=XQV_IDLE;
}
static int take_move(xqvoice_session *s,const xq_search_board_t *board,uint32_t revision,int ready,xq_search_move_t *move) {
    if(s->state!=XQV_READY || !s->request || !same_board(s,board,revision,ready) || legal_candidate(s,board,move)!=1)return 0;
    s->state=XQV_COMMITTED;s->request=0;return 1;
}
int xqvoice_session_apply(xqvoice_session *s,xq_search_board_t *board,uint32_t revision,int ready,xq_search_move_t *move) {
    if(!take_move(s,board,revision,ready,move))return 0;
    board->squares[move->to]=board->squares[move->from];board->squares[move->from]=0;
    board->side^=1;
    s->displayed_command=s->command;
    publish_result(s,XQV_RESULT_COMMAND,s->pending_phrase,"已走棋");
    return 1;
}

int xqvoice_session_auto_step(xqvoice_session *s,xq_search_board_t *board,uint32_t revision,int ready,xq_search_move_t *move) {
    uint64_t tick;
    ready=ready && board && board->side==0;
    (void)xqvoice_session_poll(s,board,revision,ready);
    if(!ready)return 0;
    if(s->state==XQV_READY)return xqvoice_session_apply(s,board,revision,ready,move);
    tick=now_ms();
    if(tick==UINT64_MAX){if(s->state!=XQV_ERROR)failed(s,"clock unavailable",5000);return 0;}
    if(!s->worker_busy && !s->need_send && s->state!=XQV_RECORDING && s->state!=XQV_CANCELLING && tick>=s->next_start_ms)
        (void)xqvoice_session_start(s,board,revision,ready);
    return 0;
}
