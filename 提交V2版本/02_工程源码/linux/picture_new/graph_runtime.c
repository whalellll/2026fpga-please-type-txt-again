/* Private PN05 graph candidate. Baseline: immutable adapter graph SHA256
 * 60c53e032e0f085476881f067ace35ab40acae5ca564b043b7edc983fe25ceb9.
 * Frozen weights/graph bytes remain unchanged. Classifier S16 GAP is an
 * explicitly authorized runtime policy; detector/board nonconv stay FP32. */
#include "xq_native_graph.h"
#include "crc32_fast.h"
#include "graph_profile.h"
#include "graph_tensor.h"
#ifndef XQ_INTEGER_CARRIER
#define XQ_INTEGER_CARRIER 1
#endif
#ifndef XQ_CLASSIFIER_S16
#define XQ_CLASSIFIER_S16 0
#endif
#ifndef XQ_HWC_DETECTOR
#define XQ_HWC_DETECTOR 0
#endif
#ifndef XQ_FAST_FP32_BILINEAR
#define XQ_FAST_FP32_BILINEAR 0
#endif
#if XQ_FAST_FP32_BILINEAR
#include "graph_bilinear_s16.c"
#endif
#if XQ_HWC_DETECTOR
#include "hwc_fast/adapter.h"
#endif
#if XQ_CLASSIFIER_S16
#include "graph_ops.h"
#if !XQ_INTEGER_CARRIER
#error "Classifier S16 requires the integer carrier"
#endif
#endif
#include "xq_resident_matrix.h"
#include "xq_conv_dispatch.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct xqn_model {
    uint32_t header[10];
    unsigned char *body,*blob;
    int32_t (*nodes)[32];
    float *outputs[3];
    unsigned batch;
    unsigned input_side;
    xqn_observer observer;
    void *observer_context;
    const xqm_transport *resident_io;
#if XQ_HWC_DETECTOR
    xqih_detector *hwc_detector;
#endif
};
void xqn_observe(xqn_model *m,xqn_observer fn,void *ctx){if(m){m->observer=fn;m->observer_context=ctx;}}
static size_t elements(const int32_t *n){return (size_t)n[1]*n[2]*n[3];}
static int range(size_t offset,size_t bytes,size_t end){return offset<=end && bytes<=end-offset;}
void xqn_free(xqn_model *m)
{
    unsigned i;if(!m)return;
    for(i=0;i<3;i++)free(m->outputs[i]);
#if XQ_HWC_DETECTOR
    xqih_close(m->hwc_detector);
#endif
    free(m->body);free(m);
}
xqn_model *xqn_load(const char *path)
{
    FILE *f=fopen(path,"rb");char magic[8];unsigned i,j;
    xqn_model *m=calloc(1,sizeof(*m));
    if(!f || !m)goto bad;
    if(fread(magic,1,8,f)!=8 || memcmp(magic,"XQGRPH1\0",8) || fread(m->header,4,10,f)!=10 ||
       (m->header[0]!=1 && m->header[0]!=2) || m->header[1]>2 || !m->header[2] || m->header[2]>200 ||
       !m->header[3] || m->header[3]>3 || m->header[7]>16u*1024u*1024u ||
       m->header[8]!=(size_t)m->header[2]*128+m->header[7]+(m->header[0]==2?16:0))goto bad;
    for(i=0;i<m->header[3];i++)if(m->header[4+i]>=m->header[2])goto bad;
    m->body=malloc(m->header[8]);if(!m->body)goto bad;
    if(fread(m->body,1,m->header[8],f)!=m->header[8] || fgetc(f)!=EOF || ferror(f) ||
       (crc32_fast(0xffffffffu,m->body,m->header[8])^0xffffffffu)!=m->header[9])goto bad;
    m->input_side=m->header[1]==0?192:m->header[1]==1?640:32;
    unsigned descriptor=m->header[0]==2?16:0;
    if(descriptor) {
        uint32_t shape[4];memcpy(shape,m->body,16);
        if(shape[0]!=3 || shape[1]!=shape[2] || shape[3]!=0 ||
           (m->header[1]==0 && shape[1]!=192) || (m->header[1]==2 && shape[1]!=32) ||
           (m->header[1]==1 && shape[1]!=416 && shape[1]!=640))goto bad;
        m->input_side=shape[1];
    }
    m->nodes=(int32_t (*)[32])(m->body+descriptor);m->blob=m->body+descriptor+m->header[2]*128;
    for(i=0;i<m->header[2];i++) {
        const int32_t *n=m->nodes[i];
        if(n[0]<1 || n[0]>11 || n[0]==2 || n[1]<1 || n[1]>65535 || n[2]<1 || n[2]>640 ||
           n[3]<1 || n[3]>640 || elements(n)>16u*1024u*1024u || n[4]<1 || n[4]>4 || n[26]<1)goto bad;
        for(j=0;j<(unsigned)n[4];j++)if(n[5+j]< -1 || n[5+j]>=(int32_t)i)goto bad;
        if(n[0]==1 && (n[9]<0 || n[9]>=80 || n[18]< -120 || n[18]>120 || n[19]< -120 || n[19]>120 ||
           n[10]<1 || n[10]>6 || n[11]<1 || n[11]>6 || n[12]<1 || n[12]>8 || n[13]<1 || n[13]>8 ||
           n[14]<0 || n[14]>8 || n[15]<0 || n[15]>8 || n[16]<1 || n[16]>8 || n[17]<1 || n[17]>8 ||
           n[20]<0 || n[21]<0 || n[22]<0 || n[23]<0 || n[21]%4 || n[22]%8 ||
           (n[24]!=0 && n[24]!=65536) || (n[25]!=0 && n[25]!=1)))goto bad;
    }
    /* The carrier owns two possible allocations per node. Authenticate
     * liveness before execution so malformed refcounts cannot free a parent
     * early or retain an output under two owning pointers. */
    unsigned uses[200]={0};
    for(i=0;i<m->header[2];i++)for(j=0;j<(unsigned)m->nodes[i][4];j++){
        int parent=m->nodes[i][5+j];if(parent>=0)uses[parent]++;
    }
    for(i=0;i<m->header[3];i++){
        for(j=0;j<i;j++)if(m->header[4+i]==m->header[4+j])goto bad;
        uses[m->header[4+i]]++;
    }
    for(i=0;i<m->header[2];i++)if(uses[i]!=(unsigned)m->nodes[i][26])goto bad;
#if XQ_HWC_DETECTOR
    if(m->header[1]==1 && !(m->hwc_detector=xqih_open(path,m->header)))goto bad;
#endif
    fclose(f);return m;
bad:
    if(f)fclose(f);
    xqn_free(m);return NULL;
}
static float sigmoid(float x){return 1.f/(1.f+expf(-x));}
unsigned xqn_input_side(const xqn_model *m){return m?m->input_side:0;}
int xqn_pin_resident(xqn_model *m,const xqm_transport *io)
{
    xqn_resident_layer layers[80];unsigned count=0;
    if(!m || !io)return 0;
    for(unsigned i=0;i<m->header[2];i++) {
        const int32_t *n=m->nodes[i];if(n[0]!=1)continue;
        unsigned cin=n[5]<0?3u:(unsigned)m->nodes[n[5]][1];
        size_t k=(size_t)cin*n[10]*n[11];
        if(count>=80 || k>65535 || !range((size_t)n[20],k*n[1],m->header[7]))return 0;
        layers[count++]=(xqn_resident_layer){(const int8_t *)m->blob+n[20],(unsigned)k,(unsigned)n[1]};
    }
    if(!xqn_resident_prepare(io,layers,count))return 0;
    m->resident_io=io;return 1;
}
int xqn_run(xqn_model *m,const xqm_transport *io,unsigned batch,const float *input,int cpu,xqm_stats *stats)
{
    xqg_tensor values[200]={0};unsigned refs[200],i,j,b,c,y,x;
    int32_t inshape[4]={0,3,0,0};int okay=0;
    if(stats)memset(stats,0,sizeof(*stats));
    if(!m || !input || !batch || batch>256 || (m->header[1]!=2 && batch!=1) || (!io && !cpu) || (io && cpu))return 0;
#if XQ_HWC_DETECTOR
    if(m->hwc_detector){
        for(i=0;i<3;i++){free(m->outputs[i]);m->outputs[i]=NULL;}
        m->batch=0;
        /* A raw2 observer cannot describe the different HWC numeric graph.
         * Reject that request explicitly instead of fabricating 60 traces. */
        if(cpu || m->observer || !io || batch!=1)return 0;
        int result=xqih_detect(m->hwc_detector,io,input,m->outputs,stats);
        if(result)m->batch=1;
        return result;
    }
#endif
#if defined(XQ_GRAPH_PROFILE) && defined(XQ_NATIVE_COACH)
    xqg_profile_reset();xqg_mark graph_start=xqg_begin();
#endif
    if(io && m->resident_io)io=m->resident_io;
    inshape[2]=inshape[3]=(int32_t)m->input_side;
    xqg_tensor initial={.f32=(float *)input,.count=(size_t)batch*3*m->input_side*m->input_side};
    for(i=0;i<3;i++){free(m->outputs[i]);m->outputs[i]=NULL;}
    for(i=0;i<m->header[2];i++)refs[i]=(unsigned)m->nodes[i][26];
    for(i=0;i<m->header[2];i++) {
        const int32_t *n=m->nodes[i],*s=n[5]<0?inshape:m->nodes[n[5]];
        xqg_tensor *source=n[5]<0?&initial:&values[n[5]];
        const float *a=NULL;
        size_t size=elements(n),srcsize=elements(s),total=(size_t)batch*size;
        unsigned ic=(unsigned)s[1],ih=(unsigned)s[2],iw=(unsigned)s[3],oc=(unsigned)n[1],oh=(unsigned)n[2],ow=(unsigned)n[3];
        float *out=NULL;
        int integer_gap=XQ_CLASSIFIER_S16 && m->header[1]==2 && n[0]==9;
        int fast_bilinear=0;
#if XQ_FAST_FP32_BILINEAR
        fast_bilinear=n[0]==6 && n[4]==1 && ic==oc && oh==ih*2 && ow==iw*2 &&
            xqg_bilinear_s16_eligible(source,batch,ic,ih,iw);
#endif
        if(total>16u*1024u*1024u || source->count!=(size_t)batch*srcsize || (!source->q16 && !source->f32))goto done;
        values[i].count=total;
        if(!XQ_INTEGER_CARRIER || (n[0]!=1 && !integer_gap)){
            values[i].f32=out=malloc(total*sizeof(float));if(!out)goto done;
        }
        if(n[0]!=1 && !integer_gap && !fast_bilinear){
            /* Materialize every parent before timing the unchanged FP32 op.
             * A mixed fanout retains q16 for conv consumers and caches f32. */
            for(j=0;j<(unsigned)n[4];j++){
                int parent=n[5+j];
                if(parent>=0 && !xqg_tensor_float(&values[parent]))goto done;
            }
            a=source->f32;if(!a)goto done;
        }
        xqg_mark node_start=xqg_begin();
        if(integer_gap){
#if XQ_CLASSIFIER_S16
            xqg_s16_view src={source->q16,source->count,batch,ic,ih,iw,source->exponent},dst;
            values[i].q16=malloc(total*2);if(!values[i].q16)goto done;
            if(n[4]!=1 || !xqg_op_run(9,&src,1,values[i].q16,total,NULL,&dst) ||
               dst.count!=total || dst.channels!=oc || dst.height!=oh || dst.width!=ow)goto done;
            values[i].exponent=dst.exponent;
            xqg_end(XQG_INTEGER_GAP,node_start,total);
#endif
        } else if(n[0]==1) {
            int8_t *q=NULL;int16_t *oq=NULL,*pre=NULL;int32_t *acc=NULL;
            size_t k=(size_t)ic*n[10]*n[11];xqm_stats st;
            xqi_shape shape={batch,ic,ih,iw,oc,(unsigned)n[10],(unsigned)n[11],(unsigned)n[12],(unsigned)n[13],
                (unsigned)n[14],(unsigned)n[15],(unsigned)n[16],(unsigned)n[17],(unsigned)n[25],(unsigned)cpu};
            if(!range((size_t)n[20],oc*k,m->header[7]) || !range((size_t)n[21],oc*4,m->header[7]) ||
               !range((size_t)n[22],oc*8,m->header[7]) || !range((size_t)n[23],(size_t)n[24],m->header[7]))goto done;
            q=malloc((size_t)batch*srcsize);oq=malloc(total*2);
            if(!q || !oq){free(q);free(oq);goto done;}
            if(m->observer){acc=malloc(total*4);pre=malloc(total*2);if(!acc || !pre){free(q);free(oq);free(acc);free(pre);goto done;}}
            if(!xqg_tensor_quantize(source,n[18],q)){free(q);free(oq);free(acc);free(pre);goto done;}
            int conv=xqn_try_conv(io,&shape,q,(const int8_t *)m->blob+n[20],(const int32_t *)(m->blob+n[21]),
                          (const int64_t *)(m->blob+n[22]),(const int8_t *)m->blob+n[23],(size_t)n[24],acc,pre,oq,&st);
            if(conv<0 || (!conv && !xqi_layer(io,&shape,q,(const int8_t *)m->blob+n[20],(const int32_t *)(m->blob+n[21]),
                          (const int64_t *)(m->blob+n[22]),(const int8_t *)m->blob+n[23],(size_t)n[24],acc,pre,oq,&st))) {
                free(q);free(oq);free(acc);free(pre);goto done;
            }
            if(m->observer)m->observer(m->observer_context,(unsigned)n[9],q,(size_t)batch*srcsize,oq,total,acc,pre);
            values[i].q16=oq;values[i].exponent=n[19];
            if(!XQ_INTEGER_CARRIER){
                xqg_mark start=xqg_begin();int converted=xqi_dequantize(oq,total,n[19],out);
                xqg_end(XQG_DEQUANTIZE,start,total);
                free(values[i].q16);values[i].q16=NULL;
                if(!converted){free(q);free(acc);free(pre);goto done;}
            }
            free(q);free(acc);free(pre);
            if(stats){stats->jobs+=st.jobs;stats->cycles+=st.cycles;}
        } else if(n[0]==3 || n[0]==11) {
            if(size!=srcsize)goto done;
            for(size_t z=0;z<total;z++)out[z]=n[0]==3?sigmoid(a[z]):a[z]>0?a[z]:0;
        } else if(n[0]==4) {
            if(size!=srcsize || n[10]!=5 || n[14]!=2)goto done;
            for(b=0;b<batch;b++)for(c=0;c<oc;c++)for(y=0;y<oh;y++)for(x=0;x<ow;x++) {
                float v=-INFINITY;
                for(int yy=(int)y-2;yy<=(int)y+2;yy++)for(int xx=(int)x-2;xx<=(int)x+2;xx++)
                    if(yy>=0 && xx>=0 && yy<(int)ih && xx<(int)iw) {
                        float f=a[((size_t)b*ic+c)*ih*iw+(unsigned)yy*iw+(unsigned)xx];if(f>v)v=f;
                    }
                out[((size_t)b*oc+c)*oh*ow+y*ow+x]=v;
            }
        }
#if XQ_FAST_FP32_BILINEAR
        else if(fast_bilinear){
            if(!xqg_bilinear_s16(source,batch,ic,ih,iw,out))goto done;
        }
#endif
        else if(n[0]==5 || n[0]==6) {
            if(ic!=oc || oh!=ih*2 || ow!=iw*2)goto done;
            for(b=0;b<batch;b++)for(c=0;c<oc;c++)for(y=0;y<oh;y++)for(x=0;x<ow;x++) {
                float v;
                const float *base=a+((size_t)b*ic+c)*ih*iw;
                if(n[0]==5)v=base[(y/2)*iw+x/2];
                else {
                    float sy=fmaxf(0,(y+.5f)*.5f-.5f),sx=fmaxf(0,(x+.5f)*.5f-.5f);
                    unsigned y0=(unsigned)sy,x0=(unsigned)sx,y1=y0+1<ih?y0+1:y0,x1=x0+1<iw?x0+1:x0;
                    float fy=sy-y0,fx=sx-x0;
                    v=(1.f-fy)*((1.f-fx)*base[y0*iw+x0]+fx*base[y0*iw+x1])+fy*((1.f-fx)*base[y1*iw+x0]+fx*base[y1*iw+x1]);
                }
                out[((size_t)b*oc+c)*oh*ow+y*ow+x]=v;
            }
        } else if(n[0]==7) {
            unsigned at=0;
            for(j=0;j<(unsigned)n[4];j++) {
                int parent=n[5+j];const int32_t *ps=parent<0?inshape:m->nodes[parent];
                const float *pv=parent<0?input:values[parent].f32;size_t psn=elements(ps);
                if(ps[2]!=n[2] || ps[3]!=n[3] || at+(unsigned)ps[1]>oc || !pv)goto done;
                for(b=0;b<batch;b++)memcpy(out+(size_t)b*size+(size_t)at*oh*ow,pv+(size_t)b*psn,psn*4);
                at+=(unsigned)ps[1];
            }
            if(at!=oc)goto done;
        } else if(n[0]==8) {
            const float *other=n[6]<0?input:values[n[6]].f32;
            if(n[4]!=2 || size!=srcsize || !other || (n[6]>=0 && size!=elements(m->nodes[n[6]])))goto done;
            for(size_t z=0;z<total;z++)out[z]=a[z]+other[z];
        } else if(n[0]==9) {
            if(ic!=oc || oh!=1 || ow!=1)goto done;
            for(b=0;b<batch;b++)for(c=0;c<oc;c++) {
                float sum=0;const float *p=a+((size_t)b*ic+c)*ih*iw;
                for(j=0;j<ih*iw;j++)sum+=p[j];
                out[(size_t)b*oc+c]=sum/(ih*iw);
            }
        } else if(n[0]==10) {if(size!=srcsize)goto done;memcpy(out,a,total*4);}
        else goto done;
        if(n[0]!=1 && !integer_gap)xqg_end((enum xqg_phase)(XQG_FP32_3+n[0]-3),node_start,total);
        for(j=0;j<(unsigned)n[4];j++) {
            int parent=n[5+j];if(parent>=0 && --refs[parent]==0){xqg_tensor_clear(&values[parent]);}
        }
    }
    /* Publish only after every output materialized successfully. No partial
     * output survives allocation failure or a failed inference. */
    for(i=0;i<m->header[3];i++)if(!xqg_tensor_float(&values[m->header[4+i]]))goto done;
    for(i=0;i<m->header[3];i++){j=m->header[4+i];m->outputs[i]=values[j].f32;values[j].f32=NULL;}
    m->batch=batch;okay=1;
done:
    if(!okay)fprintf(stderr,"XQ_NATIVE_GRAPH_FAIL node=%u model=%u no_fallback=1\n",i,m->header[1]);
    for(i=0;i<m->header[2];i++)xqg_tensor_clear(&values[i]);
#if defined(XQ_GRAPH_PROFILE) && defined(XQ_NATIVE_COACH)
    xqg_profile_report(m->header[1],okay,graph_start);
#endif
    return okay;
}
const float *xqn_output(const xqn_model *m,unsigned i,unsigned dims[4])
{
    if(!m || i>=m->header[3] || !m->outputs[i])return NULL;
    if(dims){const int32_t *n=m->nodes[m->header[4+i]];dims[0]=m->batch;dims[1]=(unsigned)n[1];dims[2]=(unsigned)n[2];dims[3]=(unsigned)n[3];}
    return m->outputs[i];
}
int xqn_board_corners(const xqn_model *m,float corners[8])
{
    float logits[2304],sum,sx,sy,maximum;unsigned c,i;
    const float *prior=xqn_output(m,0,NULL),*maps=xqn_output(m,1,NULL);
    if(!m || m->header[1]!=0 || m->batch!=1 || !prior || !maps || !corners)return 0;
    for(c=0;c<4;c++) {
        maximum=-INFINITY;
        for(i=0;i<2304;i++) {
            float x=((i%48)+.5f)/48.f,y=((i/48)+.5f)/48.f;
            float dx=x-prior[c*2],dy=y-prior[c*2+1];
            logits[i]=maps[c*2304+i]-(dx*dx+dy*dy)/.0128f;
            if(logits[i]>maximum)maximum=logits[i];
        }
        sum=sx=sy=0;
        for(i=0;i<2304;i++){logits[i]=expf(logits[i]-maximum);sum+=logits[i];}
        for(i=0;i<2304;i++){float v=logits[i]/sum;sx+=v*((i%48)+.5f)/48.f;sy+=v*((i/48)+.5f)/48.f;}
        corners[c*2]=sx;corners[c*2+1]=sy;
    }
    return 1;
}
