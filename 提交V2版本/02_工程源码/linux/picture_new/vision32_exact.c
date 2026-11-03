/* Private exact epilogue for complete-K convolutions. Included only by the
 * locality adapter; immutable upstream/raw2 and observer traces stay intact.
 * Return 0=ineligible,1=success,-1=fatal eligible execution (never retry). */
static int exact_layout(struct pango_vision32_job *j,unsigned bytes,unsigned sizes[5])
{
    unsigned k=j->cin*j->kernel*j->kernel,groups=(j->cout+7)/8;
    j->weights=align4(j->height*j->width*align4(j->cin));
    j->params=j->weights+groups*k*8;
    j->lut=j->params+groups*8*12;
    j->output=align4(j->lut+((j->flags&1u)?65536u:0u));
    return pango_vision32_sizes(j,bytes,sizes);
}
static int xqi_exact_layer(const xqm_transport *io,const xqi_shape *s,const int8_t *input,
    const int8_t *weight,const int32_t *bias,const int64_t *shifts,
    const int8_t *lut,size_t lut_bytes,int16_t *out,xqm_stats *stats)
{
    struct pango_vision32_job j={0};unsigned sizes[5],oh,ow,ci4,groups,tw,th;
    int rectangles=0;
    if(!io || !s || s->cpu_reference || s->linear || !xqv_exact_available(io) ||
       !s->batch || s->batch>300 || !s->width || !s->height || !s->cin || !s->cout ||
       s->cin>512 || s->cout>256 || s->width>640 || s->height>640 || s->kh!=s->kw ||
       (s->kh!=1 && s->kh!=3 && s->kh!=6) || s->stride_h!=s->stride_w ||
       (s->stride_h!=1 && s->stride_h!=2) || s->pad_h!=s->pad_w || s->pad_h>=s->kh ||
       s->dilation_h!=1 || s->dilation_w!=1 || s->width+2*s->pad_w<s->kw ||
       s->height+2*s->pad_h<s->kh || s->cin*s->kh*s->kw>1152)return 0;
    if(!io->shadow || io->bytes!=0x100000 || !input || !weight || !bias || !shifts || !out ||
       (lut_bytes && (lut_bytes!=65536 || !lut)))return -1;
    for(unsigned c=0;c<s->cout;c++)if(shifts[c]<0 || shifts[c]>62)return -1;
    oh=(s->height+2*s->pad_h-s->kh)/s->stride_h+1;
    ow=(s->width+2*s->pad_w-s->kw)/s->stride_w+1;
    ci4=align4(s->cin);groups=(s->cout+7)/8;tw=ow;th=oh;
    j.abi_version=PANGO_VISION32_ABI;j.width=s->width;j.height=s->height;
    j.cin=s->cin;j.cout=s->cout;j.kernel=s->kh;j.stride=s->stride_h;j.padding=s->pad_h;
    j.flags=lut_bytes?PANGO_VISION32_EXACT_LUT:PANGO_VISION32_EXACT_S16;
    j.timeout_cycles=49500000;j.timeout_us=1000000;
    if(!exact_layout(&j,(unsigned)io->bytes,sizes)){
        unsigned max_side=(640-s->kh)/s->stride_h+1,low=0,high=oh<max_side?oh:max_side;
        rectangles=1;tw=ow<max_side?ow:max_side;j.padding=0;
        j.width=(tw-1)*s->stride_w+s->kw;
        while(low<high){
            unsigned mid=low+(high-low+1)/2;j.height=(mid-1)*s->stride_h+s->kh;
            if(exact_layout(&j,(unsigned)io->bytes,sizes))low=mid;else high=mid-1;
        }
        if(!low)return 0;
        th=low;j.height=(th-1)*s->stride_h+s->kh;
        if(!exact_layout(&j,(unsigned)io->bytes,sizes))return -1;
    }
    if(stats)memset(stats,0,sizeof(*stats));
    xqg_mark stage=xqg_begin();memset(io->shadow+j.weights,0,sizes[1]);
    xqg_end(XQG_STAGING_ZERO,stage,sizes[1]);stage=xqg_begin();
    for(unsigned co=0;co<s->cout;co++)for(unsigned ky=0;ky<s->kh;ky++)
        for(unsigned kx=0;kx<s->kw;kx++)for(unsigned ci=0;ci<s->cin;ci++)
            io->shadow[j.weights+(((co/8*s->kh+ky)*s->kw+kx)*s->cin+ci)*8+co%8]=
                (uint8_t)weight[((size_t)co*s->cin+ci)*s->kh*s->kw+ky*s->kw+kx];
    for(unsigned co=0;co<groups*8;co++){
        int32_t param[3]={co<s->cout?bias[co]:0,1,co<s->cout?(int32_t)shifts[co]:0};
        memcpy(io->shadow+j.params+co*12,param,12);
    }
    if(lut_bytes)memcpy(io->shadow+j.lut,lut,65536);
    xqg_end(XQG_WEIGHT_LAYOUT,stage,(uint64_t)sizes[1]+sizes[3]+sizes[4]);
    /* Offsets remain at the maximum tile footprint. Smaller edge rectangles
     * change only input/output lengths, so the parameter lease remains valid. */
    xqv_parameters_begin(io,&j);
    for(unsigned b=0;b<s->batch;b++)for(unsigned ty=0;ty<oh;ty+=th)for(unsigned tx=0;tx<ow;tx+=tw){
        if(io->cancelled && io->cancelled(io->context))return -1;
        unsigned ny=oh-ty<th?oh-ty:th,nx=ow-tx<tw?ow-tx:tw;
        if(rectangles){j.width=(nx-1)*s->stride_w+s->kw;j.height=(ny-1)*s->stride_h+s->kh;}
        stage=xqg_begin();memset(io->shadow+j.input,0,(size_t)j.width*j.height*ci4);
        xqg_end(XQG_STAGING_ZERO,stage,(uint64_t)j.width*j.height*ci4);stage=xqg_begin();
        for(unsigned y=0;y<j.height;y++)for(unsigned xb=0;xb<j.width;xb+=8)for(unsigned cb=0;cb<s->cin;cb+=8)
            for(unsigned c=cb;c<s->cin && c<cb+8;c++)for(unsigned x=xb;x<j.width && x<xb+8;x++){
                int iy=rectangles?(int)(ty*s->stride_h+y)-(int)s->pad_h:(int)y;
                int ix=rectangles?(int)(tx*s->stride_w+x)-(int)s->pad_w:(int)x;
                if(iy<0 || ix<0 || iy>=(int)s->height || ix>=(int)s->width)continue;
                io->shadow[(y*j.width+x)*ci4+c]=(uint8_t)input[((size_t)b*s->cin+c)*s->height*s->width+(unsigned)iy*s->width+(unsigned)ix];
            }
        xqg_end(XQG_INPUT_LAYOUT,stage,(uint64_t)j.height*j.width*s->cin);
        if(!xqv_run(io,&j))return -1;
        if(stats){stats->jobs++;stats->cycles+=j.cycles;}
        stage=xqg_begin();
        for(unsigned y=0;y<ny;y++)for(unsigned xb=0;xb<nx;xb+=8)for(unsigned cb=0;cb<s->cout;cb+=8)
            for(unsigned c=cb;c<s->cout && c<cb+8;c++)for(unsigned x=xb;x<nx && x<xb+8;x++){
                int16_t value;memcpy(&value,io->shadow+j.output+2*((y*nx+x)*s->cout+c),2);
                out[((size_t)b*s->cout+c)*oh*ow+(ty+y)*ow+tx+x]=value;
            }
        xqg_end(XQG_OUTPUT_LAYOUT_REQUANT,stage,(uint64_t)s->cout*ny*nx);
    }
    return 1;
}
