/* Offline experiment, not a production loader. Introspect the existing private
 * graph in this translation unit; keep its frozen pack, conv input/output
 * exponents and weights, replacing only the classifier GAP with the r24a op.
 * No XQGRPH2 format or preview calibration parameters are invented. */
#include "graph_runtime.c"
#include "graph_ops.h"
#include "test_v321_mock.h"
#include "xq_sha256.h"
#include <assert.h>
typedef struct { unsigned count;char hash[8][4][65];int8_t *head_input;size_t head_count; } trial_trace;
static void trace_layer(void *ctx,unsigned layer,const int8_t *q,size_t qn,
    const int16_t *out,size_t on,const int32_t *acc,const int16_t *pre)
{
    trial_trace *t=ctx;assert(t->count<8 && layer==72+t->count);
    xq_sha256_hex(q,qn,t->hash[t->count][0]);xq_sha256_hex(acc,on*4,t->hash[t->count][1]);
    xq_sha256_hex(pre,on*2,t->hash[t->count][2]);xq_sha256_hex(out,on*2,t->hash[t->count][3]);t->count++;
    if(layer==79){t->head_input=malloc(qn);assert(t->head_input);memcpy(t->head_input,q,qn);t->head_count=qn;}
}
static int integer_classifier(xqn_model *m,const xqm_transport *io,unsigned batch,
    float *input,float **published,xqm_stats *stats,trial_trace *trace)
{
    xqg_tensor v[200]={0},initial={.f32=input,.count=(size_t)batch*3*32*32};
    int32_t input_shape[4]={0,3,32,32};int okay=0;unsigned gaps=0;
    *published=NULL;memset(stats,0,sizeof(*stats));
    if(m->header[1]!=2 || m->header[3]!=1 || m->header[4]!=m->header[2]-1)return 0;
    for(unsigned i=0;i<m->header[2];i++){
        const int32_t *n=m->nodes[i],*s=i?m->nodes[i-1]:input_shape;
        xqg_tensor *source=i?&v[i-1]:&initial;
        if(n[4]!=1 || n[5]!=(int32_t)i-1 || (n[0]!=1 && n[0]!=9))goto done;
        v[i].count=(size_t)batch*elements(n);v[i].q16=malloc(v[i].count*2);if(!v[i].q16)goto done;
        if(n[0]==9){
            xqg_s16_view a={source->q16,source->count,batch,(unsigned)s[1],(unsigned)s[2],(unsigned)s[3],source->exponent},out;
            if(!xqg_op_run(9,&a,1,v[i].q16,v[i].count,NULL,&out) || out.count!=v[i].count ||
               out.channels!=(unsigned)n[1] || out.height!=(unsigned)n[2] || out.width!=(unsigned)n[3])goto done;
            v[i].exponent=out.exponent;gaps++;
        } else {
            size_t qn=(size_t)batch*elements(s),on=v[i].count,k=(size_t)s[1]*n[10]*n[11];
            if(!range((size_t)n[20],(size_t)n[1]*k,m->header[7]) || !range((size_t)n[21],(size_t)n[1]*4,m->header[7]) ||
               !range((size_t)n[22],(size_t)n[1]*8,m->header[7]) || !range((size_t)n[23],(size_t)n[24],m->header[7]))goto done;
            int8_t *q=malloc(qn);int32_t *acc=malloc(on*4);int16_t *pre=malloc(on*2);xqm_stats st={0};
            if(!q || !acc || !pre){free(q);free(acc);free(pre);goto done;}
            xqi_shape shape={batch,(unsigned)s[1],(unsigned)s[2],(unsigned)s[3],(unsigned)n[1],
                (unsigned)n[10],(unsigned)n[11],(unsigned)n[12],(unsigned)n[13],(unsigned)n[14],(unsigned)n[15],
                (unsigned)n[16],(unsigned)n[17],(unsigned)n[25],0};
            int success=xqg_tensor_quantize(source,n[18],q) &&
                xqi_layer(io,&shape,q,(const int8_t *)m->blob+n[20],(const int32_t *)(m->blob+n[21]),
                          (const int64_t *)(m->blob+n[22]),(const int8_t *)m->blob+n[23],(size_t)n[24],acc,pre,v[i].q16,&st);
            if(success)trace_layer(trace,(unsigned)n[9],q,qn,v[i].q16,on,acc,pre);
            free(q);free(acc);free(pre);if(!success)goto done;
            v[i].exponent=n[19];stats->jobs+=st.jobs;stats->cycles+=st.cycles;
        }
    }
    if(gaps!=1 || trace->count!=8)goto done;
    xqg_tensor *last=&v[m->header[4]];
    if(!xqg_tensor_float(last))goto done;
    *published=last->f32;last->f32=NULL;okay=1;
done:
    for(unsigned i=0;i<m->header[2];i++)xqg_tensor_clear(v+i);
    return okay;
}
int main(int argc,char **argv)
{
    assert(argc==2);xqn_model *m=xqn_load(argv[1]);assert(m && m->header[1]==2);
    xqm_linux device={.fd=-1};assert(v321_mock_open(&device));
    const unsigned batches[]={1,3,8};
    for(unsigned scenario=0;scenario<3;scenario++){
        unsigned batch=batches[scenario];size_t count=(size_t)batch*3*32*32;
        int16_t *raw=malloc(count*2);float *input=malloc(count*4),*result=NULL;assert(raw && input);
        for(size_t i=0;i<count;i++)raw[i]=(int16_t)((int)((i*17+i/(3*32*32)*37)%255)-128);
        assert(xqi_dequantize(raw,count,m->nodes[0][18],input));
        trial_trace old={0},now={0};xqm_stats before,after;
        xqn_observe(m,trace_layer,&old);v321_mock_reset(0);
        assert(xqn_run(m,&device.io,batch,input,0,&before));
        unsigned dims[4];const float *expected=xqn_output(m,0,dims);assert(expected && dims[0]==batch);
        v321_mock_reset(0);assert(integer_classifier(m,&device.io,batch,input,&result,&after,&now));
        assert(old.count==8 && now.count==8 && before.jobs==after.jobs && before.cycles==after.cycles);
        for(unsigned i=0;i<7;i++)assert(!memcmp(old.hash[i],now.hash[i],sizeof(old.hash[i])));
        unsigned agree=0,head_different=0,head_max_delta=0;
        assert(old.head_count==now.head_count);
        for(size_t i=0;i<old.head_count;i++){
            int d=(int)old.head_input[i]-now.head_input[i];unsigned magnitude=(unsigned)(d<0?-d:d);
            if(magnitude)head_different++;
            if(magnitude>head_max_delta)head_max_delta=magnitude;
        }
        for(unsigned b=0;b<batch;b++){
            unsigned a=0,c=0;
            for(unsigned j=1;j<dims[1];j++){
                if(expected[b*dims[1]+j]>expected[b*dims[1]+a])a=j;
                if(result[b*dims[1]+j]>result[b*dims[1]+c])c=j;
            }
            if(a==c)agree++;
        }
        size_t bytes=(size_t)batch*dims[1]*4;char hash[65];xq_sha256_hex(result,bytes,hash);
        printf("CLASSIFIER_S16_TRIAL batch=%u jobs=%llu pre_gap_layers_equal=7 head_input_equal=%u head_values_changed=%u head_max_delta=%u output_equal=%u class_equal=%u sha256=%s\n",
            batch,(unsigned long long)after.jobs,!strcmp(old.hash[7][0],now.hash[7][0]),head_different,head_max_delta,!memcmp(expected,result,bytes),agree,hash);
        free(old.head_input);free(now.head_input);
        free(result);result=NULL;memset(&now,0,sizeof(now));v321_mock_reset(2);
        assert(!integer_classifier(m,&device.io,batch,input,&result,&after,&now) && !result);
        v321_mock_counts c;v321_mock_read(&c);assert(c.attempts==2 && c.jobs==1 && c.errors==1);
        free(raw);free(input);
    }
    xqn_free(m);v321_mock_close(&device);
    puts("CLASSIFIER_S16_GAP_TRIAL_FROZEN_EXPONENTS_AND_FATAL_IO_PASS_NOT_SELECTION");return 0;
}
