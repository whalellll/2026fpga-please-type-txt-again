#include "xq_int8_layer.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
extern int xi8_test_quant(int32_t,int);
int main(void){
 int16_t *src=malloc(65536*2);int8_t *out=malloc(65536);float *exact=malloc(65536*4);assert(src && out && exact);
 for(unsigned i=0;i<65536;i++){src[i]=(int16_t)((int)i-32768);exact[i]=(float)src[i];}
 for(int d=-32;d<=8;d++){
  assert(xqi_quantize(exact,65536,-d,out));
  for(unsigned i=0;i<65536;i++)assert(xi8_test_quant(src[i],d)==out[i]);
 }
 uint32_t random=0x6139a52d;
 for(unsigned i=0;i<20000;i++){
  random^=random<<13;random^=random>>17;random^=random<<5;
  int32_t v=(int32_t)(random&0xffffff)-0x800000;
  if(i<4)v=(i&1?-1:1)*(int32_t)(i<2?0xffffff:0x800001);
  float f=(float)v;
  for(int d=-32;d<=8;d++){int8_t expected;assert(xqi_quantize(&f,1,-d,&expected));assert(xi8_test_quant(v,d)==expected);}
 }
 free(src);free(out);free(exact);puts("INTEGER_QUANT_EXHAUSTIVE_S16_AND_S24_REFERENCE_PASS");return 0;
}
