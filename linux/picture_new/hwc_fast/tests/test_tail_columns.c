#define _POSIX_C_SOURCE 200809L
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wmisleading-indentation"
#include "../integer_hwc.c"
#pragma GCC diagnostic pop
#include "../tail_columns.h"
#include <assert.h>
static unsigned jobs,variant,fail_after,cancel_after,leases,expected_bits;
static unsigned offsets[3],lengths[3];static uint8_t parameters[70000],coverage[320*320];
static int8_t pixel(unsigned x,unsigned y,unsigned c)
{return (int8_t)((x*17+y*31+c*47)%256-128);}
static int16_t result(unsigned x,unsigned y,unsigned c)
{return (int16_t)((x*13+y*37+c*7)%255-128);}
static int cancel(void *context){(void)context;return cancel_after && jobs>=cancel_after;}
int xqv_exact_available(const xqm_transport *io){return io!=NULL;}
void xqv_parameters_begin(const xqm_transport *io,struct pango_vision32_job *j)
{
    unsigned sizes[5];assert(pango_vision32_sizes(j,(unsigned)io->bytes,sizes));
    assert(++leases==1);offsets[0]=j->weights;offsets[1]=j->params;offsets[2]=j->lut;
    lengths[0]=sizes[1];lengths[1]=sizes[3];lengths[2]=sizes[4];
    unsigned at=0;for(unsigned i=0;i<3;i++){memcpy(parameters+at,io->shadow+offsets[i],lengths[i]);at+=lengths[i];}
    assert(at<=sizeof(parameters));j->model_generation=123;j->reserved[0]=PANGO_VISION32_REUSE_PARAMS;
}
int xqv_run(const xqm_transport *io,struct pango_vision32_job *j)
{
    if((fail_after && jobs>=fail_after) || (io->cancelled && io->cancelled(io->context)))return 0;
    unsigned sizes[5];assert(pango_vision32_sizes(j,(unsigned)io->bytes,sizes));
    assert(j->model_generation==123 && j->reserved[0]==PANGO_VISION32_REUSE_PARAMS);
    unsigned positions[3]={j->weights,j->params,j->lut},at=0;
    assert(!memcmp(positions,offsets,sizeof(offsets)));
    for(unsigned i=0;i<3;i++){assert(!memcmp(parameters+at,io->shadow+offsets[i],lengths[i]));at+=lengths[i];}
    unsigned tx,ty,nx,ny;
    if(!variant){tx=jobs%2?318:0;ty=(jobs/2)*21;nx=tx?2:318;ny=320-ty<21?320-ty:21;}
    else if(jobs<16){tx=0;ty=jobs*21;nx=318;ny=320-ty<21?320-ty:21;}
    else{assert(jobs<18);tx=318;ty=(jobs-16)*318;nx=2;ny=320-ty<318?320-ty:318;}
    assert(j->width==(nx-1)*2+6 && j->height==(ny-1)*2+6 && !j->padding);
    assert(sizes[0]<=offsets[0] && (uint64_t)nx*ny*16*(108+512)<=67108864);
    for(unsigned y=0;y<j->height;y++)for(unsigned x=0;x<j->width;x++)for(unsigned c=0;c<4;c++){
        int sx=(int)(tx*2+x)-2,sy=(int)(ty*2+y)-2;
        int8_t expected=(c==3 || sx<0 || sy<0 || sx>=640 || sy>=640)?0:pixel((unsigned)sx,(unsigned)sy,c);
        assert(((const int8_t *)io->shadow)[((size_t)y*j->width+x)*4+c]==expected);
    }
    int16_t *out=(void *)(io->shadow+j->output);
    for(unsigned y=0;y<ny;y++)for(unsigned x=0;x<nx;x++){
        assert(!coverage[(ty+y)*320+tx+x]++);
        for(unsigned c=0;c<16;c++)out[((size_t)y*nx+x)*16+c]=result(tx+x,ty+y,c);
    }
    jobs++;j->cycles=0;return 1;
}
static void trial(unsigned selected,unsigned bits,unsigned stop,unsigned failure)
{
    xi8_model model={0};int32_t n[32]={0};xi8_stats stats={0};
    xi8_tensor input={.c=3,.w=640,.h=640,.pitch=4,.bits=8},out={.c=16,.w=320,.h=320,.pitch=16,.bits=bits};
    xqm_transport io={0};io.bytes=0x100000;io.shadow=malloc(io.bytes);assert(io.shadow);memset(io.shadow,0xcd,io.bytes);io.cancelled=cancel;
    size_t bytes=320u*320u*16u*bits/8;uint8_t *guard=malloc(bytes+128);assert(guard);memset(guard,0x5a,bytes+128);out.data=guard+64;
    input.data=malloc(640u*640u*4u);model.blob=malloc(70000);assert(input.data && model.blob);
    for(unsigned y=0;y<640;y++)for(unsigned x=0;x<640;x++)for(unsigned c=0;c<4;c++)((int8_t *)input.data)[((size_t)y*640+x)*4+c]=c==3?0:pixel(x,y,c);
    for(unsigned i=0;i<70000;i++)model.blob[i]=(uint8_t)(i*29+7);
    n[5]=-1;n[10]=6;n[12]=2;n[14]=2;n[21]=1728;n[23]=1920;n[24]=bits==8?65536:0;n[29]=1728;n[30]=192;
    jobs=leases=0;variant=selected;fail_after=failure;cancel_after=stop;expected_bits=bits;memset(coverage,0,sizeof(coverage));
    struct pango_vision32_job j;unsigned sizes[5],tw=0,th=0,tail=0;
    assert(xqih_tail_plan(n,&io,&input,&out,&j,sizes,&tw,&th,&tail)==1);
    assert(tw==318 && th==21 && tail==318);
    assert(xqih_tail_fits(&j,2,318,(unsigned)io.bytes,sizes));
    assert(!xqih_tail_fits(&j,2,319,(unsigned)io.bytes,sizes));
    assert(!xqih_tail_fits(&j,318,22,(unsigned)io.bytes,sizes));
    int okay=selected?xqih_convolution_tail(&model,n,&io,&input,&out,&stats):convolution(&model,n,&io,&input,&out,&stats);
    if(stop || failure){assert(!okay && jobs==(stop?stop:failure));}
    else{
        assert(okay && jobs==(selected?18u:32u) && stats.jobs==jobs);
        for(unsigned y=0;y<320;y++)for(unsigned x=0;x<320;x++){
            assert(coverage[y*320+x]==1);
            for(unsigned c=0;c<16;c++)assert(get(&out,((size_t)y*320+x)*16+c)==result(x,y,c));
        }
    }
    for(unsigned i=0;i<64;i++)assert(guard[i]==0x5a && guard[bytes+64+i]==0x5a);
    free(input.data);free(model.blob);free(guard);free(io.shadow);
}
int main(void)
{
    assert(!xqih_run_tail(NULL,NULL,NULL,NULL));
    for(unsigned bits=8;bits<=16;bits+=8){trial(0,bits,0,0);trial(1,bits,0,0);}
    for(unsigned cut=15;cut<=17;cut++){trial(1,8,cut,0);trial(1,8,0,cut);}
    trial(1,8,0,0);
    puts("HWC_TAIL_32_TO_18_COVERAGE_HALO_BYTES_PARAMETER_LEASE_S8_S16_CANCEL_IO_RECOVERY_PASS_NOT_BOARD");return 0;
}
