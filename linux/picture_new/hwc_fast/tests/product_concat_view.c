#define _POSIX_C_SOURCE 200809L
#include <stddef.h>
static void stats_note(const void *,const void *);
static void allocation_note(unsigned);
#define XQIH_STATS_NOTE(stats,views) stats_note(stats,views)
#define XQIH_CONCAT_ALLOC_NOTE(node) allocation_note(node)
#include "../adapter.c"
#include <assert.h>
static xi8_stats captured;static xqih_concat_stats captured_views;
static unsigned fault_mode,fault_node,fault_fired,fail_malloc;static size_t fail_size;
static int cancel_now;
unsigned xqih_test_job_count(void);void xqih_test_fail_after(unsigned);
void *__real_malloc(size_t);void *__real_calloc(size_t,size_t);
void *__wrap_malloc(size_t n)
{
    if(fail_malloc){fail_malloc=0;return NULL;}
    if(fail_size==n){fail_size=0;return NULL;}
    return __real_malloc(n);
}
void *__wrap_calloc(size_t n,size_t z){return __real_calloc(n,z);}
static int cancellation(void *p){(void)p;return cancel_now;}
static void stats_note(const void *s,const void *v)
{captured=*(const xi8_stats *)s;captured_views=*(const xqih_concat_stats *)v;}
static void allocation_note(unsigned node)
{
    if(fault_mode && node==fault_node){
        fault_fired=1;
        if(fault_mode==1)fail_malloc=1;
        else if(fault_mode==2)xqih_test_fail_after(xqih_test_job_count());
        else cancel_now=1;
    }
}
static void invalid(float *heads[3],const xqm_stats *stats)
{xqm_stats zero={0};assert(!memcmp(stats,&zero,sizeof(zero)));for(unsigned i=0;i<3;i++)assert(!heads[i]);}
static void compare_file(const char *path,const xi8_model *m,float *heads[3])
{
    FILE *f=fopen(path,"rb");assert(f);
    for(unsigned i=0;i<3;i++){
        uint32_t dims[4],expected[4]={1,m->outputs[i].c,m->outputs[i].h,m->outputs[i].w};
        assert(fread(dims,4,4,f)==4 && !memcmp(dims,expected,sizeof(dims)));
        size_t count=xi8_output_elements(m,i);float buf[256];
        for(size_t at=0;at<count;at+=256){size_t n=count-at<256?count-at:256;
            assert(fread(buf,4,n,f)==n && !memcmp(buf,heads[i]+at,n*4));}
    }
    assert(fgetc(f)==EOF && !fclose(f));
}
int main(int argc,char **argv)
{
    assert(argc==4 || argc==5);static const uint32_t header[10]={1,1,85,3,82,83,84,0x54f550,0x551fd0,0x3c17991f};
    xi8_model *m=xqih_open(argv[1],header);assert(m);
    float *input=malloc(3u*640u*640u*4u),*heads[3]={0};assert(input);
    FILE *f=fopen(argv[2],"rb");assert(f && fread(input,4,3u*640u*640u,f)==3u*640u*640u && fgetc(f)==EOF && !fclose(f));
    xqm_linux device;assert(xqm_linux_open(&device));device.io.cancelled=cancellation;xqm_stats stats;
    assert(xqih_detect(m,&device.io,input,heads,&stats) && stats.jobs==152);
    assert(captured_views.nodes==9 && captured_views.elided_bytes==4300800);
    assert(captured.allocated_tensor_bytes==16727200 && captured.reused_tensor_bytes==819200);
    assert(captured.peak_tensor_bytes<=2867200);
    printf("CONCAT_VIEW_GRAPH_COST nodes=%llu elided=%llu allocated=%llu peak=%llu jobs=%llu\n",
        (unsigned long long)captured_views.nodes,(unsigned long long)captured_views.elided_bytes,
        (unsigned long long)captured.allocated_tensor_bytes,(unsigned long long)captured.peak_tensor_bytes,(unsigned long long)stats.jobs);
    f=fopen(argv[3],"wbx");assert(f);
    for(unsigned i=0;i<3;i++){
        uint32_t dims[4]={1,m->outputs[i].c,m->outputs[i].h,m->outputs[i].w};size_t count=xi8_output_elements(m,i);
        assert(fwrite(dims,4,4,f)==4 && fwrite(heads[i],4,count,f)==count);
    }
    assert(!fclose(f));
    if(argc==5){
        const unsigned targets[]={7,46,80};
        for(unsigned i=0;i<3;i++){
            fault_mode=1;fault_node=targets[i];fault_fired=0;
            assert(!xqih_detect(m,&device.io,input,heads,&stats));invalid(heads,&stats);assert(fault_fired && !fail_malloc);
        }
        for(unsigned mode=2;mode<=3;mode++){
            fault_mode=mode;fault_node=7;fault_fired=0;
            assert(!xqih_detect(m,&device.io,input,heads,&stats));invalid(heads,&stats);assert(fault_fired);
            xqih_test_fail_after(0);cancel_now=0;
        }
        fault_mode=0;fail_size=57u*80u*80u*4u;unsigned before=xqih_test_job_count();
        assert(!xqih_detect(m,&device.io,input,heads,&stats));invalid(heads,&stats);
        assert(!fail_size && xqih_test_job_count()==before+152);
        assert(xqih_detect(m,&device.io,input,heads,&stats) && stats.jobs==152);compare_file(argv[3],m,heads);
        puts("CONCAT_VIEW_FUSED_PARENT_LIFETIME_OOM_IO_CANCEL_HEAD_FAILURE_RECOVERY_PASS");
    }
    for(unsigned i=0;i<3;i++)free(heads[i]);
    xqih_close(m);xqm_linux_close(&device);free(input);
    puts("CONCAT_VIEW_FULL_FROZEN_HEADS_9_NODES_4300800_BYTES_ELIDED_NOT_BOARD");return 0;
}
