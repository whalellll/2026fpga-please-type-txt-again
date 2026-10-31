#include "xqvoice_protocol.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int parse_u32(const char *text, uint32_t maximum, uint32_t *value)
{
    char *end;
    unsigned long parsed;

    if (!text || !*text)
        return 0;
    errno = 0;
    parsed = strtoul(text, &end, 10);
    if (errno || *end || parsed > maximum)
        return 0;
    *value = (uint32_t)parsed;
    return 1;
}

const char *xqvoice_piece_name(xqvoice_piece_t piece)
{
    static const char *const names[] = {
        "invalid", "ju", "ma", "pao", "bing", "zu", "shuai",
        "jiang", "shi", "xiang"
    };

    return (unsigned int)piece < sizeof(names) / sizeof(names[0]) ?
           names[piece] : names[0];
}

const char *xqvoice_action_name(xqvoice_action_t action)
{
    static const char *const names[] = {"invalid", "jin", "tui", "ping"};

    return (unsigned int)action < sizeof(names) / sizeof(names[0]) ?
           names[action] : names[0];
}

static xqvoice_piece_t parse_piece(const char *text)
{
    xqvoice_piece_t piece;

    for (piece = XQVOICE_PIECE_JU; piece <= XQVOICE_PIECE_XIANG; ++piece) {
        if (strcmp(text, xqvoice_piece_name(piece)) == 0)
            return piece;
    }
    return XQVOICE_PIECE_INVALID;
}

const char *xqvoice_display_state_name(xqvoice_display_state_t state)
{
    static const char *const names[] = {
        "INVALID", "LISTENING", "CAPTURING", "PARTIAL", "COMPLETE",
        "LOW_CONFIDENCE", "REJECTED", "OVERFLOW", "ERROR"
    };
    return (unsigned int)state < sizeof(names) / sizeof(names[0]) ?
           names[state] : names[0];
}

const char *xqvoice_token_text(uint8_t token)
{
    static const char *const names[] = {
        "", "车", "马", "炮", "兵", "卒", "帅", "将", "士", "象",
        "一", "二", "三", "四", "五", "六", "七", "八", "九",
        "进", "退", "平", "重来", "取消", "退出"
    };
    return token < sizeof(names) / sizeof(names[0]) ? names[token] : "";
}

static xqvoice_action_t parse_action(const char *text)
{
    xqvoice_action_t action;

    for (action = XQVOICE_ACTION_JIN; action <= XQVOICE_ACTION_PING;
         ++action) {
        if (strcmp(text, xqvoice_action_name(action)) == 0)
            return action;
    }
    return XQVOICE_ACTION_INVALID;
}

int xqvoice_parse_command(const void *data, size_t bytes,
                          xqvoice_command_t *command)
{
    char copy[XQVOICE_MAX_DATAGRAM + 1];
    char *tokens[10];
    char *save = NULL;
    char *token;
    size_t count = 0;
    uint32_t value;

    if (!data || !command || !bytes || bytes > XQVOICE_MAX_DATAGRAM ||
        memchr(data, '\0', bytes))
        return 0;
    memcpy(copy, data, bytes);
    copy[bytes] = '\0';
    while (bytes && (copy[bytes - 1] == '\n' || copy[bytes - 1] == '\r' ||
                     copy[bytes - 1] == ' ' || copy[bytes - 1] == '\t'))
        copy[--bytes] = '\0';

    token = strtok_r(copy, " \t", &save);
    while (token && count < sizeof(tokens) / sizeof(tokens[0])) {
        tokens[count++] = token;
        token = strtok_r(NULL, " \t", &save);
    }
    if (token || count < 4 || strcmp(tokens[0], "XQVOICE/1") != 0 ||
        !parse_u32(tokens[1], UINT32_MAX, &command->sequence))
        return 0;

    memset((char *)command + sizeof(command->sequence), 0,
           sizeof(*command) - sizeof(command->sequence));
    if (strcmp(tokens[2], "DISPLAY") == 0) {
        unsigned int state;
        size_t index;
        if (count < 5 || count > 5 + XQVOICE_DISPLAY_MAX_TOKENS ||
            !parse_u32(tokens[4], 1000, &value))
            return 0;
        command->confidence_permille = (uint16_t)value;
        for (state = XQVOICE_DISPLAY_LISTENING;
             state <= XQVOICE_DISPLAY_ERROR; ++state)
            if (strcmp(tokens[3], xqvoice_display_state_name(
                                      (xqvoice_display_state_t)state)) == 0)
                break;
        if (state > XQVOICE_DISPLAY_ERROR)
            return 0;
        command->type = XQVOICE_COMMAND_DISPLAY;
        command->display_state = (xqvoice_display_state_t)state;
        command->token_count = (uint8_t)(count - 5);
        for (index = 5; index < count; ++index) {
            if (!parse_u32(tokens[index], 24, &value) || !value)
                return 0;
            command->tokens[index - 5] = (uint8_t)value;
        }
        return 1;
    }
    if (strcmp(tokens[2], "MOVE") == 0) {
        if (count != 8)
            return 0;
        command->type = XQVOICE_COMMAND_MOVE;
        command->piece = parse_piece(tokens[3]);
        command->action = parse_action(tokens[5]);
        if (command->piece == XQVOICE_PIECE_INVALID ||
            command->action == XQVOICE_ACTION_INVALID ||
            !parse_u32(tokens[4], 9, &value) || value == 0)
            return 0;
        command->source_file = (uint8_t)value;
        if (!parse_u32(tokens[6], 9, &value) || value == 0)
            return 0;
        command->target = (uint8_t)value;
        if (!parse_u32(tokens[7], 1000, &value))
            return 0;
        command->confidence_permille = (uint16_t)value;
        return 1;
    }

    if (count != 4 || !parse_u32(tokens[3], 1000, &value))
        return 0;
    if (strcmp(tokens[2], "RESTART") == 0)
        command->type = XQVOICE_COMMAND_RESTART;
    else if (strcmp(tokens[2], "CANCEL") == 0)
        command->type = XQVOICE_COMMAND_CANCEL;
    else if (strcmp(tokens[2], "EXIT") == 0)
        command->type = XQVOICE_COMMAND_EXIT;
    else
        return 0;
    command->confidence_permille = (uint16_t)value;
    return 1;
}

int xqvoice_format_command(char *buffer, size_t bytes,
                           const xqvoice_command_t *command)
{
    const char *name;
    int written;

    if (!buffer || !bytes || !command ||
        command->confidence_permille > 1000)
        return 0;
    if (command->type == XQVOICE_COMMAND_DISPLAY) {
        unsigned int index;
        size_t used;
        if (command->display_state < XQVOICE_DISPLAY_LISTENING ||
            command->display_state > XQVOICE_DISPLAY_ERROR ||
            command->token_count > XQVOICE_DISPLAY_MAX_TOKENS)
            return 0;
        written = snprintf(buffer, bytes, "XQVOICE/1 %u DISPLAY %s %u",
                           command->sequence,
                           xqvoice_display_state_name(command->display_state),
                           command->confidence_permille);
        if (written <= 0 || (size_t)written >= bytes)
            return 0;
        used = (size_t)written;
        for (index = 0; index < command->token_count; ++index) {
            if (!command->tokens[index] || command->tokens[index] >= 25)
                return 0;
            written = snprintf(buffer + used, bytes - used, " %u",
                               command->tokens[index]);
            if (written <= 0 || (size_t)written >= bytes - used)
                return 0;
            used += (size_t)written;
        }
        if (used + 1 >= bytes)
            return 0;
        buffer[used++] = '\n';
        buffer[used] = '\0';
        return (int)used;
    } else if (command->type == XQVOICE_COMMAND_MOVE) {
        if (command->piece == XQVOICE_PIECE_INVALID ||
            command->action == XQVOICE_ACTION_INVALID ||
            command->source_file < 1 || command->source_file > 9 ||
            command->target < 1 || command->target > 9)
            return 0;
        written = snprintf(buffer, bytes, "XQVOICE/1 %u MOVE %s %u %s %u %u\n",
                           command->sequence,
                           xqvoice_piece_name(command->piece),
                           command->source_file,
                           xqvoice_action_name(command->action),
                           command->target, command->confidence_permille);
    } else {
        if (command->type == XQVOICE_COMMAND_RESTART)
            name = "RESTART";
        else if (command->type == XQVOICE_COMMAND_CANCEL)
            name = "CANCEL";
        else if (command->type == XQVOICE_COMMAND_EXIT)
            name = "EXIT";
        else
            return 0;
        written = snprintf(buffer, bytes, "XQVOICE/1 %u %s %u\n",
                           command->sequence, name,
                           command->confidence_permille);
    }
    return written > 0 && (size_t)written < bytes ? written : 0;
}
