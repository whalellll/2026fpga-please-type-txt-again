#define _POSIX_C_SOURCE 200809L

#include "xqvoice_client.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void usage(const char *program)
{
    fprintf(stderr,
            "usage: %s MOVE piece source jin|tui|ping target [confidence]\n"
            "       %s RESTART|CANCEL|EXIT [confidence]\n"
            "       %s DISPLAY state score [token-id ... (max 4)]\n",
            program, program, program);
}

int main(int argc, char **argv)
{
    xqvoice_client_t client;
    xqvoice_command_t command;
    char local[96];
    char wire[XQVOICE_MAX_DATAGRAM];
    char reply[128] = {0};
    int sent;

    memset(&command, 0, sizeof(command));
    command.sequence = 1;
    command.confidence_permille = 1000;
    if (argc >= 4 && argc <= 8 && strcmp(argv[1], "DISPLAY") == 0) {
        int index;
        int bytes = snprintf(wire, sizeof(wire), "XQVOICE/1 1 DISPLAY %s %s",
                             argv[2], argv[3]);
        size_t used;
        if (bytes <= 0 || (size_t)bytes >= sizeof(wire))
            return 2;
        used = (size_t)bytes;
        for (index = 4; index < argc; ++index) {
            bytes = snprintf(wire + used, sizeof(wire) - used, " %s", argv[index]);
            if (bytes <= 0 || (size_t)bytes >= sizeof(wire) - used)
                return 2;
            used += (size_t)bytes;
        }
        if (!xqvoice_parse_command(wire, used, &command)) {
            usage(argv[0]);
            return 2;
        }
    } else if (argc >= 2 && strcmp(argv[1], "MOVE") == 0 &&
        (argc == 6 || argc == 7)) {
        int bytes = snprintf(wire, sizeof(wire),
            "XQVOICE/1 1 MOVE %s %s %s %s %s\n", argv[2], argv[3], argv[4],
            argv[5], argc == 7 ? argv[6] : "1000");
        if (bytes <= 0 || (size_t)bytes >= sizeof(wire) ||
            !xqvoice_parse_command(wire, (size_t)bytes, &command)) {
            usage(argv[0]);
            return 2;
        }
    } else if (argc >= 2 && argc <= 3) {
        const char *confidence = argc == 3 ? argv[2] : "1000";
        int bytes = snprintf(wire, sizeof(wire), "XQVOICE/1 1 %s %s\n",
                             argv[1], confidence);
        if (bytes <= 0 || (size_t)bytes >= sizeof(wire) ||
            !xqvoice_parse_command(wire, (size_t)bytes, &command)) {
            usage(argv[0]);
            return 2;
        }
    } else {
        usage(argv[0]);
        return 2;
    }

    (void)snprintf(local, sizeof(local), "/run/xqvoice-send-%ld.sock",
                   (long)getpid());
    if (!xqvoice_client_open(&client, local, XQVOICE_GUI_SOCKET)) {
        perror("xqvoice-send: socket");
        return 3;
    }
    sent = xqvoice_client_send(&client, &command, reply, sizeof(reply), 1000);
    xqvoice_client_close(&client);
    if (!sent) {
        perror("xqvoice-send: send");
        return 4;
    }
    if (sent == 2)
        fputs(reply, stdout);
    else
        puts("XQVOICE_SEND_NO_REPLY");
    return 0;
}
