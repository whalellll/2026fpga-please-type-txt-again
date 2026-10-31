#include <stdio.h>
#include <string.h>

#include "xiangqi_gui_command.h"

static int expect_move(const char *line, const char *expected)
{
    xq_gui_command_t command;
    if (!xq_gui_command_parse(line, &command) ||
        command.type != XQ_GUI_COMMAND_MOVE ||
        strcmp(command.move, expected) != 0) {
        fprintf(stderr, "XQ GUI COMMAND TEST FAIL line=%s\n", line);
        return 0;
    }
    return 1;
}

static int expect_type(const char *line, xq_gui_command_type_t expected)
{
    xq_gui_command_t command;
    if (!xq_gui_command_parse(line, &command) || command.type != expected) {
        fprintf(stderr, "XQ GUI COMMAND TEST FAIL line=%s\n", line);
        return 0;
    }
    return 1;
}

static int expect_rejected(const char *line)
{
    xq_gui_command_t command;
    if (xq_gui_command_parse(line, &command)) {
        fprintf(stderr, "XQ GUI COMMAND TEST ACCEPTED invalid line=%s\n", line);
        return 0;
    }
    return 1;
}

int main(void)
{
    if (!expect_move("XQ_MOVE h2e2\n", "h2e2") ||
        !expect_move("  XQ_MOVE\th2e2  ", "h2e2") ||
        !expect_type("XQ_NEWGAME\r\n", XQ_GUI_COMMAND_NEW_GAME) ||
        !expect_type("XQ_STATUS", XQ_GUI_COMMAND_STATUS) ||
        !expect_rejected("XQ_MOVE h2j2") ||
        !expect_rejected("XQ_MOVE h2e2 extra") ||
        !expect_rejected("XQ_NEWGAME now") ||
        !expect_rejected("XQ_STATUS extra") ||
        !expect_rejected("XQ_MOVE H2E2"))
        return 1;
    puts("XQ GUI COMMAND TEST PASS");
    return 0;
}
