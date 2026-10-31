#define _POSIX_C_SOURCE 200809L

#include "xqvoice_client.h"

#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <poll.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

static socklen_t unix_address(struct sockaddr_un *address, const char *path)
{
    memset(address, 0, sizeof(*address));
    address->sun_family = AF_UNIX;
    memcpy(address->sun_path, path, strlen(path) + 1);
    return (socklen_t)(offsetof(struct sockaddr_un, sun_path) +
                       strlen(path) + 1);
}

int xqvoice_client_open(xqvoice_client_t *client, const char *local_path,
                        const char *destination_path)
{
    struct sockaddr_un address;
    socklen_t address_bytes;

    if (!client || !local_path || !destination_path ||
        strlen(local_path) >= sizeof(client->local_path) ||
        strlen(destination_path) >= sizeof(client->destination_path))
        return 0;
    memset(client, 0, sizeof(*client));
    client->fd = -1;
    memcpy(client->local_path, local_path, strlen(local_path) + 1);
    memcpy(client->destination_path, destination_path,
           strlen(destination_path) + 1);
    client->fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (client->fd < 0)
        return 0;
    address_bytes = unix_address(&address, local_path);
    unlink(local_path);
    if (bind(client->fd, (struct sockaddr *)&address, address_bytes) < 0 ||
        chmod(local_path, 0600) < 0) {
        xqvoice_client_close(client);
        return 0;
    }
    return 1;
}

void xqvoice_client_close(xqvoice_client_t *client)
{
    if (!client)
        return;
    if (client->fd >= 0)
        close(client->fd);
    client->fd = -1;
    if (client->local_path[0])
        unlink(client->local_path);
}

int xqvoice_client_send(xqvoice_client_t *client,
                        const xqvoice_command_t *command,
                        char *reply, size_t reply_bytes, int timeout_ms)
{
    struct sockaddr_un destination;
    struct pollfd poll_fd;
    char datagram[XQVOICE_MAX_DATAGRAM];
    int bytes;

    if (!client || client->fd < 0 || !command)
        return 0;
    bytes = xqvoice_format_command(datagram, sizeof(datagram), command);
    if (!bytes)
        return 0;
    if (command->type == XQVOICE_COMMAND_DISPLAY) {
        char stale[128];
        unsigned int count;
        for (count = 0; count < 4; ++count)
            if (recv(client->fd, stale, sizeof(stale), MSG_DONTWAIT) <= 0)
                break;
    }
    if (sendto(client->fd, datagram, (size_t)bytes, MSG_DONTWAIT,
               (struct sockaddr *)&destination,
               unix_address(&destination, client->destination_path)) != bytes)
        return 0;
    if (!reply || !reply_bytes || timeout_ms <= 0)
        return 1;
    poll_fd.fd = client->fd;
    poll_fd.events = POLLIN;
    poll_fd.revents = 0;
    if (poll(&poll_fd, 1, timeout_ms) <= 0 || !(poll_fd.revents & POLLIN))
        return 1;
    {
        ssize_t received = recv(client->fd, reply, reply_bytes - 1, 0);
        if (received < 0)
            return errno == EAGAIN || errno == EWOULDBLOCK ? 1 : 0;
        reply[received] = '\0';
    }
    return 2;
}
