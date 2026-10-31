#ifndef XQIH_EXPORT_TILE_H
#define XQIH_EXPORT_TILE_H
#include <stdint.h>
#include <string.h>

#ifndef XQIH_EXPORT_NOTE
#define XQIH_EXPORT_NOTE(fast) ((void)0)
#endif

/* Only trusted, complete frozen heads take the reordered path. The exponent
 * interval guarantees every nonzero S16 yields a normal finite FP32 value,
 * so no error can occur halfway through the reordered writes. */
static int xqih_export_tile_eligible(const xi8_tensor *t,const void *destination,size_t count)
{
    if(t->bits!=16 || t->c!=57 || t->pitch!=57 || t->h!=t->w ||
       (t->h!=80 && t->h!=40 && t->h!=20) || t->exponent< -126 || t->exponent>112)return 0;
    uintptr_t input=(uintptr_t)t->data,output=(uintptr_t)destination;
    size_t input_bytes=count*sizeof(int16_t),output_bytes=count*sizeof(uint32_t);
    if((input&1u) || (output&3u) || input>UINTPTR_MAX-input_bytes ||
       output>UINTPTR_MAX-output_bytes ||
       (input<output+output_bytes && output<input+input_bytes))return 0;
    return 1;
}

static int xqih_export_f32_tiled(const xi8_model *model,unsigned index,void *destination,
                                size_t capacity,unsigned dims[4])
{
    size_t count=xi8_output_elements(model,index);
    if(!count || !destination || capacity<count*4) {
        XQIH_EXPORT_NOTE(0);
        return xi8_export_f32(model,index,destination,capacity,dims);
    }
    const xi8_tensor *t=&model->outputs[index];
    if(!xqih_export_tile_eligible(t,destination,count)) {
        XQIH_EXPORT_NOTE(0);
        return xi8_export_f32(model,index,destination,capacity,dims);
    }
    XQIH_EXPORT_NOTE(1);
    uint32_t tile[8][16],*out=destination;
    const int16_t *input=t->data;
    size_t spatial=(size_t)t->h*t->w;
    for(size_t first=0;first<spatial;first+=16)for(unsigned base=0;base<57;base+=8) {
        unsigned channels=57-base<8?57-base:8;
        for(unsigned p=0;p<16;p++)for(unsigned c=0;c<channels;c++) {
            int32_t v=input[(first+p)*57+base+c];
            unsigned mag=(unsigned)(v<0?-v:v),bits=0;
            if(mag) {
                unsigned top=31u-(unsigned)__builtin_clz(mag);
                int field=127+(int)top+t->exponent;
                bits=((unsigned)field<<23)|((mag<<(23-top))&0x7fffffu);
                if(v<0)bits|=0x80000000u;
            }
            tile[c][p]=bits;
        }
        for(unsigned c=0;c<channels;c++)
            memcpy(out+(size_t)(base+c)*spatial+first,tile[c],16*sizeof(uint32_t));
    }
    if(dims){dims[0]=1;dims[1]=t->c;dims[2]=t->h;dims[3]=t->w;}
    return 1;
}
#endif
