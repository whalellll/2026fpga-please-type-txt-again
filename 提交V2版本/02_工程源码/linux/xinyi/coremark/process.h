#ifndef XINYI_COREMARK_PROCESS_H
#define XINYI_COREMARK_PROCESS_H
#include "../xinyi_product.h"
#include <sys/types.h>

typedef enum { XY_CM_STOPPED, XY_CM_RUNNING, XY_CM_CANCEL_REQUESTED,
               XY_CM_DONE, XY_CM_CANCELLED, XY_CM_FAILED } xy_cm_status;
typedef struct {
    pid_t pid;
    int fd,wait_status,saw_result,line_failed;
    xy_cm_status status;
    uint32_t token,cpu_hz;
    unsigned target_ms,elapsed_ms,progress;
    uint64_t start_ms,cancel_ms,perf_iterations,perf_ticks,validation_ticks;
    int valid,is_board;
    char identity[81],kind[24],phase[24],line[1024];
    size_t line_used,total_bytes;
    char output[XY_CM_LOG_BYTES];
    size_t output_used;
    int output_truncated;
} xy_cm_process;

void xy_cm_process_init(xy_cm_process *);
/* Absolute trusted benchmark executable; root binds its hash to the runtime.
 * cpu_hz and identity come from the current audited hardware, never a preset.
 * Host-compiled parent or child can never produce is_board=true.
 * This API does not open UART/JTAG, alter SD, or choose a bitstream. */
int xy_cm_process_start(xy_cm_process *,const char *executable,uint32_t token,
                        unsigned target_ms,uint32_t cpu_hz,const char *identity);
xy_cm_status xy_cm_process_poll(xy_cm_process *); /* bounded, nonblocking */
int xy_cm_process_cancel(xy_cm_process *); /* TERM now, KILL after 500ms via poll */
void xy_cm_process_dispose(xy_cm_process *); /* stop + reap, <=~1 second */
/* Convenience bridge: call from the GUI event loop after each poll. Returns 1
 * once it delivered the terminal callback. Cancel ack only follows waitpid.
 * Still require app.token == process.token to reject stale results. */
int xy_cm_process_apply(xy_cm_process *,xy_app *);
#endif
