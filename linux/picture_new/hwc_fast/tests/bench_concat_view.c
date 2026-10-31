/* Offline packing/coordinator CPU clue. Device calls are deliberately mocked.
 * Allocations are outside the measured windows; no board cache claim. */
#define _POSIX_C_SOURCE 200809L
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wmisleading-indentation"
#include "../integer_hwc.c"
#pragma GCC diagnostic pop
#include "../concat_view.h"
#include <assert.h>
static unsigned observe,job_at,jobs;
static uint8_t *packets[256];static size_t lengths[256];
int xqv_exact_available(const xqm_transport *io){(void)io;return 1;}
void xqv_parameters_begin(const xqm_transport *io,struct pango_vision32_job *j){(void)io;(void)j;}
int xqv_run(const xqm_transport *io,struct pango_vision32_job *j)
{
    size_t bytes=(size_t)j->width*j->height*align4(j->cin);
    if(observe==1){assert(job_at<256);packets[job_at]=malloc(bytes);assert(packets[job_at]);memcpy(packets[job_at],io->shadow,bytes);lengths[job_at]=bytes;}
    if(observe==2)assert(job_at<jobs && bytes==lengths[job_at] && !memcmp(packets[job_at],io->shadow,bytes));
    job_at++;unsigned w=(j->width+2*j->padding-j->kernel)/j->stride+1,h=(j->height+2*j->padding-j->kernel)/j->stride+1;
    memset(io->shadow+j->output,0,(size_t)w*h*j->cout*2);j->cycles=0;return 1;
}
static uint64_t cpu_now(void){struct timespec t;assert(!clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t));return (uint64_t)t.tv_sec*1000000000u+t.tv_nsec;}
typedef struct {xi8_tensor values[200],joined,output;xqih_concat_view view;unsigned node;} fixture;
static fixture fixtures[9];
static uint64_t trial(xi8_model *m,const xqm_transport *io,unsigned fused)
{
    job_at=0;uint64_t start=cpu_now();
    for(unsigned k=0;k<9;k++){
        fixture *f=fixtures+k;xi8_stats stats={0};const int32_t *n=m->n[f->node];
        if(fused)assert(xqih_convolution_view(m,n+32,io,&f->view.joined,&f->output,&stats,&f->view));
        else{assert(nonconv(n,f->values,&f->joined));assert(convolution(m,n+32,io,&f->joined,&f->output,&stats));}
    }
    return cpu_now()-start;
}
int main(int argc,char **argv)
{
    (void)xqih_run_concat;assert(argc==2);xi8_model *m=xi8_load(argv[1]);assert(m);unsigned count=0;
    for(unsigned i=0;i+1<m->h[2];i++){
        const int32_t *n=m->n[i];if(n[0]!=7 || n[26]!=1 || m->n[i+1][0]!=1 || m->n[i+1][5]!=(int)i)continue;
        assert(count<9);fixture *f=fixtures+count++;f->node=i;
        for(unsigned k=0;k<(unsigned)n[4];k++){
            unsigned p=(unsigned)n[5+k];xi8_tensor *v=f->values+p;xqih_concat_shape(v,m->n[p]);
            size_t elements=(size_t)v->c*v->h*v->w;v->data=malloc(elements*v->bits/8);assert(v->data);
            for(size_t at=0;at<elements;at++)put(v,at,(int16_t)(at*509+k*73+i));
        }
        assert(xqih_concat_plan(m,i,f->values,&f->view));xqih_concat_shape(&f->joined,n);xqih_concat_shape(&f->output,m->n[i+1]);
        f->joined.data=malloc(elements(n)*f->joined.bits/8);f->output.data=malloc(elements(m->n[i+1])*f->output.bits/8);
        assert(f->joined.data && f->output.data);
    }
    assert(count==9);xqm_transport io={0};io.bytes=0x100000;io.shadow=calloc(1,io.bytes);assert(io.shadow);
    observe=1;trial(m,&io,0);jobs=job_at;observe=2;trial(m,&io,1);assert(job_at==jobs);
    observe=0;trial(m,&io,0);trial(m,&io,1);
    uint64_t total[2]={0};
    for(unsigned r=0;r<4;r++)for(unsigned k=0;k<2;k++){
        unsigned fused=k^(r&1u);uint64_t ns=trial(m,&io,fused);assert(job_at==jobs);total[fused]+=ns;
        printf("CONCAT_CPU_PAIR round=%u view=%u ns=%llu\n",r,fused,(unsigned long long)ns);
    }
    observe=2;trial(m,&io,0);trial(m,&io,1);
    for(unsigned j=0;j<jobs;j++)free(packets[j]);
    free(io.shadow);
    for(unsigned k=0;k<9;k++){
        fixture *f=fixtures+k;for(unsigned p=0;p<200;p++)xi8_tensor_free(f->values+p);
        xi8_tensor_free(&f->joined);xi8_tensor_free(&f->output);
    }
    xi8_free(m);printf("CONCAT_CPU_CLUE_PASS jobs=%u original_ns=%llu view_ns=%llu NOT_BOARD\n",jobs,(unsigned long long)total[0],(unsigned long long)total[1]);return 0;
}
