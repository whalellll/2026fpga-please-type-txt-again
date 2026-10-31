#ifndef XQIH_CONCAT_VIEW_H
#define XQIH_CONCAT_VIEW_H

typedef struct {
    xi8_tensor joined;
    const xi8_tensor *parts[4];
    unsigned offset[4],shift[4],count;
} xqih_concat_view;
typedef struct {uint64_t nodes,elided_bytes;} xqih_concat_stats;
#ifndef XQIH_CONCAT_ALLOC_NOTE
#define XQIH_CONCAT_ALLOC_NOTE(node) ((void)0)
#endif

/* Only a checked adjacent pair with one consumer and no output alias. Parents
 * remain owned by values[] until the consumer has returned. Scaling is safe
 * in int32; the original S8/S16 storage cast is retained before quantization. */
static int xqih_concat_plan(const xi8_model *m,unsigned i,const xi8_tensor values[200],
                            xqih_concat_view *view)
{
    if(!m || !values || !view || i+1>=m->h[2])return 0;
    const int32_t *n=m->n[i],*next=m->n[i+1];
    if(n[0]!=7 || n[4]<2 || n[4]>4 || n[26]!=1 || (n[27]!=8 && n[27]!=16) ||
       next[0]!=1 || next[4]!=1 || next[5]!=(int32_t)i)return 0;
    for(unsigned k=0;k<3;k++)if(m->h[4+k]==i)return 0;
    xqih_concat_view v={0};unsigned offset=0;
    v.joined=(xi8_tensor){.c=(unsigned)n[1],.h=(unsigned)n[2],.w=(unsigned)n[3],
        .pitch=(unsigned)n[1],.bits=(unsigned)n[27],.exponent=n[19]};
    for(unsigned k=0;k<(unsigned)n[4];k++){
        int p=n[5+k];if(p<0 || (unsigned)p>=i)return 0;
        const xi8_tensor *part=values+p;int shift=part->exponent-v.joined.exponent;
        if(!part->data || !part->c || part->pitch<part->c || part->w!=v.joined.w || part->h!=v.joined.h ||
           (part->bits!=8 && part->bits!=16) || shift<0 || shift>(int)(32-part->bits) ||
           offset>v.joined.c || part->c>v.joined.c-offset)return 0;
        v.parts[k]=part;v.offset[k]=offset;v.shift[k]=(unsigned)shift;offset+=part->c;
    }
    if(offset!=v.joined.c)return 0;
    v.count=(unsigned)n[4];*view=v;return 1;
}

static int xqih_pack_concat(uint8_t *dst,const xqih_concat_view *v,unsigned width,unsigned height,
    int source_x,int source_y,int exponent,xi8_stats *stats,const xqm_transport *io)
{
    const xi8_tensor *src=&v->joined;unsigned cp=align4(src->c);int delta=src->exponent-exponent;
    size_t rowbytes=(size_t)width*cp;
    for(unsigned y=0;y<height;y++){
        if(io->cancelled && io->cancelled(io->context))return 0;
        uint8_t *row=dst+(size_t)y*rowbytes;int iy=source_y+(int)y;
        int begin=source_x<0?-source_x:0,end=(int)src->w-source_x;
        if(end>(int)width)end=(int)width;
        if(iy<0 || iy>=(int)src->h || begin>=end){memset(row,0,rowbytes);stats->input_zero_bytes+=rowbytes;continue;}
        size_t prefix=(size_t)begin*cp,suffix=(size_t)(width-(unsigned)end)*cp;
        if(prefix)memset(row,0,prefix);
        if(suffix)memset(row+(size_t)end*cp,0,suffix);
        stats->input_zero_bytes+=prefix+suffix;
        size_t pixels=(size_t)(end-begin),pixel=(size_t)(unsigned)iy*src->w+(unsigned)(source_x+begin);
        /* Segment-major reads keep each parent contiguous; destination
         * segments do not overlap. Never combine the two numeric boundaries. */
        for(unsigned k=0;k<v->count;k++){
            const xi8_tensor *part=v->parts[k];uint8_t *d=row+prefix+v->offset[k];
            size_t si=pixel*part->pitch;
            if(src->bits==8 && part->bits==8 && !v->shift[k] && !delta){
                const int8_t *s=(const int8_t *)part->data+si;
                for(size_t x=0;x<pixels;x++,s+=part->pitch,d+=cp)memcpy(d,s,part->c);
                stats->copied_input_bytes+=pixels*part->c;
            }else{
                int factor=1<<(int)v->shift[k];
#define XQIH_PACK_PART(TYPE) do {const TYPE *s=(const TYPE *)part->data+si; \
    for(size_t x=0;x<pixels;x++,s+=part->pitch,d+=cp)for(unsigned c=0;c<part->c;c++){ \
        int32_t scaled=s[c]*factor;int32_t stored=src->bits==8?(int8_t)scaled:(int16_t)scaled; \
        d[c]=(uint8_t)quant(stored,delta); \
    }}while(0)
                if(part->bits==8)XQIH_PACK_PART(int8_t);else XQIH_PACK_PART(int16_t);
#undef XQIH_PACK_PART
                stats->converted_input_values+=pixels*part->c;
            }
        }
        if(cp>src->c){
            for(size_t x=0;x<pixels;x++)memset(row+prefix+x*cp+src->c,0,cp-src->c);
            stats->input_zero_bytes+=pixels*(cp-src->c);
        }
    }
    return 1;
}

/* XQIH_CONCAT_CONV_BEGIN */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wmisleading-indentation"
static int xqih_convolution_view(const xi8_model *m,const int32_t *n,const xqm_transport *io,const xi8_tensor *src,xi8_tensor *out,xi8_stats *stats,const xqih_concat_view *view){
 struct pango_vision32_job j={0};unsigned sizes[5],tw=out->w,th=out->h;int rectangles=0;
 if(!io || !xqv_exact_available(io))return 0;
 j.abi_version=1;j.width=src->w;j.height=src->h;j.cin=src->c;j.cout=out->c;
 j.kernel=(unsigned)n[10];j.stride=(unsigned)n[12];j.padding=(unsigned)n[14];j.flags=n[24]?5u:4u;
 j.timeout_cycles=49500000;j.timeout_us=1000000;
 if(!layout(&j,(unsigned)io->bytes,sizes)){
  unsigned maxside=(640-j.kernel)/j.stride+1,lo=0,hi=th<maxside?th:maxside;tw=tw<maxside?tw:maxside;
  rectangles=1;j.padding=0;j.width=(tw-1)*j.stride+j.kernel;
  while(lo<hi){unsigned mid=lo+(hi-lo+1)/2;j.height=(mid-1)*j.stride+j.kernel;if(layout(&j,(unsigned)io->bytes,sizes))lo=mid;else hi=mid-1;}
  if(!lo)return 0;th=lo;j.height=(th-1)*j.stride+j.kernel;if(!layout(&j,(unsigned)io->bytes,sizes))return 0;
 }
 uint64_t stamp=xi8_now();
 memcpy(io->shadow+j.weights,m->blob+n[20],(size_t)n[29]);memcpy(io->shadow+j.params,m->blob+n[21],(size_t)n[30]);
 if(n[24])memcpy(io->shadow+j.lut,m->blob+n[23],(size_t)n[24]);
 xqv_parameters_begin(io,&j);stats->weight_ticks+=xi8_now()-stamp;
 for(unsigned ty=0;ty<out->h;ty+=th)for(unsigned tx=0;tx<out->w;tx+=tw){
  unsigned ny=out->h-ty<th?out->h-ty:th,nx=out->w-tx<tw?out->w-tx:tw;
  if(rectangles){j.width=(nx-1)*j.stride+j.kernel;j.height=(ny-1)*j.stride+j.kernel;}
  stamp=xi8_now();
  int source_x=rectangles?(int)(tx*j.stride)-(int)n[14]:0;
  int source_y=rectangles?(int)(ty*j.stride)-(int)n[14]:0;
  if(!xqih_pack_concat(io->shadow,view,j.width,j.height,source_x,source_y,n[18],stats,io))return 0;
  stats->pack_ticks+=xi8_now()-stamp;stamp=xi8_now();
  if(!xqv_run(io,&j))return 0;
  stats->ioctl_ticks+=xi8_now()-stamp;stats->jobs++;stats->cycles+=j.cycles;stamp=xi8_now();
  const int16_t *values=(const void *)(io->shadow+j.output);
  for(unsigned y=0;y<ny;y++){
   size_t di=((size_t)(ty+y)*out->w+tx)*out->c,si=(size_t)y*nx*out->c,count=(size_t)nx*out->c;
   if(out->bits==16)memcpy((int16_t *)out->data+di,values+si,count*2);
   else stats->output_word_values+=narrow_s16_s8((int8_t *)out->data+di,values+si,count);
   stats->output_bytes+=count*out->bits/8;
  }
  stats->output_ticks+=xi8_now()-stamp;
 }
 return 1;
}
#pragma GCC diagnostic pop
/* XQIH_CONCAT_CONV_END */

static void xqih_concat_shape(xi8_tensor *out,const int32_t *n)
{
    out->c=(unsigned)n[1];out->h=(unsigned)n[2];out->w=(unsigned)n[3];out->pitch=out->c;
    out->bits=(unsigned)n[27];out->exponent=n[19];
}
static void xqih_concat_release(xi8_tensor values[200],unsigned refs[200],const int32_t *n,size_t *live)
{
    for(unsigned j=0;j<(unsigned)n[4];j++){
        int p=n[5+j];if(p>=0 && --refs[p]==0){
            if(values[p].data)*live-=(size_t)values[p].h*values[p].w*values[p].c*values[p].bits/8;
            xi8_tensor_free(&values[p]);
        }
    }
}
static int xqih_run_concat(xi8_model *m,const xqm_transport *io,const xi8_tensor *input,
    xi8_stats *stats,xqih_concat_stats *views)
{
    xi8_tensor values[200]={{0}};unsigned refs[200],i=0;int okay=0;size_t live=0;
#if XQ_HWC_TAIL_COLUMNS
    (void)xqih_run_tail;
#endif
    if(!m || !io || !input || !input->data || input->c!=3 || input->pitch!=4 || input->w!=640 ||
       input->h!=640 || input->bits!=8 || input->exponent!=m->n[0][18] || !stats || !views)return 0;
    memset(stats,0,sizeof(*stats));memset(views,0,sizeof(*views));
    for(i=0;i<3;i++)xi8_tensor_free(&m->outputs[i]);
    for(i=0;i<m->h[2];i++)refs[i]=(unsigned)m->n[i][26];
    for(i=0;i<m->h[2];i++){
        const int32_t *n=m->n[i];xi8_tensor *out=&values[i];uint64_t stamp=xi8_now();
        xqih_concat_view view;
        if(xqih_concat_plan(m,i,values,&view)){
            const int32_t *next=m->n[i+1];xi8_tensor *consumer=&values[i+1];
            xqih_concat_shape(consumer,next);size_t bytes=elements(next)*consumer->bits/8;
            XQIH_CONCAT_ALLOC_NOTE(i);
            consumer->data=malloc(bytes);
            if(consumer->data){live+=bytes;stats->allocated_tensor_bytes+=bytes;if(live>stats->peak_tensor_bytes)stats->peak_tensor_bytes=live;}
            stats->allocate_ticks+=xi8_now()-stamp;if(!consumer->data)goto done;
            if(!xqih_convolution_view(m,next,io,&view.joined,consumer,stats,&view))goto done;
            views->nodes++;views->elided_bytes+=elements(n)*view.joined.bits/8;
            xqih_concat_release(values,refs,n,&live);refs[i]=0;
            i++;continue;
        }
        xqih_concat_shape(out,n);size_t bytes=elements(n)*out->bits/8;int reuse=-1;
        if(n[0]==8)for(unsigned j=0;j<(unsigned)n[4];j++){
            int p=n[5+j];if(p>=0 && refs[p]==1 && values[p].bits==out->bits && values[p].pitch==out->c){reuse=p;break;}
        }
        if(reuse>=0){out->data=values[reuse].data;stats->reused_tensor_bytes+=bytes;}
        else{out->data=malloc(bytes);if(out->data){live+=bytes;stats->allocated_tensor_bytes+=bytes;if(live>stats->peak_tensor_bytes)stats->peak_tensor_bytes=live;}}
        stats->allocate_ticks+=xi8_now()-stamp;if(!out->data)goto done;
        if(n[0]==1){
#if XQ_HWC_TAIL_COLUMNS
            if(!xqih_convolution_tail(m,n,io,n[5]<0?input:&values[n[5]],out,stats))goto done;
#else
            if(!convolution(m,n,io,n[5]<0?input:&values[n[5]],out,stats))goto done;
#endif
        }else{
            stamp=xi8_now();int result=nonconv(n,values,out);if(reuse>=0)values[reuse].data=NULL;
            stats->ops_ticks+=xi8_now()-stamp;if(!result)goto done;
        }
        xqih_concat_release(values,refs,n,&live);
    }
    for(i=0;i<3;i++){unsigned p=m->h[4+i];m->outputs[i]=values[p];memset(&values[p],0,sizeof(values[p]));}
    okay=1;
done:
    if(!okay)fprintf(stderr,"INTEGER_GRAPH_FAIL node=%u no_fallback=1\n",i);
    for(unsigned j=0;j<m->h[2];j++)xi8_tensor_free(&values[j]);
    return okay;
}
#endif
