#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include "xqvoice_client.h"
#include "xqvoice_gui_ipc.h"

int main(void)
{
    char server_path[96];
    char client_a_path[96];
    char client_b_path[96];
    xqvoice_gui_ipc_t server;
    xqvoice_client_t client_a;
    xqvoice_client_t client_b;
    xqvoice_command_t sent;
    xqvoice_command_t received;
    long pid = (long)getpid();

    (void)snprintf(server_path, sizeof(server_path),
                   "/tmp/xqvoice-gui-test-%ld.sock", pid);
    (void)snprintf(client_a_path, sizeof(client_a_path),
                   "/tmp/xqvoice-client-a-%ld.sock", pid);
    (void)snprintf(client_b_path, sizeof(client_b_path),
                   "/tmp/xqvoice-client-b-%ld.sock", pid);
    if (!xqvoice_gui_ipc_open(&server, server_path) ||
        !xqvoice_client_open(&client_a, client_a_path, server_path)) {
        fprintf(stderr, "XQVOICE_GUI_IPC_FAIL open\n");
        return 1;
    }

    memset(&sent, 0, sizeof(sent));
    sent.sequence = 2;
    sent.type = XQVOICE_COMMAND_RESTART;
    sent.confidence_permille = 1000;
    if (xqvoice_client_send(&client_a, &sent, NULL, 0, 0) != 1 ||
        xqvoice_gui_ipc_receive(&server, &received) != 1 ||
        received.sequence != 2) {
        fprintf(stderr, "XQVOICE_GUI_IPC_FAIL first\n");
        return 1;
    }
    if (xqvoice_client_send(&client_a, &sent, NULL, 0, 0) != 1 ||
        xqvoice_gui_ipc_receive(&server, &received) != -1) {
        fprintf(stderr, "XQVOICE_GUI_IPC_FAIL replay\n");
        return 1;
    }

    if (!xqvoice_client_open(&client_b, client_b_path, server_path)) {
        fprintf(stderr, "XQVOICE_GUI_IPC_FAIL second-client\n");
        return 1;
    }
    sent.sequence = 1;
    if (xqvoice_client_send(&client_b, &sent, NULL, 0, 0) != 1 ||
        xqvoice_gui_ipc_receive(&server, &received) != 1 ||
        received.sequence != 1) {
        fprintf(stderr, "XQVOICE_GUI_IPC_FAIL restart-sequence\n");
        return 1;
    }

    xqvoice_client_close(&client_b);
    xqvoice_client_close(&client_a);
    xqvoice_gui_ipc_close(&server, server_path);
    puts("XQVOICE_GUI_IPC_PASS replay=same-peer restart=new-peer");
    return 0;
}
