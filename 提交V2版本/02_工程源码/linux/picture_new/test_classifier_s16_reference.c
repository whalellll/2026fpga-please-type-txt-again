/* Independent exact-int64 oracle for the authorized classifier integration.
 * The pack loader is shared, but dot products, signed rounding, S16 GAP and
 * S8 rescaling below do not call the production layer/operator kernels. */
#include "graph_runtime.c"
#include "test_v321_mock.h"
#include "xq_sha256.h"
#include <assert.h>
typedef struct {
    unsigned count;size_t inputs[8],outputs[8];uint32_t crc[8][4];
    char hash[8][4][65];FILE *file;
} reference_trace;
static void capture(void *context,unsigned layer,const int8_t *q,size_t qn,
    const int16_t *out,size_t on,const int32_t *acc,const int16_t *pre)
{
    reference_trace *t=context;unsigned i=t->count;assert(i<8 && layer==72+i);
    const void *data[]={q,acc,pre,out};size_t bytes[]={qn,on*4,on*2,on*2};
    for(unsigned j=0;j<4;j++){
        xq_sha256_hex(data[j],bytes[j],t->hash[i][j]);
        t->crc[i][j]=crc32_fast(0xffffffffu,data[j],(uint32_t)bytes[j])^0xffffffffu;
    }
    t->inputs[i]=qn;t->outputs[i]=on;
    if(t->file)fprintf(t->file,"%u %zu %zu %08x %08x %08x %08x %s %s %s %s\n",layer,qn,on,
        t->crc[i][0],t->crc[i][1],t->crc[i][2],t->crc[i][3],t->hash[i][0],t->hash[i][1],t->hash[i][2],t->hash[i][3]);
    t->count++;
}
static int64_t divide_nearest_even(int64_t value,uint64_t divisor)
{
    uint64_t magnitude=(uint64_t)(value<0?-value:value),q=magnitude/divisor,r=magnitude%divisor;
    if(r>divisor/2 || (!(divisor&1u) && r==divisor/2 && (q&1u)))q++;
    return value<0?-(int64_t)q:(int64_t)q;
}
static int16_t clip16(int64_t value) { return value>32767?32767:value< -32768?-32768:(int16_t)value; }
static int8_t scale8(int16_t value,int source_exponent,int target_exponent)
{
    int delta=source_exponent-target_exponent;int64_t q=value;
    if(delta>=7)q=value<0?-128:value>0?128:0;
    else if(delta>=0)q*=INT64_C(1)<<delta;
    else if(delta<= -16)q=0;
    else q=divide_nearest_even(q,UINT64_C(1)<<(-delta));
    return q>127?127:q< -128?-128:(int8_t)q;
}
static float *reference(xqn_model *m,unsigned batch,const float *input,reference_trace *trace)
{
    assert(m->header[1]==2 && m->header[3]==1 && m->header[4]==m->header[2]-1);
    int16_t *values[200]={0};int exponent[200]={0};int32_t initial[4]={0,3,32,32};unsigned gaps=0;
    for(unsigned i=0;i<m->header[2];i++){
        const int32_t *n=m->nodes[i],*s=i?m->nodes[i-1]:initial;
        assert(n[4]==1 && n[5]==(int32_t)i-1);
        size_t on=(size_t)batch*elements(n),qn=(size_t)batch*elements(s);
        values[i]=malloc(on*2);assert(values[i]);
        if(n[0]==9){
            unsigned pixels=(unsigned)s[2]*s[3];assert(i && pixels<=65536 && n[2]==1 && n[3]==1 && n[1]==s[1]);
            for(size_t bc=0;bc<(size_t)batch*n[1];bc++){
                int64_t sum=0;for(unsigned p=0;p<pixels;p++)sum+=values[i-1][bc*pixels+p];
                assert(sum>=INT32_MIN && sum<=INT32_MAX);
                values[i][bc]=clip16(divide_nearest_even(sum,pixels));
            }
            exponent[i]=exponent[i-1];gaps++;continue;
        }
        assert(n[0]==1);
        int8_t *q=malloc(qn);int32_t *acc=malloc(on*4);int16_t *pre=malloc(on*2);assert(q && acc && pre);
        if(!i)assert(xqi_quantize(input,qn,n[18],q));
        else for(size_t j=0;j<qn;j++)q[j]=scale8(values[i-1][j],exponent[i-1],n[18]);
        const int8_t *weight=(const int8_t *)m->blob+n[20],*lut=(const int8_t *)m->blob+n[23];
        const int32_t *bias=(const int32_t *)(m->blob+n[21]);
        const int64_t *shift=(const int64_t *)(m->blob+n[22]);
        unsigned ic=(unsigned)s[1],ih=(unsigned)s[2],iw=(unsigned)s[3],oc=(unsigned)n[1],oh=(unsigned)n[2],ow=(unsigned)n[3];
        assert(oh==(ih+2*n[14]-n[16]*(n[10]-1)-1)/(unsigned)n[12]+1);
        assert(ow==(iw+2*n[15]-n[17]*(n[11]-1)-1)/(unsigned)n[13]+1);
        for(unsigned b=0;b<batch;b++)for(unsigned c=0;c<oc;c++)for(unsigned y=0;y<oh;y++)for(unsigned x=0;x<ow;x++){
            int64_t sum=0;
            for(unsigned ci=0;ci<ic;ci++)for(unsigned ky=0;ky<(unsigned)n[10];ky++)for(unsigned kx=0;kx<(unsigned)n[11];kx++){
                int yy=(int)(y*n[12]+ky*n[16])-n[14],xx=(int)(x*n[13]+kx*n[17])-n[15];
                if(yy>=0 && yy<(int)ih && xx>=0 && xx<(int)iw)
                    sum+=(int64_t)q[((size_t)b*ic+ci)*ih*iw+(unsigned)yy*iw+(unsigned)xx]*
                        weight[((size_t)c*ic+ci)*n[10]*n[11]+ky*n[11]+kx];
            }
            sum+=bias[c];assert(sum>=INT32_MIN && sum<=INT32_MAX && shift[c]>=0 && shift[c]<=62);
            size_t index=((size_t)b*oc+c)*oh*ow+y*ow+x;
            acc[index]=(int32_t)sum;pre[index]=clip16(divide_nearest_even(sum,UINT64_C(1)<<shift[c]));
            values[i][index]=n[24]?lut[(int)pre[index]+32768]:pre[index];
        }
        capture(trace,(unsigned)n[9],q,qn,values[i],on,acc,pre);
        exponent[i]=n[19];free(q);free(acc);free(pre);
    }
    assert(gaps==1 && trace->count==8);
    unsigned last=m->header[4];size_t count=(size_t)batch*elements(m->nodes[last]);float *out=malloc(count*4);assert(out);
    assert(xqi_dequantize(values[last],count,exponent[last],out));
    for(unsigned i=0;i<m->header[2];i++)free(values[i]);
    return out;
}
static float *canonical(const char *path)
{
    FILE *f=fopen(path,"rb");assert(f);char magic[8];uint32_t h[8];int32_t exponent;
    assert(fread(magic,1,8,f)==8 && !memcmp(magic,"XQINP1\0\0",8) && fread(h,4,8,f)==8 && fread(&exponent,4,1,f)==1);
    assert(h[0]==1 && h[1]==2 && h[2]==1 && h[3]==3 && h[4]==32 && h[5]==32 && h[6]==3072);
    int8_t raw[3072];int16_t wide[3072];float *out=malloc(3072*4);assert(out);
    assert(fread(raw,1,3072,f)==3072 && fgetc(f)==EOF && !ferror(f));fclose(f);
    assert((crc32_fast(0xffffffffu,raw,3072)^0xffffffffu)==h[7]);
    for(unsigned i=0;i<3072;i++)wide[i]=raw[i];
    assert(xqi_dequantize(wide,3072,exponent,out));return out;
}
int main(int argc,char **argv)
{
    assert(argc==4 && XQ_CLASSIFIER_S16==1);xqn_model *m=xqn_load(argv[1]);assert(m);
    FILE *checks=fopen(argv[3],"wx");assert(checks);fputs("XQ_NATIVE_CHECKS_V1\n",checks);
    xqm_linux device={.fd=-1};assert(v321_mock_open(&device));const unsigned batches[]={1,3,8};
    for(unsigned scenario=0;scenario<3;scenario++){
        unsigned batch=batches[scenario];size_t count=(size_t)batch*3072;float *input;
        if(!scenario)input=canonical(argv[2]);
        else {
            input=malloc(count*4);int16_t *q=malloc(count*2);assert(input && q);
            for(size_t i=0;i<count;i++)q[i]=(int16_t)((int)((i*17+i/3072*37)%255)-128);
            assert(xqi_dequantize(q,count,m->nodes[0][18],input));free(q);
        }
        reference_trace expected={.file=scenario?NULL:checks},actual={0};float *out=reference(m,batch,input,&expected);
        xqn_observe(m,capture,&actual);v321_mock_reset(0);xqm_stats stats;
        assert(xqn_run(m,&device.io,batch,input,0,&stats));
        assert(expected.count==8 && actual.count==8 && !memcmp(expected.hash,actual.hash,sizeof(expected.hash)));
        assert(!memcmp(expected.inputs,actual.inputs,sizeof(expected.inputs)) && !memcmp(expected.outputs,actual.outputs,sizeof(expected.outputs)));
        size_t bytes=(size_t)batch*m->nodes[m->header[4]][1]*4;
        assert(!memcmp(out,xqn_output(m,0,NULL),bytes));
#ifdef XQ_GRAPH_PROFILE
        xqg_profile profile;xqg_profile_read(&profile);
        assert(profile.calls[XQG_INTEGER_GAP]==1 && !profile.calls[XQG_FP32_9] && !profile.clock_failures);
        assert(profile.values[XQG_DEQUANTIZE]==bytes/4);
#endif
        char hash[65];xq_sha256_hex(out,bytes,hash);
        printf("CLASSIFIER_INTEGER_REFERENCE batch=%u layers=8 tensors=4 jobs=%llu final_sha256=%s\n",batch,(unsigned long long)stats.jobs,hash);
        xqn_observe(m,NULL,NULL);v321_mock_reset(2);
        assert(!xqn_run(m,&device.io,batch,input,0,&stats) && !xqn_output(m,0,NULL));
        v321_mock_counts counters;v321_mock_read(&counters);assert(counters.attempts==2 && counters.jobs==1 && counters.errors==1);
        free(input);free(out);
    }
    assert(!fclose(checks));xqn_free(m);v321_mock_close(&device);
    puts("CLASSIFIER_DIRECT_INT64_EIGHT_LAYER_FOUR_TENSOR_AND_BOUNDARY_PASS_NOT_BOARD");return 0;
}
