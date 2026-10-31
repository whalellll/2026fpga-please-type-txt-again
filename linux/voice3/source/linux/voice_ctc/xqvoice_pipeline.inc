/* One CPU caller; FPGA computation overlaps work on private host RAM.
 * No layer/utterance is reordered and no two hardware jobs run together. */
static void pack_mac_tile(uint8_t *stage,const uint8_t *current,unsigned t,
    unsigned start,unsigned pixels,unsigned ci,unsigned k,unsigned stride,
    unsigned dilation,unsigned pad)
{
    unsigned p,kernel,channel,K=ci*k;
    memset(stage,0,(size_t)pixels*K*2u);
    for(p=0;p<pixels;p++) {
        int32_t source_base=(int32_t)((start+p)*stride)-(int32_t)pad;
        size_t base=(size_t)p*K*2u;
        for(kernel=0;kernel<k;kernel++) {
            int32_t source=source_base+(int32_t)(kernel*dilation);
            if(source>=0 && (unsigned)source<t) {
                const uint8_t *row=current+(size_t)(unsigned)source*ci;
                size_t slot=base+(size_t)kernel*ci*2u;
                for(channel=0;channel<ci;channel++)stage[slot+channel*2u]=row[channel];
            }
        }
    }
#ifdef XQVOICE_TEST_PIPELINE
    extern void xqvoice_test_pipeline_work(unsigned,size_t);
    xqvoice_test_pipeline_work(0,(size_t)pixels*K*2u);
#endif
}
static void quant_mac_tile(const uint8_t *output,unsigned start,unsigned pixels,
    unsigned co,const int32_t *biases,const int32_t *multipliers,
    const unsigned *shifts,int32_t lo,int32_t hi,int32_t *accum,int32_t *quant,
    int keep_trace)
{
    unsigned p,n;
    for(p=0;p<pixels;p++)for(n=0;n<co;n++) {
        int32_t dense=rs32(output+((size_t)p*co+n)*4u);
        size_t at=(size_t)(start+p)*co+n;
        if(keep_trace)accum[at]=dense;
        quant[at]=requant((int64_t)dense+biases[n],multipliers[n],shifts[n],lo,hi);
    }
#ifdef XQVOICE_TEST_PIPELINE
    extern void xqvoice_test_pipeline_work(unsigned,size_t);
    xqvoice_test_pipeline_work(1,(size_t)pixels*co*4u);
#endif
}
static int run_mac_pipeline(const uint8_t *current,unsigned t,unsigned out_t,
    unsigned ci,unsigned co,unsigned k,unsigned stride,unsigned dilation,
    unsigned pad,const uint8_t *weights,const int32_t *biases,
    const int32_t *multipliers,const unsigned *shifts,int32_t lo,int32_t hi,
    int32_t *accum,int32_t *quant,int keep_trace)
{
    unsigned start=0,pixels=out_t<16u?out_t:16u,previous_start=0,previous_pixels=0;
    const uint8_t *previous=NULL;uint8_t *stage=xqvoice_mac_input_buffer(pixels,ci*k);
    uint64_t stamp;
    if(!stage)return 22;
    stamp=xqvp_now();pack_mac_tile(stage,current,t,0,pixels,ci,k,stride,dilation,pad);
    xqvp_add(XQVP_PACK,xqvp_now()-stamp);stamp=xqvp_now();
    if(xqvoice_mac_start(weights,pixels,ci*k,co))return 22;
    xqvp_add(XQVP_MAC_WAIT,xqvp_now()-stamp);
    for(;;) {
        unsigned next=start+pixels,remaining=out_t-next;
        unsigned next_pixels=remaining<16u?remaining:16u;
        if(previous_pixels) {
            stamp=xqvp_now();
            quant_mac_tile(previous,previous_start,previous_pixels,co,biases,
                multipliers,shifts,lo,hi,accum,quant,keep_trace);
            xqvp_add(XQVP_REQUANT,xqvp_now()-stamp);
        }
        if(request_cancel && request_cancel(request_cancel_context)) {
            int rc=xqvoice_mac_finish();return rc?22:26;
        }
        if(next_pixels) {
            stamp=xqvp_now();
            pack_mac_tile(stage,current,t,next,next_pixels,ci,k,stride,dilation,pad);
            xqvp_add(XQVP_PACK,xqvp_now()-stamp);
        }
        stamp=xqvp_now();
        if(xqvoice_mac_finish())return 22;
        xqvp_add(XQVP_MAC_WAIT,xqvp_now()-stamp);
        previous=xqvoice_mac_output_buffer();if(!previous)return 22;
        if(!next_pixels) {
            stamp=xqvp_now();
            quant_mac_tile(previous,start,pixels,co,biases,multipliers,shifts,
                lo,hi,accum,quant,keep_trace);
            xqvp_add(XQVP_REQUANT,xqvp_now()-stamp);break;
        }
        /* START does not write the previous shadow output. FINISH is not
         * called until that output has been consumed in the next iteration. */
        stamp=xqvp_now();
        if(xqvoice_mac_start(weights,next_pixels,ci*k,co))return 22;
        xqvp_add(XQVP_MAC_WAIT,xqvp_now()-stamp);
        previous_start=start;previous_pixels=pixels;start=next;pixels=next_pixels;
    }
    return 0;
}
