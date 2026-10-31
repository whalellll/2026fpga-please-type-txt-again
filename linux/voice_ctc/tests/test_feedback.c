/* Drive the real session protocol through RESULT -> IDLE, including stale,
 * cancellation and repeated noise. No subprocess/device substitutes needed. */
#include "xqvoice_session.c"
#include <assert.h>
static void initial(xq_search_board_t *b) {
    static const uint8_t back[9]={5,4,3,2,1,2,3,4,5};
    memset(b,0,sizeof(*b));
    for(unsigned i=0;i<9;i++){b->squares[i]=back[i];b->squares[81+i]=back[i]|SIDE_BLACK;}
    for(unsigned i=0;i<9;i+=2){b->squares[27+i]=PIECE_P;b->squares[54+i]=PIECE_P|SIDE_BLACK;}
    b->squares[19]=b->squares[25]=PIECE_C;b->squares[64]=b->squares[70]=PIECE_C|SIDE_BLACK;
}
static void arm(xqvoice_session *s,const xq_search_board_t *b) {
    s->state=XQV_RECORDING;s->request=s->worker_request=++s->next_request;
    s->worker_busy=1;s->reply_received=0;s->revision=3;s->snapshot=*b;s->input_kind='L';
}
static void result(xqvoice_session *s,const xq_search_board_t *b,int code,const char *heard,int stale) {
    char hex[65],line[256];size_t n=strlen(heard);assert(n<=31);
    for(size_t i=0;i<n;i++)sprintf(hex+2*i,"%02x",(unsigned char)heard[i]);
    if(!n)strcpy(hex,"-");
    snprintf(line,sizeof(line),"XQW1 RESULT %u %d %s",s->request,code,hex);
    assert(worker_line(s,line,b,3,1));
    snprintf(line,sizeof(line),"XQW1 IDLE %u",s->request);
    assert(worker_line(s,line,b,stale?4:3,1));
}
int main(void) {
    xqvoice_session s;xq_search_board_t b,before;xq_search_move_t move;initial(&b);before=b;xqvoice_session_init(&s);
    xqvoice_timing t=worker_timing(" request_us=2000 cnn_us=20 decode_us=10 tail_valid=1 endpoint_to_result_us=50 last_voice_to_result_us=500 feature_tail_us=10");
    assert(t.valid && t.endpoint_to_result_us==50 && t.last_voice_to_result_us==500);
    assert(!worker_timing(" request_us=-1 cnn_us=0 decode_us=0 tail_valid=1 endpoint_to_result_us=0 last_voice_to_result_us=0 feature_tail_us=0").valid);
    assert(!worker_timing(" request_us=1 request_us=2 cnn_us=0 decode_us=0 tail_valid=1 endpoint_to_result_us=0 last_voice_to_result_us=0 feature_tail_us=0").valid);
    assert(!worker_timing(" request_us=1 cnn_us=0 decode_us=0 tail_valid=1 endpoint_to_result_us=2 last_voice_to_result_us=0 feature_tail_us=0").valid);
    assert(!worker_timing(" request_us=18446744073709551616 cnn_us=0 decode_us=0 tail_valid=1 endpoint_to_result_us=0 last_voice_to_result_us=0 feature_tail_us=0").valid);
    arm(&s,&b);result(&s,&b,0,"帅五进九",0);
    assert(s.result==XQV_RESULT_ILLEGAL && !strcmp(s.heard_text,"帅五进九") && !strcmp(s.result_text,"不合法，请重说"));
    assert(!memcmp(&b,&before,sizeof(b)));uint32_t generation=s.result_generation;
    /* Same meaningful result is stable; a different transcript is a new result. */
    arm(&s,&b);result(&s,&b,0,"帅五进九",0);assert(s.result_generation==generation);
    arm(&s,&b);result(&s,&b,0,"卒一进一",0);assert(s.result_generation==++generation && !strcmp(s.heard_text,"卒一进一"));
    for(unsigned i=0;i<100;i++) {
        arm(&s,&b);result(&s,&b,i%2?-1:-3,"",0);
        assert(s.state==XQV_IDLE && !s.request && !s.worker_busy && !s.error);
        assert(s.result_generation==generation && !strcmp(s.heard_text,"卒一进一") && s.result==XQV_RESULT_ILLEGAL);
    }
    assert(s.quiet_rejections==100);
    arm(&s,&b);result(&s,&b,0,"马二进",0);
    assert(s.result==XQV_RESULT_UNRECOGNIZED && !strcmp(s.heard_text,"马二进") && !strcmp(s.result_text,"无法识别，请重说"));
    arm(&s,&b);result(&s,&b,0,"",0);assert(s.result==XQV_RESULT_UNRECOGNIZED && !s.heard_text[0]);
    arm(&s,&b);result(&s,&b,-2,"",0);assert(s.result==XQV_RESULT_TOO_LONG && strstr(s.result_text,"太长"));
    arm(&s,&b);result(&s,&b,25,"",0);
    assert(s.result==XQV_RESULT_UNRECOGNIZED && !strcmp(s.result_text,"无法识别，请重说"));
    const int faults[]={-20,-21,-22,-25,10};
    for(unsigned i=0;i<sizeof(faults)/sizeof(faults[0]);i++) {
        arm(&s,&b);result(&s,&b,faults[i],"",0);
        assert(s.result==XQV_RESULT_UNAVAILABLE && s.next_start_ms>=now_ms()+4900u);
    }
    generation=s.result_generation;arm(&s,&b);result(&s,&b,0,"马二进三",1);
    assert(s.result_generation==generation && s.state==XQV_IDLE && !memcmp(&b,&before,sizeof(b)));
    arm(&s,&b);unsigned id=s.request;s.state=XQV_CANCELLING;s.request=0;
    char line[256];snprintf(line,sizeof(line),"XQW1 RESULT %u 0 e9a9ace4ba8ce8bf9be4b889",id);assert(worker_line(&s,line,&b,3,1));
    snprintf(line,sizeof(line),"XQW1 IDLE %u",id);assert(worker_line(&s,line,&b,3,1));assert(s.result_generation==generation);
    arm(&s,&b);result(&s,&b,0,"马二进三",0);assert(s.state==XQV_READY && s.result_generation==generation);
    assert(xqvoice_session_apply(&s,&b,3,1,&move));
    assert(s.result==XQV_RESULT_COMMAND && !strcmp(s.heard_text,"马二进三") && !strcmp(s.result_text,"已走棋"));
    assert(!xqvoice_session_apply(&s,&b,3,1,&move));assert(b.squares[20]==PIECE_N && !b.squares[1]);
    puts("FEEDBACK_PASS raw illegal/partial/empty,100 silent rejects,stable duplicates,visible long/device failures,stale/cancel gating,legal once");
    return 0;
}
