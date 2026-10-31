#ifndef XINYI_LAYOUT_H
#define XINYI_LAYOUT_H
#include "../xinyi_board/gui_options.h"
/* Shared native draw/hit rectangles; right and bottom edges are exclusive. */
typedef struct { unsigned x,y,w,h; } xy_rect;
enum { XY_BOARD_X=176, XY_BOARD_Y=160, XY_BOARD_CELL=88 };
#if XINYI_HOME_R13
static const xy_rect xy_layout_home_start={760,340,400,92};
static const xy_rect xy_layout_home_coremark={760,468,400,92};
static const xy_rect xy_layout_home_camera={760,596,400,92};
static const xy_rect xy_layout_home_exit={760,724,400,92};
static const xy_rect xy_layout_home_cm_log={600,832,320,68};
static const xy_rect xy_layout_home_cm_reference={952,832,390,68};
static const xy_rect xy_layout_cm_run={248,832,320,68};
static const xy_rect xy_layout_detail_home={1374,832,300,68};
static const xy_rect xy_layout_preview_start={600,648,720,84};
#else
static const xy_rect xy_layout_home_start={112,336,300,76};
static const xy_rect xy_layout_home_coremark={440,336,330,76};
static const xy_rect xy_layout_home_cm_log={800,336,360,76};
static const xy_rect xy_layout_home_cm_reference={1190,336,610,76};
#endif
static const xy_rect xy_layout_cm_log_close={1090,958,300,64};
static const xy_rect xy_layout_cm_log_prev={112,958,300,64};
static const xy_rect xy_layout_cm_log_next={440,958,300,64};
static const xy_rect xy_layout_coremark_cancel={1430,980,370,58};
static const xy_rect xy_layout_mode_switch={1052,962,280,48};
static const xy_rect xy_layout_voice_restart={1352,962,196,48};
static const xy_rect xy_layout_game_home={1568,962,224,48};
#if XINYI_BATTLE_R17
/* Four identical chess discs: two mode choices, restart, home. Hit testing
 * uses the same inscribed circle, never the unused rectangle corners. */
static const xy_rect xy_layout_battle_nav[4]={
    {1080,856,144,144},{1260,856,144,144},
    {1440,856,144,144},{1620,856,144,144}};
#endif
#endif
