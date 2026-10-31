/* Normal-RAM commands built once from the immutable canonical page runs.
 * No framebuffer/model access. Allocation failure keeps the original merge. */
#ifndef XINYI_PAIR_CACHE_H
#define XINYI_PAIR_CACHE_H
#include <stdlib.h>
static const uint32_t *xy16_pairs[16];
static int xy16_pairs_initialized;
#if XINYI_GUI_METRIC_DELTAS
typedef struct {const xy15_run *run;unsigned word;} xy19_row_index;
static xy19_row_index xy19_rows[4][1080];
#endif
#ifdef XINYI_PAIR_CACHE_TEST_STATS
static unsigned xy16_pair_cache_hits;
#endif
typedef struct {
    uint32_t *data;
    size_t used,capacity,header;
    unsigned end,kind,value;
} xy16_writer;
static int xy16_emit(xy16_writer *w,unsigned offset,unsigned count,uint32_t value)
{
    if(w->kind==2 && w->end==offset && w->value==value){
        w->data[w->header]+=count;w->end+=count;return 1;
    }
    if(count>=4){
        if(w->capacity-w->used<3)return 0;
        w->data[w->used++]=offset;w->header=w->used;
        w->data[w->used++]=0x80000000u|count;w->data[w->used++]=value;
        w->kind=2;w->value=value;
    }else{
        if(w->kind!=1 || w->end!=offset || w->data[w->header]+count>1024){
            if(w->capacity-w->used<2u+count)return 0;
            w->data[w->used++]=offset;w->header=w->used;w->data[w->used++]=0;
        }else if(w->capacity-w->used<count)return 0;
        w->data[w->header]+=count;
        for(unsigned i=0;i<count;i++)w->data[w->used++]=value;
        w->kind=1;
    }
    w->end=offset+count;return 1;
}
static void xy16_pair_prepare(void)
{
    if(xy16_pairs_initialized)return;
    xy16_pairs_initialized=1;
#if XINYI_GUI_METRIC_DELTAS
    for(unsigned key=0;key<4;key++)if(key!=1){
        const xy15_run *run=xy15_pages[key];unsigned word=0;
        for(unsigned row=0;row<1080;row++){
            while(word+run->count<=row*960u){word+=run->count;run++;}
            xy19_rows[key][row]=(xy19_row_index){run,word};
        }
    }
#endif
    static const size_t run_counts[4]={sizeof(xy15_page_0)/sizeof(xy15_run),
        sizeof(xy15_page_1)/sizeof(xy15_run),sizeof(xy15_page_2)/sizeof(xy15_run),
        sizeof(xy15_page_3)/sizeof(xy15_run)};
    for(unsigned source=0;source<(XINYI_GUI_METRIC_DELTAS?4u:1u);source++)
    for(unsigned target=XINYI_GUI_METRIC_DELTAS?0u:2u;target<4;target++){
        if(source==1 || target==1 || source==target)continue;
        /* Each merged span needs at most five words (two header + three
         * literals). Merged spans <= sum of both immutable run counts. */
        size_t capacity=6u*(run_counts[source]+run_counts[target])+1u;
#ifdef XINYI_PAIR_CACHE_FORCE_OOM
        uint32_t *data=NULL;
#else
        uint32_t *data=malloc(capacity*sizeof(*data));
#endif
        if(!data)continue;
        xy16_writer writer={.data=data,.capacity=capacity};
        const xy15_run *old=xy15_pages[source],*next=xy15_pages[target];
        unsigned at=0,left=next->count,old_left=old->count;int okay=1;
        while(at<VIDEO_FB_FRAME_BYTES/4){
            unsigned count=left<old_left?left:old_left;
            if(next->value!=old->value && !xy16_emit(&writer,at,count,next->value)){okay=0;break;}
            at+=count;left-=count;old_left-=count;
            if(!left && at<VIDEO_FB_FRAME_BYTES/4){next++;left=next->count;}
            if(!old_left && at<VIDEO_FB_FRAME_BYTES/4){old++;old_left=old->count;}
        }
        if(!okay || writer.used>=capacity){free(data);continue;}
        data[writer.used++]=UINT32_MAX;
        uint32_t *smaller=realloc(data,writer.used*sizeof(*data));
        xy16_pairs[source*4u+target]=smaller?smaller:data;
    }
}
#endif
