#define _POSIX_C_SOURCE 200809L
#include "integer_hwc.h"
#include "crc32_fast.h"
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
extern int xqv_run(const xqm_transport *,struct pango_vision32_job *);
extern void xqv_parameters_begin(const xqm_transport *,struct pango_vision32_job *);
extern int xqv_exact_available(const xqm_transport *);
struct xi8_model {uint32_t h[10];uint8_t *body,*blob;int32_t (*n)[32];xi8_tensor outputs[3];};
static volatile const uint32_t *timer;
static unsigned timer_hz=1000000000u;
void xi8_clock_init(void){
#if defined(__riscv) && __riscv_xlen==32
 int fd=open("/dev/mem",O_RDONLY|O_SYNC|O_CLOEXEC);if(fd<0)abort();
 volatile uint32_t *sys=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,0x1fe00000);
 if(sys==MAP_FAILED || sys[0x300/4]!=0x53563300 || sys[0x318/4]!=49500000)abort();
 volatile const uint32_t *p=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,0x0200b000);
 if(p==MAP_FAILED)abort();
 timer=p+0xff8/4;timer_hz=49500000;munmap((void *)sys,4096);close(fd);
#endif
}
uint64_t xi8_now(void){
 if(timer){uint32_t a,b,c;do{a=timer[1];b=timer[0];c=timer[1];}while(a!=c);return ((uint64_t)a<<32)|b;}
 struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))abort();return (uint64_t)t.tv_sec*1000000000u+(unsigned)t.tv_nsec;
}
uint64_t xi8_us(uint64_t t){return t/timer_hz*1000000u+t%timer_hz*1000000u/timer_hz;}
static unsigned align4(unsigned n){return (n+3u)&~3u;}
static int range(unsigned at,size_t bytes,size_t end){return at<=end && bytes<=end-at;}
static size_t elements(const int32_t *n){return (size_t)n[1]*n[2]*n[3];}
void xi8_tensor_free(xi8_tensor *t){if(t){free(t->data);memset(t,0,sizeof(*t));}}
void xi8_free(xi8_model *m){if(m){for(unsigned i=0;i<3;i++)xi8_tensor_free(&m->outputs[i]);free(m->body);free(m);}}
xi8_model *xi8_load(const char *path){
 FILE *f=fopen(path,"rb");char magic[8];xi8_model *m=calloc(1,sizeof(*m));unsigned refs[200]={0};
 if(!f || !m)goto bad;
 if(fread(magic,1,8,f)!=8 || memcmp(magic,"XQINT81\0",8) || fread(m->h,4,10,f)!=10 ||
    m->h[0]!=1 || m->h[1]!=1 || !m->h[2] || m->h[2]>200 || m->h[3]!=3 ||
    m->h[7]>16u*1024u*1024u || m->h[8]!=(size_t)m->h[2]*128+m->h[7])goto bad;
 m->body=malloc(m->h[8]);if(!m->body)goto bad;
 if(fread(m->body,1,m->h[8],f)!=m->h[8] || fgetc(f)!=EOF || ferror(f) ||
    (crc32_fast(0xffffffffu,m->body,m->h[8])^0xffffffffu)!=m->h[9])goto bad;
 m->n=(int32_t (*)[32])m->body;m->blob=m->body+m->h[2]*128;
 for(unsigned i=0;i<m->h[2];i++){
  const int32_t *n=m->n[i];
  if(i==0 && n[0]!=1)goto bad;
  if(n[1]<1 || n[1]>512 || n[2]<1 || n[2]>640 || n[3]<1 || n[3]>640 || elements(n)>16u*1024u*1024u ||
     n[4]<1 || n[4]>4 || n[19]<-100 || n[19]>100 || (n[27]!=8 && n[27]!=16 && n[27]!=32) ||
     n[28]<0 || n[28]>=(1<<24) || n[26]<1 || (n[31]&~3))goto bad;
  for(unsigned j=0;j<(unsigned)n[4];j++){int p=n[5+j];if(p< -1 || p>=(int)i || (p<0 && i!=0))goto bad;if(p>=0)refs[p]++;}
  if(n[0]==1){
   const int32_t *s=n[5]<0?NULL:m->n[n[5]];unsigned ci=s?(unsigned)s[1]:3;
   unsigned k=ci*(unsigned)n[10]*(unsigned)n[11],groups=((unsigned)n[1]+7)/8;
   if(n[4]!=1 || n[1]>256 || n[25] || (n[10]!=1 && n[10]!=3 && n[10]!=6) || n[11]!=n[10] ||
      (n[12]!=1 && n[12]!=2) || n[13]!=n[12] || n[14]<0 || n[14]>=n[10] || n[15]!=n[14] ||
      n[16]!=1 || n[17]!=1 || k>1152 || n[18]<-100 || n[18]>100 ||
      (n[24]!=0 && n[24]!=65536) || n[27]!=(n[24]?8:16) ||
      n[20]<0 || n[21]<0 || n[23]<0 || (n[20]&3) || (n[21]&3) ||
      n[29]!=(int)(groups*k*8) || n[30]!=(int)(groups*8*12) ||
      !range((unsigned)n[20],(size_t)n[29],m->h[7]) || !range((unsigned)n[21],(size_t)n[30],m->h[7]) || !range((unsigned)n[23],(size_t)n[24],m->h[7]))goto bad;
   unsigned ih=s?(unsigned)s[2]:640,iw=s?(unsigned)s[3]:640;
   if(ih+2*(unsigned)n[14]<(unsigned)n[10] || iw+2*(unsigned)n[14]<(unsigned)n[10] ||
      (ih+2*(unsigned)n[14]-(unsigned)n[10])/(unsigned)n[12]+1!=(unsigned)n[2] ||
      (iw+2*(unsigned)n[14]-(unsigned)n[10])/(unsigned)n[12]+1!=(unsigned)n[3])goto bad;
   for(unsigned co=0;co<groups*8;co++){
    uint32_t scale,shift;memcpy(&scale,m->blob+n[21]+co*12+4,4);memcpy(&shift,m->blob+n[21]+co*12+8,4);
    if(scale!=1 || shift>62)goto bad;
   }
  }else{
   if(n[0]!=4 && n[0]!=5 && n[0]!=7 && n[0]!=8 && n[0]!=10 && n[0]!=11)goto bad;
   if(n[0]==8){if(n[4]!=2)goto bad;}else if(n[0]!=7 && n[4]!=1)goto bad;
   const int32_t *a=m->n[n[5]];
   if(n[0]==5){if(n[1]!=a[1] || n[2]!=a[2]*2 || n[3]!=a[3]*2 || n[27]!=a[27] || n[19]!=a[19])goto bad;}
   else if(n[0]==7){unsigned channels=0;for(unsigned j=0;j<(unsigned)n[4];j++){const int32_t *b=m->n[n[5+j]];if(b[2]!=n[2] || b[3]!=n[3] || b[19]<n[19] || b[19]-n[19]>30)goto bad;channels+=(unsigned)b[1];}if(channels!=(unsigned)n[1])goto bad;}
   else{
    if(n[1]!=a[1] || n[2]!=a[2] || n[3]!=a[3])goto bad;
    if(n[0]==8){const int32_t *b=m->n[n[6]];if(n[1]!=b[1] || n[2]!=b[2] || n[3]!=b[3] || a[19]<n[19] || b[19]<n[19] || a[19]-n[19]>30 || b[19]-n[19]>30)goto bad;}
    else if(n[19]!=a[19])goto bad;
    if(n[0]==4 && (n[10]!=5 || n[14]!=2 || n[27]!=a[27]))goto bad;
   }
  }
 }
 for(unsigned j=0;j<3;j++){if(m->h[4+j]>=m->h[2])goto bad;for(unsigned k=0;k<j;k++)if(m->h[4+j]==m->h[4+k])goto bad;refs[m->h[4+j]]++;}
 for(unsigned i=0;i<m->h[2];i++)if(refs[i]!=(unsigned)m->n[i][26])goto bad;
 fclose(f);return m;
bad:if(f)fclose(f);xi8_free(m);return NULL;
}
int xi8_input_load(xi8_model *m,const char *path,xi8_tensor *t){
 FILE *f=fopen(path,"rb");char magic[8];uint32_t h[8];int okay=0;
 if(!f || !m || !t || t->data)goto done;
 if(fread(magic,1,8,f)!=8 || memcmp(magic,"XQHWC81\0",8) || fread(h,4,8,f)!=8 ||
    h[0]!=1 || h[1]!=640 || h[2]!=640 || h[3]!=3 || h[4]!=4 || h[5]!=640u*640*4 || (int32_t)h[6]!=m->n[0][18])goto done;
 t->data=malloc(h[5]);if(!t->data)goto done;
 if(fread(t->data,1,h[5],f)!=h[5] || fgetc(f)!=EOF || (crc32_fast(0xffffffffu,t->data,h[5])^0xffffffffu)!=h[7]){xi8_tensor_free(t);goto done;}
 t->c=3;t->h=t->w=640;t->pitch=4;t->bits=8;t->exponent=(int32_t)h[6];okay=1;
done:if(f)fclose(f);return okay;
}
static inline int32_t get(const xi8_tensor *t,size_t i){return t->bits==8?((int8_t *)t->data)[i]:t->bits==16?((int16_t *)t->data)[i]:((int32_t *)t->data)[i];}
static inline void put(xi8_tensor *t,size_t i,int32_t v){if(t->bits==8)((int8_t *)t->data)[i]=(int8_t)v;else if(t->bits==16)((int16_t *)t->data)[i]=(int16_t)v;else ((int32_t *)t->data)[i]=v;}
static inline int8_t quant(int32_t v,int delta){
 unsigned mag=(unsigned)(v<0?-v:v),q;
 if(delta>=7)q=mag?128:0;
 else if(delta>=0)q=mag<<(unsigned)delta;
 else if(delta<=-25)q=0;
 else{unsigned shift=(unsigned)-delta,mask=(1u<<shift)-1,half=1u<<(shift-1);q=mag>>shift;unsigned r=mag&mask;if(r>half || (r==half && (q&1)))q++;}
 unsigned limit=v<0?128u:127u;if(q>limit)q=limit;return (int8_t)(v<0?-(int)q:(int)q);
}
#ifdef XI8_TEST
int xi8_test_quant(int32_t v,int delta){return quant(v,delta);}
#endif
/* Explicit alias type permits aligned word loads from the S16 device shadow.
 * Unaligned addresses and non-little-endian hosts retain the scalar path. */
typedef uint32_t xi8_word __attribute__((__may_alias__));
static size_t narrow_s16_s8(int8_t *dst,const int16_t *src,size_t count){
 size_t words=0;
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
 if(!(((uintptr_t)src|(uintptr_t)dst)&3u)){
  xi8_word *d=(void *)dst;const xi8_word *s=(const void *)src;
  words=count/4;
  for(size_t i=0;i<words;i++){
   uint32_t a=s[i*2],b=s[i*2+1];
   d[i]=(a&0xffu)|((a>>8)&0xff00u)|((b<<16)&0xff0000u)|((b<<8)&0xff000000u);
  }
  src+=words*4;dst+=words*4;count-=words*4;
 }
#endif
 for(size_t i=0;i<count;i++)dst[i]=(int8_t)src[i];return words*4;
}
static void pack_input(uint8_t *dst,const xi8_tensor *src,unsigned width,unsigned height,int source_x,int source_y,int exponent,xi8_stats *stats){
 unsigned cp=align4(src->c);int delta=src->exponent-exponent;
 size_t rowbytes=(size_t)width*cp;
 for(unsigned y=0;y<height;y++){
  uint8_t *row=dst+(size_t)y*rowbytes;int iy=source_y+(int)y;
  int begin=source_x<0?-source_x:0,end=(int)src->w-source_x;
  if(end>(int)width)end=(int)width;
  if(iy<0 || iy>=(int)src->h || begin>=end){memset(row,0,rowbytes);stats->input_zero_bytes+=rowbytes;continue;}
  size_t prefix=(size_t)begin*cp,suffix=(size_t)(width-(unsigned)end)*cp;
  if(prefix)memset(row,0,prefix);if(suffix)memset(row+(size_t)end*cp,0,suffix);
  stats->input_zero_bytes+=prefix+suffix;
  size_t si=((size_t)(unsigned)iy*src->w+(unsigned)(source_x+begin))*src->pitch;
  uint8_t *d=row+prefix;size_t pixels=(size_t)(end-begin);
  if(src->bits==8 && delta==0 && src->pitch==cp){
   memcpy(d,(uint8_t *)src->data+si,pixels*cp);stats->copied_input_bytes+=pixels*cp;
  }else{
   /* Hoist the storage width test out of the element loop. */
#define PACK_TYPED(TYPE) do { const TYPE *s=(const TYPE *)src->data+si; \
    for(size_t x=0;x<pixels;x++,s+=src->pitch,d+=cp){ \
     for(unsigned c=0;c<src->c;c++)d[c]=(uint8_t)quant(s[c],delta); \
     if(cp>src->c)memset(d+src->c,0,cp-src->c); \
    } }while(0)
   if(src->bits==8)PACK_TYPED(int8_t);else if(src->bits==16)PACK_TYPED(int16_t);else PACK_TYPED(int32_t);
#undef PACK_TYPED
   stats->converted_input_values+=pixels*src->c;stats->input_zero_bytes+=pixels*(cp-src->c);
  }
 }
}
static int layout(struct pango_vision32_job *j,unsigned bytes,unsigned sizes[5]){
 unsigned k=j->cin*j->kernel*j->kernel,groups=(j->cout+7)/8;
 j->weights=align4(j->width*j->height*align4(j->cin));j->params=j->weights+groups*k*8;
 j->lut=j->flags==5?align4(j->params+groups*8*12):0;j->output=align4(j->params+groups*8*12)+(j->flags==5?65536:0);
 if(!pango_vision32_sizes(j,bytes,sizes))return 0;
 uint64_t ow=(j->width+2*j->padding-j->kernel)/j->stride+1,oh=(j->height+2*j->padding-j->kernel)/j->stride+1;
 return ow*oh*j->cout*(k+512u)<=UINT64_C(67108864);
}
static int convolution(const xi8_model *m,const int32_t *n,const xqm_transport *io,const xi8_tensor *src,xi8_tensor *out,xi8_stats *stats){
 struct pango_vision32_job j={0};unsigned sizes[5],tw=out->w,th=out->h;int rectangles=0;
 if(!io || !xqv_exact_available(io))return 0;
 j.abi_version=1;j.width=src->w;j.height=src->h;j.cin=src->c;j.cout=out->c;
 j.kernel=(unsigned)n[10];j.stride=(unsigned)n[12];j.padding=(unsigned)n[14];j.flags=n[24]?5u:4u;
 j.timeout_cycles=49500000;j.timeout_us=1000000;
 if(!layout(&j,(unsigned)io->bytes,sizes)){
  unsigned maxside=(640-j.kernel)/j.stride+1,lo=0,hi=th<maxside?th:maxside;tw=tw<maxside?tw:maxside;
  rectangles=1;j.padding=0;j.width=(tw-1)*j.stride+j.kernel;
  while(lo<hi){unsigned mid=lo+(hi-lo+1)/2;j.height=(mid-1)*j.stride+j.kernel;if(layout(&j,(unsigned)io->bytes,sizes))lo=mid;else hi=mid-1;}
  if(!lo)return 0;th=lo;j.height=(th-1)*j.stride+j.kernel;if(!layout(&j,(unsigned)io->bytes,sizes))return 0;
 }
 uint64_t stamp=xi8_now();
 memcpy(io->shadow+j.weights,m->blob+n[20],(size_t)n[29]);memcpy(io->shadow+j.params,m->blob+n[21],(size_t)n[30]);
 if(n[24])memcpy(io->shadow+j.lut,m->blob+n[23],(size_t)n[24]);
 xqv_parameters_begin(io,&j);stats->weight_ticks+=xi8_now()-stamp;
 for(unsigned ty=0;ty<out->h;ty+=th)for(unsigned tx=0;tx<out->w;tx+=tw){
  unsigned ny=out->h-ty<th?out->h-ty:th,nx=out->w-tx<tw?out->w-tx:tw;
  if(rectangles){j.width=(nx-1)*j.stride+j.kernel;j.height=(ny-1)*j.stride+j.kernel;}
  stamp=xi8_now();
  int source_x=rectangles?(int)(tx*j.stride)-(int)n[14]:0;
  int source_y=rectangles?(int)(ty*j.stride)-(int)n[14]:0;
  pack_input(io->shadow,src,j.width,j.height,source_x,source_y,n[18],stats);
  stats->pack_ticks+=xi8_now()-stamp;stamp=xi8_now();
  if(!xqv_run(io,&j))return 0;
  stats->ioctl_ticks+=xi8_now()-stamp;stats->jobs++;stats->cycles+=j.cycles;stamp=xi8_now();
  const int16_t *values=(const void *)(io->shadow+j.output);
  for(unsigned y=0;y<ny;y++){
   size_t di=((size_t)(ty+y)*out->w+tx)*out->c,si=(size_t)y*nx*out->c,count=(size_t)nx*out->c;
   if(out->bits==16)memcpy((int16_t *)out->data+di,values+si,count*2);
   else stats->output_word_values+=narrow_s16_s8((int8_t *)out->data+di,values+si,count);
   stats->output_bytes+=count*out->bits/8;
  }
  stats->output_ticks+=xi8_now()-stamp;
 }
 return 1;
}
/* Separable max5: vertical pass into the final output, then a five-register
 * horizontal window in place. No intermediate image or row buffer. */
#define DEFINE_POOL(NAME,TYPE,MINIMUM) \
static void NAME(const xi8_tensor *a,xi8_tensor *out){ \
 TYPE *dst=out->data;const TYPE *src=a->data;size_t row=(size_t)a->w*a->c; \
 for(unsigned y=0;y<a->h;y++){ \
  unsigned first=y>2?y-2:0,last=y+2<a->h?y+2:a->h-1;TYPE *d=dst+(size_t)y*row; \
  memcpy(d,src+(size_t)first*a->w*a->pitch,row*sizeof(TYPE)); \
  for(unsigned yy=first+1;yy<=last;yy++){const TYPE *s=src+(size_t)yy*a->w*a->pitch; \
   for(size_t i=0;i<row;i++)if(s[i]>d[i])d[i]=s[i]; \
  } \
 } \
 for(unsigned y=0;y<a->h;y++)for(unsigned q=0;q<a->c;q++){ \
  TYPE *d=dst+(size_t)y*row+q;int32_t v0=MINIMUM,v1=MINIMUM,v2=d[0]; \
  int32_t v3=a->w>1?d[a->c]:MINIMUM,v4=a->w>2?d[a->c*2]:MINIMUM; \
  for(unsigned x=0;x<a->w;x++){ \
   int32_t v=v0;if(v1>v)v=v1;if(v2>v)v=v2;if(v3>v)v=v3;if(v4>v)v=v4; \
   int32_t next=x+3<a->w?d[(size_t)(x+3)*a->c]:MINIMUM;d[(size_t)x*a->c]=(TYPE)v; \
   v0=v1;v1=v2;v2=v3;v3=v4;v4=next; \
  } \
 } \
}
DEFINE_POOL(pool8,int8_t,INT8_MIN)
DEFINE_POOL(pool16,int16_t,INT16_MIN)
DEFINE_POOL(pool32,int32_t,INT32_MIN)
#undef DEFINE_POOL
static int nonconv(const int32_t *n,xi8_tensor *values,xi8_tensor *out){
 xi8_tensor *a=&values[n[5]];size_t pixels=(size_t)out->h*out->w;unsigned c=out->c;
 if(n[0]==7){
  unsigned offset=0;
  for(unsigned j=0;j<(unsigned)n[4];j++){
   xi8_tensor *p=&values[n[5+j]];int shift=p->exponent-out->exponent;
   if(!p->data || p->h!=out->h || p->w!=out->w || offset+p->c>c || shift<0 || shift>30)return 0;
   if(p->bits==out->bits && shift==0){for(size_t z=0;z<pixels;z++)memcpy((uint8_t *)out->data+(z*c+offset)*out->bits/8,(uint8_t *)p->data+z*p->pitch*p->bits/8,p->c*p->bits/8);}
   else if(p->bits==8 && out->bits==16){
    const int8_t *src=p->data;int16_t *dst=(int16_t *)out->data+offset;int factor=1<<shift;
    for(size_t z=0;z<pixels;z++,src+=p->pitch,dst+=c)for(unsigned q=0;q<p->c;q++)dst[q]=(int16_t)(src[q]*factor);
   }else for(size_t z=0;z<pixels;z++)for(unsigned q=0;q<p->c;q++)put(out,z*c+offset+q,get(p,z*p->pitch+q)*(1<<shift));
   offset+=p->c;
  }
  return offset==c;
 }
 if(!a->data || a->c!=c)return 0;
 if(n[0]==8){
  xi8_tensor *b=&values[n[6]];int sa=a->exponent-out->exponent,sb=b->exponent-out->exponent;
  if(n[4]!=2 || !b->data || b->c!=c || a->h!=out->h || b->h!=out->h || a->w!=out->w || b->w!=out->w || sa<0 || sa>30 || sb<0 || sb>30)return 0;
  if(a->pitch==c && b->pitch==c && out->bits==16 && a->bits<=16 && b->bits<=16){
   int fa=1<<sa,fb=1<<sb;int16_t *d=out->data;size_t count=pixels*c;
#define ADD_TYPED(A,B) do {const A *pa=a->data;const B *pb=b->data; \
    if(!sa && !sb){for(size_t i=0;i<count;i++)d[i]=(int16_t)(pa[i]+pb[i]);} \
    else for(size_t i=0;i<count;i++)d[i]=(int16_t)(pa[i]*fa+pb[i]*fb); }while(0)
   if(a->bits==8){if(b->bits==8)ADD_TYPED(int8_t,int8_t);else ADD_TYPED(int8_t,int16_t);}
   else{if(b->bits==8)ADD_TYPED(int16_t,int8_t);else ADD_TYPED(int16_t,int16_t);}
#undef ADD_TYPED
  }else for(size_t z=0;z<pixels;z++)for(unsigned q=0;q<c;q++)put(out,z*c+q,get(a,z*a->pitch+q)*(1<<sa)+get(b,z*b->pitch+q)*(1<<sb));
 }else if(n[0]==4){
  if(n[10]!=5 || n[14]!=2 || a->h!=out->h || a->w!=out->w || a->exponent!=out->exponent)return 0;
  if(a->pitch==c && out->bits==a->bits){
   if(a->bits==8)pool8(a,out);else if(a->bits==16)pool16(a,out);else pool32(a,out);return 1;
  }
  for(unsigned y=0;y<out->h;y++)for(unsigned x=0;x<out->w;x++)for(unsigned q=0;q<c;q++){
   int32_t v=INT32_MIN;
   for(int yy=(int)y-2;yy<=(int)y+2;yy++)for(int xx=(int)x-2;xx<=(int)x+2;xx++)if(yy>=0 && xx>=0 && yy<(int)a->h && xx<(int)a->w){
    int32_t t=get(a,((size_t)(unsigned)yy*a->w+(unsigned)xx)*a->pitch+q);if(t>v)v=t;
   }
   put(out,((size_t)y*out->w+x)*c+q,v);
  }
 }else if(n[0]==5){
  if(out->h!=a->h*2 || out->w!=a->w*2 || out->bits!=a->bits || out->exponent!=a->exponent)return 0;
  unsigned bytes=c*out->bits/8;
  for(unsigned y=0;y<a->h;y++){
   uint8_t *row=(uint8_t *)out->data+(size_t)y*2*out->w*bytes;
   for(unsigned x=0;x<a->w;x++){const uint8_t *p=(const uint8_t *)a->data+((size_t)y*a->w+x)*a->pitch*a->bits/8;memcpy(row+(size_t)x*2*bytes,p,bytes);memcpy(row+((size_t)x*2+1)*bytes,p,bytes);}
   memcpy(row+(size_t)out->w*bytes,row,(size_t)out->w*bytes);
  }
 }else if(n[0]==10 || n[0]==11){
  if(a->h!=out->h || a->w!=out->w || a->exponent!=out->exponent)return 0;
  for(size_t z=0;z<pixels;z++)for(unsigned q=0;q<c;q++){int32_t v=get(a,z*a->pitch+q);put(out,z*c+q,n[0]==11 && v<0?0:v);}
 }else return 0;
 return 1;
}
int xi8_run(xi8_model *m,const xqm_transport *io,const xi8_tensor *input,xi8_stats *stats){
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
  if(n[0]==1){if(!convolution(m,n,io,n[5]<0?input:&values[n[5]],out,stats))goto done;}
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
size_t xi8_output_elements(const xi8_model *m,unsigned i){return !m || i>=3 || !m->outputs[i].data?0:(size_t)m->outputs[i].c*m->outputs[i].h*m->outputs[i].w;}
int xi8_export_f32(const xi8_model *m,unsigned i,void *destination,size_t capacity,unsigned dims[4]){
 size_t count=xi8_output_elements(m,i);if(!count || !destination || capacity<count*4)return 0;
 const xi8_tensor *t=&m->outputs[i];if(t->bits!=16)return 0;uint32_t *out=destination;size_t spatial=(size_t)t->h*t->w;
 for(unsigned c=0;c<t->c;c++)for(size_t p=0;p<spatial;p++){
  int32_t v=get(t,p*t->pitch+c);unsigned mag=(unsigned)(v<0?-v:v),bits=0;
  if(mag){unsigned top=31u-(unsigned)__builtin_clz(mag);int field=127+(int)top+t->exponent;if(field<=0 || field>=255)return 0;
   bits=((unsigned)field<<23)|((mag<<(23-top))&0x7fffffu);if(v<0)bits|=0x80000000u;
  }
  out[(size_t)c*spatial+p]=bits;
 }
 if(dims){dims[0]=1;dims[1]=t->c;dims[2]=t->h;dims[3]=t->w;}return 1;
}
