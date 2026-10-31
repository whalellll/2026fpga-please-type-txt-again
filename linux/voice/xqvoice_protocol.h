#ifndef XQVOICE_PROTOCOL_H
#define XQVOICE_PROTOCOL_H

#include <stddef.h>
#include <stdint.h>

#define XQVOICE_PROTOCOL_VERSION 1u
#define XQVOICE_GUI_SOCKET "/run/xiangqi-gui-command.sock"
#define XQVOICE_MAX_DATAGRAM 128u

typedef enum {
    XQVOICE_COMMAND_INVALID = 0,
    XQVOICE_COMMAND_MOVE,
    XQVOICE_COMMAND_RESTART,
    XQVOICE_COMMAND_CANCEL,
    XQVOICE_COMMAND_EXIT,
    XQVOICE_COMMAND_DISPLAY
} xqvoice_command_type_t;

#define XQVOICE_DISPLAY_MAX_TOKENS 4u
typedef enum {
    XQVOICE_DISPLAY_INVALID = 0,
    XQVOICE_DISPLAY_LISTENING,
    XQVOICE_DISPLAY_CAPTURING,
    XQVOICE_DISPLAY_PARTIAL,
    XQVOICE_DISPLAY_COMPLETE,
    XQVOICE_DISPLAY_LOW_CONFIDENCE,
    XQVOICE_DISPLAY_REJECTED,
    XQVOICE_DISPLAY_OVERFLOW,
    XQVOICE_DISPLAY_ERROR
} xqvoice_display_state_t;

typedef enum {
    XQVOICE_PIECE_INVALID = 0,
    XQVOICE_PIECE_JU,
    XQVOICE_PIECE_MA,
    XQVOICE_PIECE_PAO,
    XQVOICE_PIECE_BING,
    XQVOICE_PIECE_ZU,
    XQVOICE_PIECE_SHUAI,
    XQVOICE_PIECE_JIANG,
    XQVOICE_PIECE_SHI,
    XQVOICE_PIECE_XIANG
} xqvoice_piece_t;

typedef enum {
    XQVOICE_ACTION_INVALID = 0,
    XQVOICE_ACTION_JIN,
    XQVOICE_ACTION_TUI,
    XQVOICE_ACTION_PING
} xqvoice_action_t;

typedef struct {
    uint32_t sequence;
    xqvoice_command_type_t type;
    xqvoice_piece_t piece;
    xqvoice_action_t action;
    uint8_t source_file;
    uint8_t target;
    uint16_t confidence_permille;
    xqvoice_display_state_t display_state;
    uint8_t token_count;
    uint8_t tokens[XQVOICE_DISPLAY_MAX_TOKENS];
} xqvoice_command_t;

int xqvoice_parse_command(const void *data, size_t bytes,
                          xqvoice_command_t *command);
int xqvoice_format_command(char *buffer, size_t bytes,
                           const xqvoice_command_t *command);
const char *xqvoice_piece_name(xqvoice_piece_t piece);
const char *xqvoice_action_name(xqvoice_action_t action);
const char *xqvoice_display_state_name(xqvoice_display_state_t state);
const char *xqvoice_token_text(uint8_t token);

#endif
