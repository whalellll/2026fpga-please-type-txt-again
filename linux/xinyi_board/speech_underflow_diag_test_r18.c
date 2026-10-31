#define UF_NO_MAIN 1
#include "speech_underflow_diag_r18.c"
#include <assert.h>
typedef struct {unsigned writes;uint32_t u,hash;uint64_t clock;int mode;} F;
static uint32_t fs(void *p){return ((F*)p)->mode==1?256u:0u;}
static uint32_t fu(void *p){return ((F*)p)->u;}
static void fw(void *p,uint32_t v){F*f=p;++f->writes;f->hash=(f->hash^v)*16777619u;if(f->mode==3||f->writes==17||f->writes==130||f->writes==257)++f->u;}
static uint64_t ft(void*p){F*f=p;return f->clock+=10000;}
static int fc(void*p){F*f=p;return f->mode==2 && f->writes>=256;}
int main(void)
{
 int16_t pcm[4096];for(unsigned i=0;i<4096;i++)pcm[i]=(int16_t)(i*7993u+17u);
 for(unsigned mode=0;mode<4;mode++)for(unsigned length=31;length<=4096;length=length==31?512:4097){
  F a={.mode=(int)mode},b=a;xqs_io x={&a,fs,fu,fw,ft,fc},y={&b,fs,fu,fw,ft,fc};uint32_t da=999,db=998;uf_reset();
  int ra=xqs_stream_reference(&x,pcm,length,&da),rb=xqs_stream(&y,pcm,length,&db);
  assert(ra==rb && da==db && a.writes==b.writes && a.hash==b.hash && a.u==b.u && a.clock==b.clock);
  assert(uf_count<=32);for(unsigned j=0;j<uf_count;j++)assert(uf_events[j].sample_index<=b.writes && uf_events[j].stage==1);
 }
 F a={.mode=3},b=a;xqs_io x={&a,fs,fu,fw,ft,fc},y={&b,fs,fu,fw,ft,fc};uint32_t da,db;uf_reset();
 assert(xqs_stream_reference(&x,pcm,4096,&da)==xqs_stream(&y,pcm,4096,&db));
 assert(da==db && uf_count==32 && a.hash==b.hash);
 assert(uf_events[0].sample_index==64 && uf_events[0].delta==64);
 assert(xqs_stream(&y,pcm,31,&db));assert(uf_stage==2);
 puts("UF_DIAG_REAL_STREAM_OUTPUT_DELTA_RC_CANCEL_TIMEOUT_CAPACITY_PASS_NOT_BOARD");return 0;
}
