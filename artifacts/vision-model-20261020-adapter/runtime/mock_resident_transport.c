/* PC numerical test fixture, never linked into a native device worker. */
#include "xq_resident_matrix.h"
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
typedef struct {xqm_linux linux;struct pango_mac_model model;uint8_t *snapshot;unsigned regs,runs,restores;} fixture;
static fixture *slots[4],*physical_owner;static uint8_t physical[0x100000];
void *xqn_mock_open(void)
{
    unsigned i;for(i=0;i<4 && slots[i];i++);
    if(i==4)return NULL;
    fixture *f=calloc(1,sizeof(*f));if(!f)return NULL;
    f->linux.io.shadow=calloc(1,0x100000);f->snapshot=calloc(1,0x100000);
    if(!f->linux.io.shadow || !f->snapshot){free(f->linux.io.shadow);free(f->snapshot);free(f);return NULL;}
    f->linux.fd=(int)i+42;f->linux.io.context=&f->linux;f->linux.io.bytes=0x100000;slots[i]=f;return &f->linux.io;
}
void xqn_mock_close(void *transport)
{
    if(!transport)return;
    xqm_transport *t=transport;fixture *f=(fixture *)t->context;
    if(f->linux.resident_free)f->linux.resident_free(f->linux.resident_cache);
    if(physical_owner==f)physical_owner=NULL;
    slots[f->linux.fd-42]=NULL;free(t->shadow);free(f->snapshot);free(f);
}
void xqn_mock_counters(void *transport,unsigned *values)
{
    fixture *f=(fixture *)((xqm_transport *)transport)->context;
    values[0]=f->regs;values[1]=f->runs;values[2]=f->restores;
}
int __wrap_ioctl(int fd,unsigned long request,...)
{
    if(fd<42 || fd>=46 || !slots[fd-42])return -1;
    fixture *f=slots[fd-42];va_list ap;va_start(ap,request);void *arg=va_arg(ap,void *);va_end(ap);
    if(request==PANGO_MAC_IOC_REGISTER_MODEL) {
        struct pango_mac_model *m=arg;if(!pango_mac_model_valid(m,0x100000))return -1;
        f->model=*m;memcpy(f->snapshot+m->offset,f->linux.io.shadow+m->offset,m->bytes);
        physical_owner=NULL;f->regs++;return 0;
    }
    if(request!=PANGO_MAC_IOC_RUN_RESIDENT)return -1;
    struct pango_mac_job *j=arg;unsigned tiles=(j->cin+3)/4;
    if(tiles*((j->cout+31)/32)>64 || !j->zero_bias || j->output_format!=3 ||
       !pango_mac_resident_sources_valid(f->model.offset,f->model.bytes,j->weight_offset,((j->cout+31)/32)*tiles*128,0,0,j->input_offset,j->pixels*tiles*8,j->output_offset,j->pixels*j->cout*4))return -1;
    if(physical_owner!=f){memcpy(physical+f->model.offset,f->snapshot+f->model.offset,f->model.bytes);physical_owner=f;f->restores++;}
    for(unsigned p=0;p<j->pixels;p++)for(unsigned co=0;co<j->cout;co++) {
        int32_t sum=0;
        for(unsigned k=0;k<j->cin;k++) {
            int8_t a=(int8_t)f->linux.io.shadow[j->input_offset+(p*tiles+k/4)*8+(k%4)*2];
            unsigned at=j->weight_offset+(co/32*tiles+k/4)*128+(co%32/2*4+k%4)*2+co%2;
            sum+=(int32_t)a*(int8_t)physical[at];
        }
        memcpy(f->linux.io.shadow+j->output_offset+(p*j->cout+co)*4,&sum,4);
    }
    f->runs++;j->status=2;j->cycles=17;return 0;
}
