/* Actual VAD feed and optional wire parser, synthetic blocks only. */
#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L
#define now_ms capture_now_ms
#include "../voice_ctc/xqvoice_capture.c"
#undef now_ms
#include "../voice_ctc/xqvoice_session.c"
#include <assert.h>

static void feed(xqvoice_capture_state *s,xqvoice_stream_metrics *m,uint64_t *candidate,
                 const int16_t *block,uint64_t stamp)
{
    int active=s->active;(void)xqvoice_capture_feed(s,block);
    capture_utterance_start(m,s,active,candidate,stamp);
}
int main(void)
{
    int16_t samples[64000],voice[160],quiet[160]={0};xqvoice_capture_state s;
    xqvoice_stream_metrics metrics={0};uint64_t candidate=0;
    for(unsigned i=0;i<160;i++)voice[i]=(i&1u)?400:-400;
    xqvoice_capture_init(&s,samples,64000);s.listen=1;
    for(unsigned i=0;i<10;i++)feed(&s,&metrics,&candidate,quiet,10000u*i);
    assert(!candidate && !metrics.utterance_start_us);
    feed(&s,&metrics,&candidate,voice,500000);assert(candidate==500000 && !metrics.utterance_start_us);
    feed(&s,&metrics,&candidate,quiet,510000);assert(!candidate && !metrics.utterance_start_us);
    for(unsigned i=0;i<3;i++)feed(&s,&metrics,&candidate,voice,1000000u+i*10000u);
    assert(s.active && candidate==1000000 && metrics.utterance_start_us==1000000);
    for(unsigned i=0;i<60;i++)feed(&s,&metrics,&candidate,voice,1030000u+i*10000u);
    for(unsigned i=0;i<XQV_END_SILENCE_CHUNKS;i++)feed(&s,&metrics,&candidate,quiet,1630000u+i*10000u);
    assert(s.done==2 && metrics.utterance_start_us==1000000);

    const char *base=" request_us=9000000 cnn_us=10000 decode_us=1000 tail_valid=1 endpoint_to_result_us=20000 last_voice_to_result_us=470000 feature_tail_us=9000";
    char wire[768];xqvoice_timing t=worker_timing(base);
    assert(t.valid && !t.utterance_valid); /* Old wire remains functional. */
    uint64_t now=now_ms()*1000u,start=now-1000000u;
    snprintf(wire,sizeof(wire),"%s utterance_start_us=%llu utterance_to_result_us=900000",base,(unsigned long long)start);
    t=worker_timing(wire);assert(t.valid && t.utterance_valid && t.utterance_start_us==start);
    const char *bad[]={" utterance_start_us=0 utterance_to_result_us=900000",
        " utterance_start_us=-1 utterance_to_result_us=900000",
        " utterance_start_us=18446744073709551616 utterance_to_result_us=900000",
        " utterance_start_us=1 utterance_to_result_us=0",
        " utterance_start_us=1 utterance_start_us=1 utterance_to_result_us=900000",
        " utterance_start_us=1", " utterance_to_result_us=900000"};
    for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++){
        snprintf(wire,sizeof(wire),"%s%s",base,bad[i]);t=worker_timing(wire);assert(t.valid && !t.utterance_valid);
    }
    snprintf(wire,sizeof(wire),"%s utterance_start_us=%llu utterance_to_result_us=900000",base,(unsigned long long)(now+9000000u));
    assert(!worker_timing(wire).utterance_valid);
    snprintf(wire,sizeof(wire),"%s utterance_start_us=%llu utterance_to_result_us=469999",base,(unsigned long long)start);
    assert(!worker_timing(wire).utterance_valid);
    snprintf(wire,sizeof(wire),"%s utterance_start_us=%llu utterance_to_result_us=9000001",base,(unsigned long long)start);
    assert(!worker_timing(wire).utterance_valid);
    puts("R17_REAL_VAD_FIRST_CONSECUTIVE_BLOCK_NO_LISTENING_OR_NOISE_START_AND_OPTIONAL_WIRE_NEGATIVES_PASS");
    return 0;
}
