#ifndef XQVOICE_DISPLAY_H
#define XQVOICE_DISPLAY_H

#include "xqvoice_protocol.h"

/* Linux GUI preview state only. These functions cannot modify chess state. */
void xq_fb_gui_set_voice_display(const xqvoice_command_t *event);
void xq_fb_gui_refresh_voice_display(void);

#endif
