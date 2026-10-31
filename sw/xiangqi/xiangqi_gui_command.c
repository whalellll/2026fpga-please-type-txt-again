#include "xiangqi_gui_command.h"

#include <string.h>

static const char *skip_space(const char *text)
{
    while (*text == ' ' || *text == '\t')
        ++text;
    return text;
}

static int end_of_line(const char *text)
{
    text = skip_space(text);
    return *text == '\0' || *text == '\r' || *text == '\n';
}

static int parse_move(const char *text, xq_gui_command_t *command)
{
    unsigned int index;

    text = skip_space(text);
    for (index = 0u; index < 4u; ++index) {
        char value = text[index];
        if ((index & 1u) == 0u) {
            if (value < 'a' || value > 'i')
                return 0;
        } else if (value < '0' || value > '9') {
            return 0;
        }
        command->move[index] = value;
    }
    command->move[4] = '\0';
    return end_of_line(text + 4);
}

int xq_gui_command_parse(const char *line, xq_gui_command_t *command)
{
    const char *cursor;
    const char *token_end;
    size_t token_length;

    if (line == 0 || command == 0)
        return 0;
    memset(command, 0, sizeof(*command));
    cursor = skip_space(line);
    token_end = cursor;
    while (*token_end != '\0' && *token_end != ' ' &&
           *token_end != '\t' && *token_end != '\r' &&
           *token_end != '\n')
        ++token_end;
    token_length = (size_t)(token_end - cursor);
    if (token_length == 7u && memcmp(cursor, "XQ_MOVE", 7u) == 0) {
        if (!parse_move(token_end, command))
            return 0;
        command->type = XQ_GUI_COMMAND_MOVE;
        return 1;
    }
    if (token_length == 10u && memcmp(cursor, "XQ_NEWGAME", 10u) == 0) {
        if (!end_of_line(token_end))
            return 0;
        command->type = XQ_GUI_COMMAND_NEW_GAME;
        return 1;
    }
    if (token_length == 9u && memcmp(cursor, "XQ_STATUS", 9u) == 0) {
        if (!end_of_line(token_end))
            return 0;
        command->type = XQ_GUI_COMMAND_STATUS;
        return 1;
    }
    return 0;
}
