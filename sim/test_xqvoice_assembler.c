#include <stdio.h>
#include <string.h>

#include "xqvoice_assembler.h"

int main(void)
{
    xqvoice_assembler_t assembler;
    xqvoice_command_t command;
    char error[128];

    xqvoice_assembler_reset(&assembler);
    if (xqvoice_assembler_feed(&assembler, 2, 900, 1, &command,
                               error, sizeof(error)) != 0 ||
        xqvoice_assembler_feed(&assembler, 15, 850, 1, &command,
                               error, sizeof(error)) != 0 ||
        xqvoice_assembler_feed(&assembler, 19, 800, 1, &command,
                               error, sizeof(error)) != 0 ||
        xqvoice_assembler_feed(&assembler, 16, 750, 1, &command,
                               error, sizeof(error)) != 1 ||
        command.type != XQVOICE_COMMAND_MOVE ||
        command.piece != XQVOICE_PIECE_MA || command.source_file != 6 ||
        command.action != XQVOICE_ACTION_JIN || command.target != 7 ||
        command.confidence_permille != 750 ||
        xqvoice_assembler_pending(&assembler)) {
        fprintf(stderr, "XQVOICE_ASSEMBLER_FAIL move=%s\n", error);
        return 1;
    }
    if (xqvoice_assembler_feed(&assembler, 15, 900, 2, &command,
                               error, sizeof(error)) >= 0 ||
        xqvoice_assembler_pending(&assembler)) {
        fprintf(stderr, "XQVOICE_ASSEMBLER_FAIL order=%s\n", error);
        return 1;
    }
    if (xqvoice_assembler_feed(&assembler, 22, 900, 2, &command,
                               error, sizeof(error)) != 1 ||
        command.type != XQVOICE_COMMAND_RESTART) {
        fprintf(stderr, "XQVOICE_ASSEMBLER_FAIL control=%s\n", error);
        return 1;
    }
    puts("XQVOICE_ASSEMBLER_PASS phrase=ma-liu-jin-qi controls=immediate");
    return 0;
}
