#ifndef XINYI_BOARD_COACH_TASK_H
#define XINYI_BOARD_COACH_TASK_H
#include "platform.h"
#include "coach_protocol.h"

typedef struct xy_coach_task xy_coach_task;
typedef struct {
    /* Caller verifies immutable hashes before open. Both paths must be absolute.
     * Only /run/xinyi-coach.XXXXXX on verified tmpfs contains request payloads. */
    const char *worker_path,*models_path;
    unsigned startup_ms,request_ms,cancel_ms,term_ms,drain_ms;
    /* Optional pre-audited read-only V321 BUSY checker: 1 idle, 0 busy,
     * -1 unknown. NULL opens only the V321 register page read-only. */
    int (*vision_drained)(void *);
    void *context;
} xy_coach_config;
typedef enum { XY_COACH_READY, XY_COACH_RESULT, XY_COACH_GEOMETRY_REJECT,
               XY_COACH_CANCELLED, XY_COACH_FATAL, XY_COACH_UNDRAINED, XY_COACH_PARTIAL }
    xy_coach_event_type;
typedef struct {
    xy_coach_event_type type;
    uint32_t token;
    unsigned remote_status;
    int consumed,drained,resident_ready,worker_reaped;
} xy_coach_event;

/* open starts one resident worker; READY is asynchronous. No automatic reload.
 * stderr/stdout stay in a bounded private pipe and never reach the UART. */
xy_coach_task *xy_coach_open(const xy_coach_config *);
int xy_coach_ready(const xy_coach_task *);
int xy_coach_start(xy_coach_task *,uint32_t token,const xy_platform_frame *);
/* Pin the platform frame until this returns one for its exact token. It means
 * the writer has joined and will never read the supplied RAM pointer again. */
int xy_coach_consumed(xy_coach_task *,uint32_t token);
int xy_coach_cancel(xy_coach_task *,uint32_t token);
/* Nonblocking. RESULT and PARTIAL write *out (<=300, distinct mapped/unmapped).
 * Geometry/error/cancel leave *out untouched. A reusable terminal event waits
 * for request removal, release status9, IDLE and V321 BUSY=0. Cancellation is
 * acknowledged only by that handshake, or reaped worker plus BUSY=0.
 * UNDRAINED is fatal and never a safe cancellation ack. */
int xy_coach_poll(xy_coach_task *,xy_coach_event *,xqcoach_result *out);
/* Bounded shutdown. Zero retains quarantined resources on unsafe drain;
 * caller must not release/reuse them. Only our fixed files are cleaned. */
int xy_coach_close(xy_coach_task *);
/* Process identity for supervision; no frame/payload information. */
long xy_coach_worker_pid(const xy_coach_task *);
#endif
