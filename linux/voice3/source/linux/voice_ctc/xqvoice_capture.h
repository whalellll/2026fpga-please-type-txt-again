#ifndef XQV_CAPTURE_H
#define XQV_CAPTURE_H
#ifndef XQV_END_SILENCE_CHUNKS
#define XQV_END_SILENCE_CHUNKS 45u
#endif
#if XQV_END_SILENCE_CHUNKS < 12 || XQV_END_SILENCE_CHUNKS > 100
#error Invalid endpoint silence
#endif
#include <stddef.h>
#include <stdint.h>
typedef struct {
    int16_t ring[20][160];
    int16_t *samples;size_t capacity,count;
    unsigned ring_next,ring_count,chunks,voiced,quiet,start_run;
    int active,done,listen;
} xqvoice_capture_state;
void xqvoice_capture_init(xqvoice_capture_state *s,int16_t *samples,size_t capacity);
/* 0 waiting, 1 capturing, 2 done; negative timeout/too-long/too-short. */
int xqvoice_capture_feed(xqvoice_capture_state *s,const int16_t chunk[160]);
/* Manual stop validates the collected utterance; it never truncates an overlong one. */
int xqvoice_capture_finish(xqvoice_capture_state *s);
int xqvoice_capture_features(const char *device,uint8_t **input,size_t *bytes);
int xqvoice_listen_features(const char *device,uint8_t **input,size_t *bytes);
enum {XQV_CAPTURE_LISTENING=0,XQV_CAPTURE_SPEECH=1,XQV_CAPTURE_INFER=2};
typedef struct {
    int (*cancel)(void *context);
    void (*stage)(void *context,unsigned phase);
    void *context;
    unsigned hop_samples;
} xqvoice_capture_control;
int xqvoice_capture_controlled(const char *device,uint8_t **input,size_t *bytes,const xqvoice_capture_control *control);
typedef struct {
    uint64_t started_us,endpoint_us,last_voice_us,features_done_us;
    unsigned frames,max_backlog_frames,paced,streamed;
} xqvoice_stream_metrics;
/* Same controlled capture; exposes existing endpoint clocks without tracing. */
int xqvoice_capture_controlled_metrics(const char *device,uint8_t **input,size_t *bytes,
    const xqvoice_capture_control *control,xqvoice_stream_metrics *metrics);
int xqvoice_live_features(const char *device,uint8_t **input,size_t *bytes,int listen,
                         xqvoice_stream_metrics *metrics);
#endif
