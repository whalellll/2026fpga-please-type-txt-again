#ifndef XQ_ROI_PIPELINE_H
#define XQ_ROI_PIPELINE_H
#include "xq_roi.h"
/* The package loader must verify the integer models and golden acceptance
 * before supplying validated=1. There is deliberately no default backend.
 * Callbacks own their internal MAC/ioctl timeout and return 1 only on success.
 */
typedef struct {
    void *context;
    unsigned input_size;
    int validated,synthetic_test;
    /* Input bytes are RGB CHW pixels, not normalized/quantized tensors.
     * The model adapter owns its delivered normalization and quantization.
     * Output = post-first-NMS <=300 boxes in letterbox input coordinates. */
    int (*detector)(void *,const uint8_t *,unsigned,xqr_box *,unsigned *);
    /* Patch = RGB CHW32 from the original full-resolution image.
     * Output probabilities15, after the delivered classifier softmax. */
    int (*classifier)(void *,const uint8_t *,float probabilities15[15]);
    int (*cancelled)(void *);
    uint64_t (*now_ms)(void *);
} xqr_backend;
typedef struct {
    uint64_t rgb_ms,letterbox_ms,detector_ms,crop_ms,classifier_ms,nms_ms,map_ms,total_ms;
    unsigned proposals,background,classified,retained,outside;
    uint64_t capture_id,view_id;
    uint32_t frame_id;
    int synthetic_test;
} xqr_timing;
typedef enum {XQR_OK,XQR_NO_MODEL,XQR_BAD_REQUEST,XQR_BUSY,XQR_CANCELLED,
              XQR_DETECTOR_FAILED,XQR_CLASSIFIER_FAILED,XQR_GEOMETRY_FAILED} xqr_status;
typedef struct {
    xqr_backend backend;
    uint8_t *rgb,*input;
    uint64_t last_capture_id;
    unsigned busy;
} xqr_pipeline;
int xqr_pipeline_open(xqr_pipeline *,const xqr_backend *);
int xqr_pipeline_close(xqr_pipeline *);
/* Serialized per context, input frame remains immutable. Failed/cancelled
 * work never publishes FEN. Synthetic callbacks always mark result.is_stub.
 * All stages use the same capture token, frame and explicit manual view id.
 */
xqr_status xqr_pipeline_run(xqr_pipeline *,const xqv_frame *,uint64_t capture_id,
                           const xqr_manual *,uint64_t view_id,float usable_threshold,
                           xqv_result *,xqr_timing *);
#endif
