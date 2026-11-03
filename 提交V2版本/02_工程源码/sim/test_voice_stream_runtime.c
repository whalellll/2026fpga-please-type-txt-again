#include "xqvoice_accel.h"
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
static int8_t expected[40];
int __wrap_ioctl(int fd,unsigned long request,...){
    va_list args;struct pango_voice_infer *job;
    assert(fd==71 && request==PANGO_VOICE_IOC_INFER);
    va_start(args,request);job=va_arg(args,struct pango_voice_infer*);va_end(args);
    assert(!memcmp(expected,job->input,40));job->token=7;job->confidence=321;return 0;
}
int main(void){
    xqvoice_accel_t a;struct pango_voice_stream packet;int8_t values[4000];
    uint32_t seq;unsigned i,bin;size_t frames;uint8_t token;uint16_t confidence;
    memset(&a,0,sizeof(a));a.fd=71;
    for(seq=0;seq<500;seq++){
        memset(&packet,0,sizeof(packet));packet.feature_count=1;
        packet.frames[0].end_sample=400+seq*160;packet.frames[0].sequence=seq;
        for(bin=0;bin<20;bin++)packet.frames[0].values[bin]=(int8_t)((seq*11+bin*7)%256-128);
        assert(xqvoice_accel_accept(&a,&packet));
    }
    frames=xqvoice_accel_features(&a,300*160,500*160,values,sizeof(values));assert(frames==198);
    for(bin=0;bin<20;bin++){
        int sum=0,maximum=-128;
        for(i=0;i<frames;i++){int v=(int8_t)(((300+i)*11+bin*7)%256-128);assert(values[i*20+bin]==v);sum+=v;if(v>maximum)maximum=v;}
        expected[bin]=(int8_t)(sum/(int)frames);expected[20+bin]=(int8_t)maximum;
    }
    assert(xqvoice_accel_infer(&a,values,frames,&token,&confidence));assert(token==7 && confidence==321);
    assert(!xqvoice_accel_features(&a,0,1600,values,sizeof(values)));
    assert(!xqvoice_accel_features(&a,1,1600,values,sizeof(values)));
    packet.frames[0].end_sample+=320;packet.frames[0].sequence+=2;
    assert(xqvoice_accel_accept(&a,&packet));assert(a.discontinuities==1);
    assert(!xqvoice_accel_features(&a,400*160,503*160,values,sizeof(values)));
    packet.frames[0].end_sample=1;assert(!xqvoice_accel_accept(&a,&packet));
    puts("VOICE_STREAM_RUNTIME_RING_WRAP_EXACT_POOLING_TIMESTAMP_AND_GAP_PASS");
}
