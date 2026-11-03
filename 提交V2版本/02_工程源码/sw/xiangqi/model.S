    /* The local H128 evaluator model is a separate MicroSD payload.  The
     * bootloader validates xqmodel.bin and loads it at this fixed DDR range
     * before entering the GUI image.  Absolute symbols preserve the existing
     * C model interface without embedding another copy in xiangqi.bin. */
    .globl xq_model_start
    .globl xq_model_end
    .set xq_model_start, 0x0f000000
    .set xq_model_end,   0x0f032bb0
