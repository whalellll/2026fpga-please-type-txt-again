#ifndef XQ_PICTURE_DISPLAY_H
#define XQ_PICTURE_DISPLAY_H
#include "xq_grid.h"
#define XQP_IMAGE_X 32
#define XQP_IMAGE_Y 96
#define XQP_IMAGE_W 640
#define XQP_IMAGE_H 360
#define XQP_CAL_X 736
#define XQP_CAL_Y 594
#define XQP_CAL_W 204
#define XQP_CAL_H 48
typedef struct {
    uint64_t capture_ms, inference_ms, mapping_ms, total_ms;
    uint32_t comparisons, matches, uncertain, unscored, invalid;
    uint32_t parameters;
    unsigned selected, has_frame, calibrating, corner_count;
    int is_stub,preview_only,manual_geometry;
    unsigned model_backend; /* 0 legacy, 1 PC assisted, 2 native driver experimental */
} xqp_metrics;
/* Linux renderer extension; shared bare-metal renderer/header stay frozen. */
void xq_fb_gui_picture_feedback(const char *line1, const char *line2,
                                 const char *line3);
/* pixels and geometry are ordinary RAM with process lifetime. Drawing uses
 * only aligned 32-bit writes to framebuffer mappings. NULL hides the page. */
void xq_fb_gui_picture_diagnostic(const uint32_t *pixels, const xqg_detection *,
                                  const xqv_result *, const xqp_metrics *);
/* Optional 320x360 rectified manual view, ordinary RAM. NULL selects raw. */
void xq_fb_gui_picture_topview(const uint32_t *pixels);
#endif
