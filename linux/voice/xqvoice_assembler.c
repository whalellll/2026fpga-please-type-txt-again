#include "xqvoice_assembler.h"

#include <stdio.h>
#include <string.h>

static void set_error(char *output, size_t output_bytes, const char *message)
{
    if (output && output_bytes)
        (void)snprintf(output, output_bytes, "%s", message);
}

void xqvoice_assembler_reset(xqvoice_assembler_t *assembler)
{
    if (assembler)
        memset(assembler, 0, sizeof(*assembler));
}

int xqvoice_assembler_pending(const xqvoice_assembler_t *assembler)
{
    return assembler && assembler->count != 0;
}

static int valid_for_slot(uint8_t slot, uint8_t token)
{
    if (slot == 0)
        return token >= 1 && token <= 9;
    if (slot == 1 || slot == 3)
        return token >= 10 && token <= 18;
    return slot == 2 && token >= 19 && token <= 21;
}

int xqvoice_assembler_feed(xqvoice_assembler_t *assembler, uint8_t token,
                           uint16_t confidence, uint32_t sequence,
                           xqvoice_command_t *command,
                           char *error, size_t error_bytes)
{
    if (!assembler || !command || token == 0 || token >= 25) {
        set_error(error, error_bytes, "bad token assembler arguments");
        return -1;
    }
    memset(command, 0, sizeof(*command));
    if (token >= 22) {
        command->sequence = sequence;
        command->confidence_permille = confidence;
        command->type = token == 22 ? XQVOICE_COMMAND_RESTART :
                        token == 23 ? XQVOICE_COMMAND_CANCEL :
                                      XQVOICE_COMMAND_EXIT;
        xqvoice_assembler_reset(assembler);
        set_error(error, error_bytes, "control command complete");
        return 1;
    }
    if (!valid_for_slot(assembler->count, token)) {
        if (token >= 1 && token <= 9)
            xqvoice_assembler_reset(assembler);
        else {
            xqvoice_assembler_reset(assembler);
            set_error(error, error_bytes, "token violates command order");
            return -1;
        }
    }
    assembler->tokens[assembler->count++] = token;
    if (assembler->count == 1 || confidence < assembler->minimum_confidence)
        assembler->minimum_confidence = confidence;
    if (assembler->count < 4) {
        set_error(error, error_bytes, "waiting for next token");
        return 0;
    }
    command->sequence = sequence;
    command->confidence_permille = assembler->minimum_confidence;
    command->type = XQVOICE_COMMAND_MOVE;
    command->piece = (xqvoice_piece_t)assembler->tokens[0];
    command->source_file = (uint8_t)(assembler->tokens[1] - 9);
    command->action = (xqvoice_action_t)(assembler->tokens[2] - 18);
    command->target = (uint8_t)(assembler->tokens[3] - 9);
    xqvoice_assembler_reset(assembler);
    set_error(error, error_bytes, "move command complete");
    return 1;
}
