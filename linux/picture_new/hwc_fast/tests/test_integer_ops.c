/* Independent scalar references for the memory-saving integer kernels. */
#define XI8_TEST 1
#include "../integer_hwc.c"
#include <assert.h>
static uint32_t rng=0x8126cfea;
static uint32_t random_word(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static void pool_case(unsigned h,unsigned w,unsigned c,unsigned bits){
 size_t count=(size_t)h*w*c,bytes=count*bits/8;
 xi8_tensor a={.data=malloc(bytes),.c=c,.h=h,.w=w,.pitch=c,.bits=bits},out=a;
 out.data=malloc(bytes);int32_t n[32]={0};n[0]=4;n[4]=1;n[5]=0;n[10]=5;n[14]=2;
 assert(a.data && out.data);
 for(size_t i=0;i<count;i++)put(&a,i,bits==8?(int8_t)random_word():bits==16?(int16_t)random_word():(int32_t)random_word());
 assert(nonconv(n,&a,&out));
 for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)for(unsigned q=0;q<c;q++){
  int32_t best=INT32_MIN;
  for(int yy=(int)y-2;yy<=(int)y+2;yy++)for(int xx=(int)x-2;xx<=(int)x+2;xx++)if(yy>=0 && yy<(int)h && xx>=0 && xx<(int)w){
   int32_t v=get(&a,((size_t)(unsigned)yy*w+(unsigned)xx)*c+q);if(v>best)best=v;
  }
  assert(get(&out,((size_t)y*w+x)*c+q)==best);
 }
 free(a.data);free(out.data);
}
static void narrow_case(unsigned source_offset,unsigned destination_offset,size_t count){
 uint8_t *raw=malloc(count*2+32),*dst=malloc(count+32);assert(raw && dst);
 int16_t *src=(void *)(raw+source_offset);memset(dst,0x5a,count+32);
 for(size_t i=0;i<count;i++)src[i]=count==65536?(int16_t)i:(int16_t)(i*3919u+random_word());
 narrow_s16_s8((int8_t *)dst+destination_offset,src,count);
 for(size_t i=0;i<count;i++)assert(dst[destination_offset+i]==(uint8_t)src[i]);
 for(unsigned i=0;i<destination_offset;i++)assert(dst[i]==0x5a);
 for(size_t i=destination_offset+count;i<count+32;i++)assert(dst[i]==0x5a);
 free(raw);free(dst);
}
static void input_case(unsigned bits,int delta,unsigned channels,unsigned pitch,int sx,int sy){
 xi8_tensor src={.c=channels,.h=5,.w=7,.pitch=pitch,.bits=bits,.exponent=delta};
 size_t count=(size_t)src.h*src.w*pitch;src.data=malloc(count*bits/8);assert(src.data);
 for(size_t i=0;i<count;i++)put(&src,i,bits==8?(int8_t)random_word():bits==16?(int16_t)random_word():(int32_t)(random_word()&0xffffff)-0x800000);
 unsigned cp=align4(channels);size_t bytes=9*7*cp;
 uint8_t *actual=malloc(bytes+16),*expected=calloc(1,bytes);assert(actual && expected);memset(actual,0xa5,bytes+16);
 xi8_stats stats={0};pack_input(actual,&src,9,7,sx,sy,0,&stats);
 for(unsigned y=0;y<7;y++)for(unsigned x=0;x<9;x++)for(unsigned q=0;q<channels;q++){
  int ix=sx+(int)x,iy=sy+(int)y;
  if(ix>=0 && ix<(int)src.w && iy>=0 && iy<(int)src.h)expected[((size_t)y*9+x)*cp+q]=(uint8_t)quant(get(&src,((size_t)(unsigned)iy*src.w+(unsigned)ix)*pitch+q),delta);
 }
 /* Existing HWC direct-copy semantics preserve opaque padded source lanes.
  * They are ignored by CIN, but the entire packed shadow must still match. */
 if(bits==8 && delta==0 && pitch==cp)for(unsigned y=0;y<7;y++)for(unsigned x=0;x<9;x++){
  int ix=sx+(int)x,iy=sy+(int)y;
  if(ix>=0 && ix<(int)src.w && iy>=0 && iy<(int)src.h)for(unsigned q=channels;q<cp;q++)expected[((size_t)y*9+x)*cp+q]=((uint8_t *)src.data)[((size_t)(unsigned)iy*src.w+(unsigned)ix)*pitch+q];
 }
 assert(!memcmp(actual,expected,bytes));for(size_t i=bytes;i<bytes+16;i++)assert(actual[i]==0xa5);
 assert(stats.input_zero_bytes<=bytes);
 assert(stats.input_zero_bytes+stats.converted_input_values+stats.copied_input_bytes==bytes);
 free(actual);free(expected);free(src.data);
}
static void add_case(unsigned ba,unsigned bb,int sa,int sb,int alias){
 enum{COUNT=90};xi8_tensor values[2]={{.c=3,.h=5,.w=6,.pitch=3,.bits=ba,.exponent=sa},{.c=3,.h=5,.w=6,.pitch=3,.bits=bb,.exponent=sb}};
 int16_t expected[COUNT];int32_t n[32]={0};n[0]=8;n[4]=2;n[5]=0;n[6]=1;
 for(unsigned j=0;j<2;j++){values[j].data=malloc(COUNT*values[j].bits/8);assert(values[j].data);for(unsigned i=0;i<COUNT;i++)put(&values[j],i,(int)(random_word()%101)-50);}
 for(unsigned i=0;i<COUNT;i++)expected[i]=(int16_t)(get(&values[0],i)*(1<<sa)+get(&values[1],i)*(1<<sb));
 xi8_tensor out={.data=alias?values[0].data:malloc(COUNT*2),.c=3,.h=5,.w=6,.pitch=3,.bits=16};assert(out.data);
 assert(nonconv(n,values,&out));assert(!memcmp(out.data,expected,sizeof(expected)));
 if(!alias)free(out.data);free(values[0].data);free(values[1].data);
}
int main(void){
 for(unsigned bits=8;bits<=32;bits*=2)for(unsigned h=1;h<=7;h++)for(unsigned w=1;w<=7;w++)for(unsigned c=1;c<=5;c+=2)pool_case(h,w,c,bits);
 pool_case(20,20,128,8);
 for(unsigned s=0;s<=2;s+=2)for(unsigned d=0;d<4;d++)for(size_t n=0;n<260;n++)narrow_case(s,d,n);
 narrow_case(0,0,65536);
 for(unsigned bits=8;bits<=32;bits*=2)for(int delta=-32;delta<=8;delta+=4)for(unsigned c=1;c<=8;c++)for(int pos=-3;pos<=3;pos+=3){
  input_case(bits,delta,c,c,pos,pos);if(bits==8)input_case(bits,delta,c,align4(c),pos,pos);
 }
 for(unsigned a=8;a<=16;a*=2)for(unsigned b=8;b<=16;b*=2)for(int sa=0;sa<=2;sa++)for(int sb=0;sb<=2;sb++){add_case(a,b,sa,sb,0);if(a==16)add_case(a,b,sa,sb,1);}
 puts("INTEGER_OPS_POOL_NARROW_PACK_ADD_ALIAS_REFERENCE_PASS");return 0;
}
