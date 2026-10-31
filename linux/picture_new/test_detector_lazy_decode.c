#define _POSIX_C_SOURCE 200809L
#include "xq_native_graph.h"
#include "xq_roi.h"
#include "native_parameters.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define XQ_NATIVE_DETECTOR_SIDE 640u
static unsigned which,obj_calls[2],box_calls[2],pre_count[2],cases;
static int allocation_fail;
void *__real_malloc(size_t);
void *__wrap_malloc(size_t bytes){return allocation_fail?NULL:__real_malloc(bytes);}
#ifdef XQDECODE_TEST_PROBE
#define XQDECODE_NOTE_BOX() (++box_calls[which])
#define XQDECODE_NOTE_OBJ() (++obj_calls[which])
#else
#define XQDECODE_NOTE_BOX() ((void)0)
#define XQDECODE_NOTE_OBJ() ((void)0)
#endif
/* The checker creates this directly from the pinned immutable worker. */
#include "decoder_reference.inc"
_Static_assert(sizeof(proposal)==28,"proposal byte comparison must include no padding");
static proposal *pre[2];
static xqr_box output[2][300];
static unsigned capture_nms(proposal *p,unsigned n,xqr_box out[300])
{assert(n<=352800);pre_count[which]=n;memcpy(pre[which],p,n*sizeof(*p));return nms(p,n,out);}
#define XQDECODE_NMS capture_nms
#include "detector_lazy_decode.h"

struct xqn_model {float *head[3];unsigned dims[3][4];int missing;};
const float *xqn_output(const xqn_model *m,unsigned index,unsigned dims[4])
{assert(index<3);memcpy(dims,m->dims[index],4*sizeof(*dims));return m->missing==(int)index?NULL:m->head[index];}
static void reset(xqn_model *m,float background_obj)
{
    m->missing=-1;
    for(unsigned head=0;head<3;head++) {
        unsigned side=80u>>head,area=side*side;
        m->dims[head][0]=1;m->dims[head][1]=57;m->dims[head][2]=side;m->dims[head][3]=side;
        for(unsigned i=0;i<57*area;i++)m->head[head][i]=-INFINITY;
        for(unsigned a=0;a<3;a++)for(unsigned i=0;i<area;i++)m->head[head][(a*19+4)*area+i]=background_obj;
    }
}
static float *anchor(xqn_model *m,unsigned head,unsigned a,unsigned position)
{return m->head[head]+a*19*m->dims[head][2]*m->dims[head][2]+position;}
static void activate(xqn_model *m,unsigned head,unsigned a,unsigned position,float obj,float cls)
{
    unsigned area=m->dims[head][2]*m->dims[head][2];float *p=anchor(m,head,a,position);
    p[0]=.125f;p[area]=-.25f;p[2*area]=.375f;p[3*area]=-.5f;p[4*area]=obj;
    for(unsigned c=0;c<14;c++)p[(c+5)*area]=cls;
}
static void sparse_candidates(xqn_model *m)
{
    reset(m,-INFINITY);
    for(unsigned i=0;i<36;i++) {
        unsigned head=i%3,side=80u>>head,area=side*side;
        activate(m,head,i%3,(i*37u)%area,0,-INFINITY);
        anchor(m,head,i%3,(i*37u)%area)[(5+i%14)*area]=0;
    }
}
static void compare(xqn_model *m)
{
    int status[2];unsigned count[2]={0x1234u,0x1234u};
    for(which=0;which<2;which++) {
        memset(output[which],0xa5,sizeof(output[which]));pre_count[which]=0;box_calls[which]=0;obj_calls[which]=0;
        status[which]=which?xqdecode_detector_boxes(m,output[which],&count[which]):
                            reference_detector_boxes(m,output[which],&count[which]);
    }
    assert(status[0]==status[1] && count[0]==count[1]);
#ifdef XQDECODE_TEST_PROBE
    assert(obj_calls[0]==obj_calls[1] && box_calls[1]<=box_calls[0]);
#endif
    assert(pre_count[0]==pre_count[1] && !memcmp(pre[0],pre[1],pre_count[0]*sizeof(proposal)));
    assert(!memcmp(output[0],output[1],sizeof(output[0])));++cases;
}
static void correctness(xqn_model *m)
{
    reset(m,-INFINITY);compare(m);
    /* Every anchor passes obj but no class can contribute: the exact waste. */
    reset(m,-4.f);compare(m);
#ifdef XQDECODE_TEST_PROBE
    assert(obj_calls[0]==25200 && box_calls[0]==25200 && box_calls[1]==0);
#endif
    reset(m,-INFINITY);
    for(unsigned h=0;h<3;h++)for(unsigned a=0;a<3;a++)activate(m,h,a,7+a,0.f,a==0?-1.f:-2.f);
    compare(m);assert(pre_count[0]==3*3*14);
    /* Duplicate boxes/scores exercise class-aware suppression and stable ties. */
    reset(m,-INFINITY);activate(m,0,0,40,0,0);activate(m,0,0,41,0,0);activate(m,1,0,3,0,0);compare(m);
    sparse_candidates(m);compare(m);assert(pre_count[0]==36);
    float obj=logf(.001f/(1.f-.001f)),cls=logf(.002f/(1.f-.002f));
    for(int offset=-8;offset<=8;offset++) {
        float value=obj;for(int i=0;i<abs(offset);i++)value=nextafterf(value,offset<0?-INFINITY:INFINITY);
        reset(m,-INFINITY);activate(m,0,0,0,value,INFINITY);compare(m);
        value=cls;for(int i=0;i<abs(offset);i++)value=nextafterf(value,offset<0?-INFINITY:INFINITY);
        reset(m,-INFINITY);activate(m,0,0,0,0,value);compare(m);
    }
    const uint32_t special[]={0x00000000u,0x80000000u,0x7f800000u,0xff800000u,0x7fc12345u,0xffc12345u,0x7f7fffffu,0xff7fffffu,0x00000001u};
    for(unsigned s=0;s<sizeof(special)/sizeof(*special);s++)for(unsigned field=0;field<6;field++) {
        float value;memcpy(&value,special+s,4);reset(m,-INFINITY);activate(m,0,0,5,0,0);
        unsigned area=80u*80u;anchor(m,0,0,5)[field*area]=value;compare(m);
    }
    /* Deterministic finite logits across all three heads, sparse active cells. */
    uint32_t state=0x59aab1e3u;
    reset(m,-INFINITY);
    for(unsigned i=0;i<120;i++) {
        unsigned head=i%3,side=80u>>head,area=side*side;
        activate(m,head,i%3,(i*37u)%area,0,-INFINITY);
        float *p=anchor(m,head,i%3,(i*37u)%area);
        for(unsigned field=0;field<19;field++){state=state*1664525u+1013904223u;p[field*area]=((int)(state%32001u)-16000)*(1.f/1000.f);}
    }
    compare(m);
    for(unsigned head=0;head<3;head++)for(unsigned field=0;field<4;field++) {
        reset(m,-INFINITY);m->dims[head][field]^=1;compare(m);
    }
    for(int head=0;head<3;head++){reset(m,-INFINITY);m->missing=head;compare(m);}
    reset(m,-INFINITY);allocation_fail=1;compare(m);allocation_fail=0;
}
int main(int argc,char **argv)
{
    xqn_model m={0};
    for(unsigned h=0;h<3;h++){unsigned side=80u>>h;m.head[h]=malloc((size_t)57*side*side*4);assert(m.head[h]);}
    for(unsigned i=0;i<2;i++){pre[i]=malloc(352800*sizeof(proposal));assert(pre[i]);}
    if(argc==2 && !strcmp(argv[1],"--bench")) {
#ifdef XQDECODE_TEST_PROBE
        assert(!"probe build cannot measure production timing");
#else
        for(unsigned scenario=0;scenario<2;scenario++) {
        if(scenario)sparse_candidates(&m);else reset(&m,-4.f);
        compare(&m); /* Check and warm both paths outside the measured interval. */
        for(which=0;which<2;which++)for(unsigned repeat=0;repeat<3;repeat++) {
            struct timespec a,b;unsigned count=0;assert(!clock_gettime(CLOCK_MONOTONIC,&a));
            int okay=which?xqdecode_detector_boxes(&m,output[which],&count):reference_detector_boxes(&m,output[which],&count);
            assert(!clock_gettime(CLOCK_MONOTONIC,&b));assert(okay && (scenario?count>0:!count));
            printf("DECODER_NO_PROBE_NS scenario=%s variant=%u value=%llu\n",scenario?"sparse_candidates":"inactive_classes",which,(unsigned long long)(b.tv_sec-a.tv_sec)*1000000000u+b.tv_nsec-a.tv_nsec);
        }
        }
#endif
    } else {
        assert(argc==1);correctness(&m);
        printf("DETECTOR_LAZY_PRE_NMS_NMS_THRESHOLDS_NONFINITE_DIMS_OOM_PASS cases=%u\n",cases);
    }
    for(unsigned h=0;h<3;h++)free(m.head[h]);
    for(unsigned i=0;i<2;i++)free(pre[i]);
    return 0;
}
