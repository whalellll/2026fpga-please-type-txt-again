#ifndef XQVOICE_GUI_IPC_H
#define XQVOICE_GUI_IPC_H

#include <sys/socket.h>
#include <sys/un.h>

#include "xqvoice_protocol.h"

typedef enum {
    XQVOICE_REPLY_APPLIED = 0,
    XQVOICE_REPLY_REJECTED,
    XQVOICE_REPLY_BUSY,
    XQVOICE_REPLY_DISPLAYED
} xqvoice_reply_t;

typedef struct {
    int fd;
    uint32_t last_sequence;
    int have_sequence;
    struct sockaddr_un peer;
    socklen_t peer_bytes;
    uint32_t pending_sequence;
    int have_peer;
} xqvoice_gui_ipc_t;

int xqvoice_gui_ipc_open(xqvoice_gui_ipc_t *ipc, const char *path);
void xqvoice_gui_ipc_close(xqvoice_gui_ipc_t *ipc, const char *path);
/* Returns 1 for a command, 0 when idle, and -1 after dropping bad input. */
int xqvoice_gui_ipc_receive(xqvoice_gui_ipc_t *ipc,
                            xqvoice_command_t *command);
int xqvoice_gui_ipc_reply(xqvoice_gui_ipc_t *ipc, xqvoice_reply_t reply,
                          const char *reason);

#endif
