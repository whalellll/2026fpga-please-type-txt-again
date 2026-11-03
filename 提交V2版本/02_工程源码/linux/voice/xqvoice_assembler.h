#ifndef XQVOICE_ASSEMBLER_H
#define XQVOICE_ASSEMBLER_H

#include <stddef.h>
#include <stdint.h>

#include "xqvoice_protocol.h"

typedef struct {
    uint8_t tokens[4];
    uint8_t count;
    uint16_t minimum_confidence;
} xqvoice_assembler_t;

void xqvoice_assembler_reset(xqvoice_assembler_t *assembler);
int xqvoice_assembler_pending(const xqvoice_assembler_t *assembler);
int xqvoice_assembler_feed(xqvoice_assembler_t *assembler, uint8_t token,
                           uint16_t confidence, uint32_t sequence,
                           xqvoice_command_t *command,
                           char *error, size_t error_bytes);

#endif
