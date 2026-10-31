#include "crc32_fast.h"
/* Slicing-by-2 costs 2KiB of BRAM. Read one aligned source word per four
 * bytes and fold its two halves using the reflected IEEE streaming state. */
static uint32_t table[2][256];
static int initialized;
#if defined(__GNUC__) && defined(__BYTE_ORDER__) && (__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__)
typedef uint32_t crc32_word_t __attribute__((__may_alias__));
#endif
uint32_t crc32_fast(uint32_t crc,const void *bytes,uint32_t count)
{
 const uint8_t *p=bytes;
 uint32_t i,j,c;
 if(!initialized){
  for(i=0;i<256u;i++){
   c=i;
   for(j=0;j<8u;j++)c=(c>>1)^(0xedb88320u&-(c&1u));
   table[0][i]=c;
  }
  for(i=0;i<256u;i++){
   c=table[0][i];table[1][i]=table[0][c&255u]^(c>>8);
  }
  initialized=1;
 }
 while(count&&((uintptr_t)p&3u)){
  crc=table[0][(crc^*p++)&255u]^(crc>>8);count--;
 }
 while(count>=4u){
#if defined(__GNUC__) && defined(__BYTE_ORDER__) && (__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__)
  c=crc^*(volatile const crc32_word_t *)(const void *)p;
#else
  c=crc^((uint32_t)p[0]|((uint32_t)p[1]<<8)|
         ((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24));
#endif
  c=table[1][c&255u]^table[0][(c>>8)&255u]^(c>>16);
  crc=table[1][c&255u]^table[0][(c>>8)&255u]^(c>>16);
  p+=4;count-=4;
 }
 while(count--)crc=table[0][(crc^*p++)&255u]^(crc>>8);
 return crc;
}
