#ifndef XIANGQI_GUI_COMMAND_H
#define XIANGQI_GUI_COMMAND_H

#include <stdint.h>

#define XQ_GUI_COMMAND_MOVE_CAPACITY 5u

typedef enum {
    XQ_GUI_COMMAND_INVALID = 0,
    XQ_GUI_COMMAND_MOVE,
    XQ_GUI_COMMAND_NEW_GAME,
    XQ_GUI_COMMAND_STATUS
} xq_gui_command_type_t;

typedef struct {
    xq_gui_command_type_t type;
    char move[XQ_GUI_COMMAND_MOVE_CAPACITY];
} xq_gui_command_t;

/* Parse one complete, NUL-terminated software-control line. */
int xq_gui_command_parse(const char *line, xq_gui_command_t *command);

#endif
