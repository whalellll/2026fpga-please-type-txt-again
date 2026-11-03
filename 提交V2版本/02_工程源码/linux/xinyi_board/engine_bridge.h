#ifndef XINYI_ENGINE_BRIDGE_H
#define XINYI_ENGINE_BRIDGE_H
#include "xiangqi_search.h"
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>

typedef enum { XY_ENGINE_STOPPED,XY_ENGINE_STARTING,XY_ENGINE_READY,
    XY_ENGINE_BUSY,XY_ENGINE_DONE,XY_ENGINE_STOPPING,XY_ENGINE_FAILED } xy_engine_state;
typedef struct {
    uint32_t token,revision,board_crc,nodes,elapsed_us,red_win_permille;
    int okay,have_wdl;
    int32_t score_cp;
    xq_search_move_t move;
    char iccs[5],notation[128];
} xy_engine_reply;
typedef struct {
    pid_t pid;
    int input,output,wait_status,cancel_requested,fault;
    xy_engine_state state;
    uint32_t token,revision,board_crc,nodes;
    uint64_t started_ms,cancel_ms;
    unsigned timeout_ms;
    xq_search_board_t position;
    xy_engine_reply reply;
    char line[512],pending[256];
    size_t used,pending_bytes;
} xy_engine;

void xy_engine_init(xy_engine *);
/* Trusted absolute service executable; service links the real dedicated
 * engine, never a CPU search fallback. Position is copied before enqueue.
 * At most one in-flight request. Start/ready/search remain nonblocking. */
int xy_engine_start(xy_engine *,const char *executable,uint32_t token,
                    uint32_t revision,const xq_search_board_t *,unsigned nodes);
xy_engine_state xy_engine_poll(xy_engine *);
int xy_engine_take(xy_engine *,xy_engine_reply *); /* exactly once */
int xy_engine_cancel(xy_engine *);
/* STOPPED is the cancellation ack, only after waitpid. FAILED is also reaped.
 * A subsequent explicit request may initialize a new service process. */
int xy_engine_dispose(xy_engine *);
int xy_engine_notation(const xq_search_board_t *,const char *iccs,char *,size_t);
#endif
