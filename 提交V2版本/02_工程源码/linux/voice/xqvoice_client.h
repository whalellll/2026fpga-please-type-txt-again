#ifndef XQVOICE_CLIENT_H
#define XQVOICE_CLIENT_H

#include <stddef.h>

#include "xqvoice_protocol.h"

typedef struct {
    int fd;
    char local_path[108];
    char destination_path[108];
} xqvoice_client_t;

int xqvoice_client_open(xqvoice_client_t *client, const char *local_path,
                        const char *destination_path);
void xqvoice_client_close(xqvoice_client_t *client);
int xqvoice_client_send(xqvoice_client_t *client,
                        const xqvoice_command_t *command,
                        char *reply, size_t reply_bytes, int timeout_ms);

#endif
