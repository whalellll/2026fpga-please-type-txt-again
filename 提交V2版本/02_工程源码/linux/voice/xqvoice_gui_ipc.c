#define _POSIX_C_SOURCE 200809L

#include "xqvoice_gui_ipc.h"

#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int same_peer(const xqvoice_gui_ipc_t *ipc,
                     const struct sockaddr_un *peer, socklen_t peer_bytes)
{
    size_t old_length;
    size_t new_length;

    if (!ipc->have_peer || peer->sun_family != AF_UNIX ||
        peer->sun_path[0] == '\0')
        return 0;
    old_length = strnlen(ipc->peer.sun_path, sizeof(ipc->peer.sun_path));
    new_length = strnlen(peer->sun_path, sizeof(peer->sun_path));
    return ipc->peer_bytes == peer_bytes && old_length == new_length &&
           memcmp(ipc->peer.sun_path, peer->sun_path, new_length) == 0;
}

int xqvoice_gui_ipc_open(xqvoice_gui_ipc_t *ipc, const char *path)
{
    struct sockaddr_un address;
    int flags;

    if (!ipc || !path || strlen(path) >= sizeof(address.sun_path))
        return 0;
    memset(ipc, 0, sizeof(*ipc));
    ipc->fd = -1;
    ipc->fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (ipc->fd < 0)
        return 0;
    flags = fcntl(ipc->fd, F_GETFL, 0);
    if (flags < 0 || fcntl(ipc->fd, F_SETFL, flags | O_NONBLOCK) < 0)
        goto fail;

    memset(&address, 0, sizeof(address));
    address.sun_family = AF_UNIX;
    memcpy(address.sun_path, path, strlen(path) + 1);
    unlink(path);
    if (bind(ipc->fd, (struct sockaddr *)&address,
             (socklen_t)(offsetof(struct sockaddr_un, sun_path) +
                         strlen(path) + 1)) < 0 || chmod(path, 0600) < 0)
        goto fail_unlink;
    return 1;

fail_unlink:
    unlink(path);
fail:
    close(ipc->fd);
    ipc->fd = -1;
    return 0;
}

void xqvoice_gui_ipc_close(xqvoice_gui_ipc_t *ipc, const char *path)
{
    if (!ipc)
        return;
    if (ipc->fd >= 0)
        close(ipc->fd);
    ipc->fd = -1;
    if (path)
        unlink(path);
}

int xqvoice_gui_ipc_receive(xqvoice_gui_ipc_t *ipc,
                            xqvoice_command_t *command)
{
    char datagram[XQVOICE_MAX_DATAGRAM];
    struct sockaddr_un peer;
    socklen_t peer_bytes = sizeof(peer);
    ssize_t received;

    if (!ipc || ipc->fd < 0 || !command)
        return 0;
    memset(&peer, 0, sizeof(peer));
    received = recvfrom(ipc->fd, datagram, sizeof(datagram), 0,
                        (struct sockaddr *)&peer, &peer_bytes);
    if (received < 0)
        return errno == EAGAIN || errno == EWOULDBLOCK ? 0 : -1;
    if (!received || !xqvoice_parse_command(datagram, (size_t)received,
                                             command))
        return -1;
    if (ipc->have_sequence && same_peer(ipc, &peer, peer_bytes) &&
        (int32_t)(command->sequence - ipc->last_sequence) <= 0)
        return -1;
    ipc->last_sequence = command->sequence;
    ipc->have_sequence = 1;
    ipc->pending_sequence = command->sequence;
    ipc->peer = peer;
    ipc->peer_bytes = peer_bytes;
    ipc->have_peer = peer.sun_family == AF_UNIX && peer.sun_path[0] != '\0';
    return 1;
}

int xqvoice_gui_ipc_reply(xqvoice_gui_ipc_t *ipc, xqvoice_reply_t reply,
                          const char *reason)
{
    char message[128];
    const char *status;
    int bytes;

    if (!ipc || ipc->fd < 0)
        return 0;
    if (reply == XQVOICE_REPLY_APPLIED)
        status = "APPLIED";
    else if (reply == XQVOICE_REPLY_REJECTED)
        status = "REJECTED";
    else if (reply == XQVOICE_REPLY_BUSY)
        status = "BUSY";
    else if (reply == XQVOICE_REPLY_DISPLAYED)
        status = "DISPLAYED";
    else
        return 0;
    if (!reason || !*reason)
        reason = "none";
    bytes = snprintf(message, sizeof(message), "XQGUI/1 %u %s %s\n",
                     ipc->pending_sequence, status, reason);
    if (bytes <= 0 || (size_t)bytes >= sizeof(message))
        return 0;
    if (!ipc->have_peer)
        return 1;
    return sendto(ipc->fd, message, (size_t)bytes, MSG_DONTWAIT,
                  (struct sockaddr *)&ipc->peer, ipc->peer_bytes) == bytes;
}
