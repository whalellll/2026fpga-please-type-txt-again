#ifndef XQIH_TAIL_COLUMNS_H
#define XQIH_TAIL_COLUMNS_H

/* Frozen detector input layer only. Parameter/output offsets and maximum
 * footprints come from the original main rectangle; no lease is relocated.
 * Numeric pack, exact kernel and S16 narrowing remain the provider's helpers. */
static int xqih_tail_fits(const struct pango_vision32_job *base,unsigned nx,unsigned ny,
                          unsigned bytes,const unsigned capacity[5])
{
    struct pango_vision32_job probe=*base;unsigned sizes[5];
    if(!nx || !ny)return 0;
    probe.width=(nx-1)*probe.stride+probe.kernel;
    probe.height=(ny-1)*probe.stride+probe.kernel;
    if(!pango_vision32_sizes(&probe,bytes,sizes) || sizes[0]>capacity[0] || sizes[2]>capacity[2])return 0;
    unsigned k=probe.cin*probe.kernel*probe.kernel;
    return (uint64_t)nx*ny*probe.cout*(k+512u)<=UINT64_C(67108864);
}
static int xqih_tail_plan(const int32_t *n,const xqm_transport *io,
    const xi8_tensor *src,const xi8_tensor *out,struct pango_vision32_job *j,
    unsigned sizes[5],unsigned *tw,unsigned *th,unsigned *tail_height)
{
    /* Other layers retain the original function, including traversal order. */
    if(n[5]>=0)return 0;
    memset(j,0,sizeof(*j));*tw=out->w;*th=out->h;
    j->abi_version=1;j->width=src->w;j->height=src->h;j->cin=src->c;j->cout=out->c;
    j->kernel=(unsigned)n[10];j->stride=(unsigned)n[12];j->padding=(unsigned)n[14];j->flags=n[24]?5u:4u;
    j->timeout_cycles=49500000;j->timeout_us=1000000;
    if(layout(j,(unsigned)io->bytes,sizes))return 0;
    unsigned maxside=(640-j->kernel)/j->stride+1,lo=0,hi=*th<maxside?*th:maxside;
    *tw=*tw<maxside?*tw:maxside;j->padding=0;j->width=(*tw-1)*j->stride+j->kernel;
    while(lo<hi){
        unsigned mid=lo+(hi-lo+1)/2;j->height=(mid-1)*j->stride+j->kernel;
        if(layout(j,(unsigned)io->bytes,sizes))lo=mid;else hi=mid-1;
    }
    if(!lo)return -1;
    *th=lo;j->height=(*th-1)*j->stride+j->kernel;
    if(!layout(j,(unsigned)io->bytes,sizes))return -1;
    unsigned nx=out->w%*tw;
    if(!nx)return 0;
    lo=0;hi=out->h<maxside?out->h:maxside;
    while(lo<hi){
        unsigned mid=lo+(hi-lo+1)/2;
        if(xqih_tail_fits(j,nx,mid,(unsigned)io->bytes,sizes))lo=mid;else hi=mid-1;
    }
    if(lo<=*th)return 0;
    *tail_height=lo;return 1;
}
static int xqih_tail_submit(const int32_t *n,const xqm_transport *io,const xi8_tensor *src,
    xi8_tensor *out,xi8_stats *stats,struct pango_vision32_job *j,
    unsigned tx,unsigned ty,unsigned nx,unsigned ny)
{
    j->width=(nx-1)*j->stride+j->kernel;j->height=(ny-1)*j->stride+j->kernel;
    uint64_t stamp=xi8_now();
    int source_x=(int)(tx*j->stride)-(int)n[14],source_y=(int)(ty*j->stride)-(int)n[14];
    pack_input(io->shadow,src,j->width,j->height,source_x,source_y,n[18],stats);
    stats->pack_ticks+=xi8_now()-stamp;stamp=xi8_now();
    if(!xqv_run(io,j))return 0;
    stats->ioctl_ticks+=xi8_now()-stamp;stats->jobs++;stats->cycles+=j->cycles;stamp=xi8_now();
    const int16_t *values=(const void *)(io->shadow+j->output);
    for(unsigned y=0;y<ny;y++){
        size_t di=((size_t)(ty+y)*out->w+tx)*out->c,si=(size_t)y*nx*out->c,count=(size_t)nx*out->c;
        if(out->bits==16)memcpy((int16_t *)out->data+di,values+si,count*2);
        else stats->output_word_values+=narrow_s16_s8((int8_t *)out->data+di,values+si,count);
        stats->output_bytes+=count*out->bits/8;
    }
    stats->output_ticks+=xi8_now()-stamp;return 1;
}
static int xqih_convolution_tail(const xi8_model *m,const int32_t *n,const xqm_transport *io,
    const xi8_tensor *src,xi8_tensor *out,xi8_stats *stats)
{
    if(!io || !xqv_exact_available(io))return 0;
    struct pango_vision32_job j;unsigned sizes[5],tw=0,th=0,tail_height=0;
    int selected=xqih_tail_plan(n,io,src,out,&j,sizes,&tw,&th,&tail_height);
    if(selected<0)return 0;
    if(!selected)return convolution(m,n,io,src,out,stats);
    uint64_t stamp=xi8_now();
    memcpy(io->shadow+j.weights,m->blob+n[20],(size_t)n[29]);
    memcpy(io->shadow+j.params,m->blob+n[21],(size_t)n[30]);
    if(n[24])memcpy(io->shadow+j.lut,m->blob+n[23],(size_t)n[24]);
    xqv_parameters_begin(io,&j);stats->weight_ticks+=xi8_now()-stamp;
    for(unsigned tx=0;tx<out->w;tx+=tw){
        unsigned nx=out->w-tx<tw?out->w-tx:tw,height=nx<tw?tail_height:th;
        for(unsigned ty=0;ty<out->h;ty+=height){
            unsigned ny=out->h-ty<height?out->h-ty:height;
            if(!xqih_tail_submit(n,io,src,out,stats,&j,tx,ty,nx,ny))return 0;
        }
    }
    return 1;
}

/* The provider coordinator below is copied unchanged except its name and
 * convolution call. Restrict its existing compact-style exception here. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wmisleading-indentation"
/* XQIH_TAIL_COORDINATOR_BEGIN */
static int xqih_run_tail(xi8_model *m,const xqm_transport *io,const xi8_tensor *input,xi8_stats *stats){
 xi8_tensor values[200]={{0}};unsigned refs[200],i=0;int okay=0;size_t live=0;
 if(!m || !io || !input || !input->data || input->c!=3 || input->pitch!=4 || input->w!=640 || input->h!=640 || input->bits!=8 || input->exponent!=m->n[0][18] || !stats)return 0;
 memset(stats,0,sizeof(*stats));for(i=0;i<3;i++)xi8_tensor_free(&m->outputs[i]);
 for(i=0;i<m->h[2];i++)refs[i]=(unsigned)m->n[i][26];
 for(i=0;i<m->h[2];i++){
  const int32_t *n=m->n[i];xi8_tensor *out=&values[i];uint64_t stamp=xi8_now();
  out->c=(unsigned)n[1];out->h=(unsigned)n[2];out->w=(unsigned)n[3];out->pitch=out->c;out->bits=(unsigned)n[27];out->exponent=n[19];
  size_t bytes=elements(n)*out->bits/8;int reuse=-1;
  if(n[0]==8)for(unsigned j=0;j<(unsigned)n[4];j++){
   int p=n[5+j];if(p>=0 && refs[p]==1 && values[p].bits==out->bits && values[p].pitch==out->c){reuse=p;break;}
  }
  if(reuse>=0){out->data=values[reuse].data;stats->reused_tensor_bytes+=bytes;}
  else{out->data=malloc(bytes);if(out->data){live+=bytes;stats->allocated_tensor_bytes+=bytes;if(live>stats->peak_tensor_bytes)stats->peak_tensor_bytes=live;}}
  stats->allocate_ticks+=xi8_now()-stamp;if(!out->data)goto done;
  if(n[0]==1){if(!xqih_convolution_tail(m,n,io,n[5]<0?input:&values[n[5]],out,stats))goto done;}
  else{stamp=xi8_now();int result=nonconv(n,values,out);if(reuse>=0)values[reuse].data=NULL;stats->ops_ticks+=xi8_now()-stamp;if(!result)goto done;}
  for(unsigned j=0;j<(unsigned)n[4];j++){
   int p=n[5+j];if(p>=0 && --refs[p]==0){if(values[p].data)live-=(size_t)values[p].h*values[p].w*values[p].c*values[p].bits/8;xi8_tensor_free(&values[p]);}
  }
 }
 for(i=0;i<3;i++){unsigned p=m->h[4+i];m->outputs[i]=values[p];memset(&values[p],0,sizeof(values[p]));}
 okay=1;
done:
 if(!okay)fprintf(stderr,"INTEGER_GRAPH_FAIL node=%u no_fallback=1\n",i);
 for(unsigned j=0;j<m->h[2];j++)xi8_tensor_free(&values[j]);return okay;
}
/* XQIH_TAIL_COORDINATOR_END */
#pragma GCC diagnostic pop
#endif
