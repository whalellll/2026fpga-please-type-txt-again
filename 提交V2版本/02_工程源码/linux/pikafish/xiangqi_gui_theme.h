/* User-selected light palette by default; dark remains an explicit option. */
#ifndef XIANGQI_GUI_THEME_H
#define XIANGQI_GUI_THEME_H
#define XQ_RGB565(r,g,b) ((((r) >> 3) << 11) | (((g) >> 2) << 5) | ((b) >> 3))

#if defined(XQ_GUI_LIGHT_THEME) && defined(XQ_GUI_DARK_THEME)
#error "Select only one GUI theme"
#endif

#ifndef XQ_GUI_DARK_THEME
#define C_BG       XQ_RGB565(244,240,232)
#define C_PANEL    XQ_RGB565(249,247,240)
#define C_CARD     XQ_RGB565(255,253,247)
#define C_BORDER   XQ_RGB565(222,216,202)
#define C_SHADOW   XQ_RGB565(214,207,192)
#define C_DIVIDER  XQ_RGB565(215,210,196)
#define C_TEXT     XQ_RGB565(52,61,55)
#define C_GOLD     XQ_RGB565(151,77,46)
#define C_GREEN    XQ_RGB565(72,102,87)
#else
#define C_BG       0x1083u
#define C_PANEL    0x18e4u
#define C_CARD     C_PANEL
#define C_BORDER   0x2986u
#define C_SHADOW   0x0842u
#define C_DIVIDER  0x39e7u
#define C_TEXT     0xef5bu
#define C_GOLD     0xd4ceu
#define C_GREEN    0x7d13u
#endif

/* Wood and piece colours are shared by both themes. */
#define C_BOARD    0xd5eeu
#define C_LINE     0x61e6u
#define C_PIECE    0xff5au
#define C_RED      0xb166u
#define C_BLACK    0x2945u
#endif
