#ifndef XQ_ROI_H
#define XQ_ROI_H
#include "xq_grid.h"

/* CPU-side, ordinary RAM only. This is an image/detection contract, not a
 * quantized model implementation. RGB channel order is explicit throughout.
 */
#define XQR_MAX_DETECTIONS 300u
#define XQR_PATCH_SIZE 32u
typedef struct { int x0,y0,x1,y1; } xqr_roi; /* half open */
typedef struct { float x0,y0,x1,y1,score; unsigned class_id; } xqr_box;
typedef struct {
    unsigned size,width,height,left,top;
    double ratio,pad_x,pad_y; /* nominal ratio; before resize integer rounding */
    xqr_roi roi;
} xqr_letterbox;
typedef struct {
    xqg_grid grid;
    double corners[4][2]; /* a0,i0,i9,a9; independent of ROI rectangle */
    xqr_roi roi;
    uint64_t view_id;
} xqr_manual;
int xqr_roi_valid(xqr_roi);
int xqr_letterbox_plan(xqr_roi,unsigned input_size,xqr_letterbox *);
int xqr_rgb565(const xqv_frame *,uint8_t *rgb,size_t capacity);
/* OpenCV INTER_LINEAR byte semantics, subject to independent PC vector check.
 * Source crop bounds can include constant-114 padding. Output is RGB CHW.
 */
int xqr_resize_rgb(const uint8_t *rgb,unsigned width,unsigned height,size_t stride,
                   int x0,int y0,int x1,int y1,unsigned dst_w,unsigned dst_h,
                   uint8_t *chw,size_t capacity);
int xqr_detector_input(const uint8_t *rgb,xqr_roi,unsigned input_size,
                       uint8_t *chw,size_t capacity,xqr_letterbox *);
int xqr_piece_crop(const uint8_t *rgb,const xqr_box *,uint8_t *chw,size_t capacity);
int xqr_box_original(const xqr_letterbox *,xqr_box *);
/* NMS input must be in one coordinate space and one frozen frame. workspace
 * holds count boxes, output capacity >= requested max_det (<=300). Ties use
 * original input order; Torch GPU tie equivalence awaits delivered vectors.
 * The detector adapter owns YOLO raw-head decoding and its top-30000
 * prelimit. This utility is used directly for the <=300 second-stage boxes.
 */
int xqr_nms(const xqr_box *,unsigned count,float threshold,float iou,unsigned max_det,
            xqr_box *workspace,size_t workspace_count,xqr_box *out,unsigned *out_count);
int xqr_fuse(const xqr_box *,const float *probabilities15,unsigned count,
             xqr_box *out,unsigned *out_count);
int xqr_manual_init(xqr_manual *,xqr_roi,const double corners[4][2],uint64_t view_id);
/* Moving camera/board requires an explicit new view_id/setup. This provider
 * cannot detect movement; never advertise automatic geometric self-healing.
 * Outside-quadrilateral centres are dropped before conservative legacy map.
 */
int xqr_map(const xqr_manual *,uint64_t view_id,const xqr_box *,unsigned count,
            uint32_t frame,float threshold,xqv_result *out,unsigned *outside);
/* Rectified viewer only; no pixels from a tracked position or model stub. */
int xqr_rectify(const xqr_manual *,const xqv_frame *,uint32_t *ordinary_rgb565,
                unsigned width,unsigned height,size_t capacity);
#endif
