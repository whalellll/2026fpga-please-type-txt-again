#ifndef XINYI_BOARD_SPEECH_TASK_H
#define XINYI_BOARD_SPEECH_TASK_H
#include <stdint.h>
#include <stddef.h>
#include <sys/types.h>
#include "../voice_speech/xq_speech.h"

#define XY_SPEECH_WIRE_MAGIC 0x31505358u
enum { XYSP_READY=1,XYSP_RUN,XYSP_RESULT,XYSP_IDLE_FRAME,XYSP_QUIT,XYSP_BYE,XYSP_ERROR };
typedef struct {
    uint32_t magic,kind,token,revision,status,count,underflows,reserved;
    uint8_t tokens[96];
} xy_speech_wire;
_Static_assert(sizeof(xy_speech_wire)==128,"Private speech wire layout");

enum { XY_SPEECH_IDLE,XY_SPEECH_STARTING,XY_SPEECH_RUNNING,XY_SPEECH_DONE,
       XY_SPEECH_FAILED,XY_SPEECH_STOPPING,XY_SPEECH_STOPPED };
typedef struct {
    pid_t pid;
    int fd,state,ready,result_received,cancelling,closing,bye_received;
    int cleanup_confirmed,wait_status,protocol_error;
    uint32_t token,revision,underflows,result_status,starts;
    uint64_t deadline_ms;
    char worker[1024],pcm_directory[512];
    xy_speech_wire request;
    uint8_t incoming[128],outgoing[128];
    size_t incoming_used,outgoing_used,outgoing_sent;
} xy_speech_task;

/* Single event-thread API. Worker is a standalone exec binary, never a
 * post-fork call into malloc, the PCM cache or device MMIO. Paths are immutable
 * SHA-bound deployment inputs owned by the caller. Playback is fixed volume100.
 * Main/worker diagnostics never include a position, transcript or filename.
 */
void xy_speech_task_init(xy_speech_task *);
int xy_speech_task_start(xy_speech_task *,const char *worker,const char *pcm_directory,
    uint32_t token,uint32_t revision,const xq_search_board_t *before,const char *iccs);
int xy_speech_task_poll(xy_speech_task *);
int xy_speech_task_cancel(xy_speech_task *,uint32_t token,uint32_t revision);
/* Requests a graceful worker shutdown. Poll until pid==-1; cancel ack requires
 * state==STOPPED && cleanup_confirmed, both after waitpid. A dead/crashed worker
 * is FAILED; caller must not turn it into an unqualified safe-stop receipt.
 * FAILED with unknown cleanup blocks another start until the caller has
 * explicitly recovered the audio environment and initialized a fresh task. */
int xy_speech_task_close(xy_speech_task *);
#endif
