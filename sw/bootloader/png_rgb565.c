#include "png_rgb565.h"
#include "crc32_fast.h"

typedef struct {png565_write_fn write;void *user;uint32_t file_crc,chunk_crc;int file_crc_enabled;} png_sink_t;
#if defined(__GNUC__) && defined(__BYTE_ORDER__) && (__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__)
/* The snapshot is byte storage, so a plain uint32_t pointer would violate
 * effective-type aliasing. GCC's may_alias permits the aligned word load. */
typedef uint32_t png565_word_t __attribute__((__may_alias__));
#define PNG565_ALIGNED_WORDS 1
#endif
/* Filter byte sits at offset3, so the following RGB data is word aligned.
 * Four pixels can be stored with three BRAM word transactions instead of
 * twelve byte transactions. The emitted scanline still starts at Filter None. */
static uint32_t row_words[(PNG565_ROW_BYTES+3u)/4u];
#define row ((uint8_t *)(void *)row_words+3u)

#if defined(__GNUC__)
__attribute__((__always_inline__))
#endif
static inline void expand_row(const uint8_t *pixels,uint32_t *a_out,
                              uint32_t *b_out,int aligned)
{
 uint32_t x,p0,p1,r0,g0,b0,r1,g1,b1,r2,g2,b2,r3,g3,b3;
 uint32_t rr,gg,bb,a=*a_out,b=*b_out;
 uint32_t *out=row_words+1;
 row[0]=0;b+=a; /* Filter None contributes zero to a and the current a to b. */
 for(x=0;x<PNG565_WIDTH;x+=4){
#if defined(PNG565_ALIGNED_WORDS)
  if(aligned){
   p0=*(volatile const png565_word_t *)(const void *)pixels;
   p1=*(volatile const png565_word_t *)(const void *)(pixels+4);
  }else
#else
  (void)aligned;
#endif
  {
   p0=(uint32_t)pixels[0]|((uint32_t)pixels[1]<<8)|
      ((uint32_t)pixels[2]<<16)|((uint32_t)pixels[3]<<24);
   p1=(uint32_t)pixels[4]|((uint32_t)pixels[5]<<8)|
      ((uint32_t)pixels[6]<<16)|((uint32_t)pixels[7]<<24);
  }
  pixels+=8;
  /* Expand both halfwords together; masks prevent cross-pixel bits. */
  rr=((p0>>8)&0x00f800f8u)|((p0>>13)&0x00070007u);
  gg=((p0>>3)&0x00fc00fcu)|((p0>>9)&0x00030003u);
  bb=((p0<<3)&0x00f800f8u)|((p0>>2)&0x00070007u);
  r0=rr&255u;g0=gg&255u;b0=bb&255u;
  r1=rr>>16;g1=gg>>16;b1=bb>>16;
  rr=((p1>>8)&0x00f800f8u)|((p1>>13)&0x00070007u);
  gg=((p1>>3)&0x00fc00fcu)|((p1>>9)&0x00030003u);
  bb=((p1<<3)&0x00f800f8u)|((p1>>2)&0x00070007u);
  r2=rr&255u;g2=gg&255u;b2=bb&255u;
  r3=rr>>16;g3=gg>>16;b3=bb>>16;
#if defined(PNG565_ALIGNED_WORDS)
  out[0]=r0|(g0<<8)|(b0<<16)|(r1<<24);
  out[1]=g1|(b1<<8)|(r2<<16)|(g2<<24);
  out[2]=b2|(r3<<8)|(g3<<16)|(b3<<24);
#else
  {
   uint8_t *bytes=(uint8_t *)(void *)out;
   bytes[0]=(uint8_t)r0;bytes[1]=(uint8_t)g0;bytes[2]=(uint8_t)b0;
   bytes[3]=(uint8_t)r1;bytes[4]=(uint8_t)g1;bytes[5]=(uint8_t)b1;
   bytes[6]=(uint8_t)r2;bytes[7]=(uint8_t)g2;bytes[8]=(uint8_t)b2;
   bytes[9]=(uint8_t)r3;bytes[10]=(uint8_t)g3;bytes[11]=(uint8_t)b3;
  }
#endif
  out+=3;
  /* Same byte order as the output, without reading the row a second time. */
  a+=r0;b+=a;a+=g0;b+=a;a+=b0;b+=a;
  a+=r1;b+=a;a+=g1;b+=a;a+=b1;b+=a;
  a+=r2;b+=a;a+=g2;b+=a;a+=b2;b+=a;
  a+=r3;b+=a;a+=g3;b+=a;a+=b3;b+=a;
 }
 /* 3841 bytes keep both sums below2^32 before reducing once per row. */
 *a_out=a%65521u;*b_out=b%65521u;
}
static void be32(uint8_t *b,uint32_t n)
{b[0]=(uint8_t)(n>>24);b[1]=(uint8_t)(n>>16);b[2]=(uint8_t)(n>>8);b[3]=(uint8_t)n;}
static int emit(png_sink_t *s,const uint8_t *b,uint32_t n,int chunk)
{
 int r=s->write(s->user,b,n);
 if(r)return r;
 if(s->file_crc_enabled)s->file_crc=crc32_fast(s->file_crc,b,n);
 if(chunk)s->chunk_crc=crc32_fast(s->chunk_crc,b,n);
 return 0;
}
static int chunk_start(png_sink_t *s,const uint8_t type[4],uint32_t n)
{
 uint8_t len[4];int r;
 be32(len,n);s->chunk_crc=0xffffffffu;
 r=emit(s,len,4u,0);if(r)return r;
 return emit(s,type,4u,1);
}
static int chunk_end(png_sink_t *s)
{uint8_t crc[4];be32(crc,s->chunk_crc^0xffffffffu);return emit(s,crc,4u,0);}
int png565_encode(const uint8_t *pixels,png565_write_fn write,void *user,
                  png565_poll_fn poll,uint32_t *file_crc)
{
 static const uint8_t signature[8]={137,80,78,71,13,10,26,10};
 static const uint8_t ihdr[4]={'I','H','D','R'},idat[4]={'I','D','A','T'},iend[4]={'I','E','N','D'};
 uint8_t header[13],block[5],adler[4],zheader[2]={0x78,0x01};
 png_sink_t s;uint32_t y,a=1,b=0;uint16_t n=(uint16_t)PNG565_ROW_BYTES;
 int r;
 if(!pixels||!write)return -1;
 s.write=write;s.user=user;s.file_crc=0xffffffffu;s.chunk_crc=0;s.file_crc_enabled=file_crc!=0;
 be32(header,PNG565_WIDTH);be32(header+4,PNG565_HEIGHT);
 header[8]=8;header[9]=2;header[10]=0;header[11]=0;header[12]=0;
 r=emit(&s,signature,8,0);if(r)return r;
 r=chunk_start(&s,ihdr,13);if(r)return r;
 r=emit(&s,header,13,1);if(r)return r;
 r=chunk_end(&s);if(r)return r;
 r=chunk_start(&s,idat,2u+PNG565_HEIGHT*(5u+PNG565_ROW_BYTES)+4u);if(r)return r;
 r=emit(&s,zheader,2,1);if(r)return r;
 for(y=0;y<PNG565_HEIGHT;y++){
  if(poll&&(r=poll(user,y))!=0)return r;
  if(((uintptr_t)pixels&3u)==0u)expand_row(pixels,&a,&b,1);
  else expand_row(pixels,&a,&b,0);
  pixels+=PNG565_WIDTH*2u;
  block[0]=(y+1u==PNG565_HEIGHT)?1u:0u;
  block[1]=(uint8_t)n;block[2]=(uint8_t)(n>>8);
  block[3]=(uint8_t)~n;block[4]=(uint8_t)(~n>>8);
  r=emit(&s,block,5,1);if(r)return r;
  r=emit(&s,row,PNG565_ROW_BYTES,1);if(r)return r;
 }
 be32(adler,(b<<16)|a);r=emit(&s,adler,4,1);if(r)return r;
 r=chunk_end(&s);if(r)return r;
 r=chunk_start(&s,iend,0);if(r)return r;
 r=chunk_end(&s);if(r)return r;
 if(file_crc)*file_crc=s.file_crc^0xffffffffu;
 return 0;
}
