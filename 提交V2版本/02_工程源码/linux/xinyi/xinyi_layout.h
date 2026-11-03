#ifndef XINYI_LAYOUT_H
#define XINYI_LAYOUT_H
/* Shared native draw/hit rectangles; right and bottom edges are exclusive. */
typedef struct { unsigned x,y,w,h; } xy_rect;
enum { XY_BOARD_X=176, XY_BOARD_Y=160, XY_BOARD_CELL=88 };
static const xy_rect xy_layout_home_start={112,336,300,76};
static const xy_rect xy_layout_home_coremark={440,336,330,76};
static const xy_rect xy_layout_home_cm_log={800,336,360,76};
static const xy_rect xy_layout_home_cm_reference={1190,336,610,76};
static const xy_rect xy_layout_cm_log_close={1090,958,300,64};
static const xy_rect xy_layout_cm_log_prev={112,958,300,64};
static const xy_rect xy_layout_cm_log_next={440,958,300,64};
static const xy_rect xy_layout_coremark_cancel={1430,980,370,58};
static const xy_rect xy_layout_mode_switch={1052,962,280,48};
static const xy_rect xy_layout_voice_restart={1352,962,196,48};
static const xy_rect xy_layout_game_home={1568,962,224,48};
#endif
