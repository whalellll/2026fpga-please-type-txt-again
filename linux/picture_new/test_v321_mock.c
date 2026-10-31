#include "test_v321_mock.h"
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>

static xqm_linux *active;
static v321_mock_counts counts;
int v321_mock_open(xqm_linux *c)
{
    if(!c || active)return 0;
    memset(c,0,sizeof(*c));c->fd=71;
    c->io.shadow=calloc(1,0x100000);if(!c->io.shadow)return 0;
    c->io.bytes=0x100000;c->io.context=c;
    c->features=PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED|PANGO_MAC_FEATURE_VISION32;
    active=c;v321_mock_reset(0);return 1;
}
void v321_mock_close(xqm_linux *c)
{
    if(c && c==active){free(c->io.shadow);memset(c,0,sizeof(*c));c->fd=-1;active=NULL;}
}
void v321_mock_reset(uint64_t fail_at){memset(&counts,0,sizeof(counts));counts.fail_at=fail_at;}
void v321_mock_read(v321_mock_counts *out){if(out)*out=counts;}
int __wrap_ioctl(int fd,unsigned long request,...)
{
    va_list ap;va_start(ap,request);struct pango_vision32_job *j=va_arg(ap,void *);va_end(ap);
    unsigned sizes[5];
    counts.attempts++;
    if(!active || fd!=active->fd || request!=PANGO_MAC_IOC_RUN_VISION32){
        counts.unexpected++;errno=ENOTTY;return -1;
    }
    if(!j || j->flags!=2 || !pango_vision32_sizes(j,(uint32_t)active->io.bytes,sizes)){
        counts.errors++;errno=EINVAL;return -1;
    }
    if(counts.fail_at && counts.attempts==counts.fail_at){counts.errors++;errno=ETIMEDOUT;return -1;}
    unsigned ow=(j->width+2*j->padding-j->kernel)/j->stride+1;
    unsigned oh=(j->height+2*j->padding-j->kernel)/j->stride+1;
    unsigned ci4=(j->cin+3)&~3u,k=j->cin*j->kernel*j->kernel,groups=(j->cout+7)/8;
    const int8_t *input=(const int8_t *)active->io.shadow+j->input;
    const int8_t *weights=(const int8_t *)active->io.shadow+j->weights;
    int8_t patch[1152];
    for(unsigned y=0;y<oh;y++)for(unsigned x=0;x<ow;x++){
        unsigned at=0;
        for(unsigned ky=0;ky<j->kernel;ky++)for(unsigned kx=0;kx<j->kernel;kx++){
            int iy=(int)(y*j->stride+ky)-(int)j->padding;
            int ix=(int)(x*j->stride+kx)-(int)j->padding;
            if(iy<0 || ix<0 || iy>=(int)j->height || ix>=(int)j->width){
                memset(patch+at,0,j->cin);at+=j->cin;
            } else {memcpy(patch+at,input+((size_t)iy*j->width+(unsigned)ix)*ci4,j->cin);at+=j->cin;}
        }
        assert(at==k);
        for(unsigned g=0;g<groups;g++){
            int32_t sums[8]={0};const int8_t *w=weights+(size_t)g*k*8;
            for(unsigned q=0;q<k;q++,w+=8){
                int32_t v=patch[q];
                sums[0]+=v*w[0];sums[1]+=v*w[1];sums[2]+=v*w[2];sums[3]+=v*w[3];
                sums[4]+=v*w[4];sums[5]+=v*w[5];sums[6]+=v*w[6];sums[7]+=v*w[7];
            }
            unsigned n=j->cout-g*8;if(n>8)n=8;
            memcpy(active->io.shadow+j->output+4*(((size_t)y*ow+x)*j->cout+g*8),sums,n*4);
        }
    }
    j->status=2;j->error=0;
    j->cycles=k*groups*((ow*oh+3)/4);j->mac_cycles=j->cycles;
    j->read_bytes=sizes[0]+sizes[1];j->write_bytes=sizes[2];
    counts.jobs++;counts.cycles+=j->cycles;return 0;
}
