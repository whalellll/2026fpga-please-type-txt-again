#include GEOMETRY_SOURCE
#include <assert.h>
static int tracking,depth;
static size_t live_bytes,peak_bytes,total_bytes,first_bytes;
static unsigned allocations;
static struct {void *pointer;size_t bytes;} entries[32];
void *__real_malloc(size_t);
void *__real_calloc(size_t,size_t);
void __real_free(void *);
static void record(void *pointer,size_t bytes)
{
    if(!tracking)return;
    if(!allocations)first_bytes=bytes;
    ++allocations;total_bytes+=bytes;
    if(pointer){unsigned i=0;while(i<32 && entries[i].pointer)i++;assert(i<32);
        entries[i].pointer=pointer;entries[i].bytes=bytes;live_bytes+=bytes;
        if(live_bytes>peak_bytes)peak_bytes=live_bytes;}
}
void *__wrap_malloc(size_t bytes)
{void *p=__real_malloc(bytes);if(!depth)record(p,bytes);return p;}
void *__wrap_calloc(size_t n,size_t bytes)
{depth++;void *p=__real_calloc(n,bytes);depth--;record(p,n*bytes);return p;}
void __wrap_free(void *p)
{
    if(p)for(unsigned i=0;i<32;i++)if(entries[i].pointer==p){live_bytes-=entries[i].bytes;entries[i].pointer=NULL;break;}
    __real_free(p);
}
int main(int argc,char **argv)
{
    assert(argc==3);FILE *f=fopen(argv[1],"rb");assert(f);char magic[8];unsigned n;
    double coarse[4][2],corners[4][2]={{0}};xqr_box boxes[300];xnp_refinement stats={0};
    uint8_t (*rng)[240][4]=malloc(91u*240u*4u),*rgb=malloc(1280u*720u*3u);assert(rng && rgb);
    assert(fread(magic,1,8,f)==8 && !memcmp(magic,"XQGEOM1",8) && fread(&n,4,1,f)==1 && n<=300);
    assert(fread(coarse,8,8,f)==8 && fread(boxes,24,n,f)==n && fread(rng,1,91u*240u*4u,f)==91u*240u*4u &&
        fread(rgb,1,1280u*720u*3u,f)==1280u*720u*3u && fgetc(f)==EOF && !fclose(f));
    tracking=1;int okay=xnp_refine(rgb,coarse,boxes,n,rng,corners,&stats);tracking=0;assert(!live_bytes && !depth);
    f=fopen(argv[2],"wbx");assert(f && fwrite(&okay,4,1,f)==1 && fwrite(corners,8,8,f)==8 &&
        fwrite(&stats,sizeof(stats),1,f)==1 && !fclose(f));
    printf("GEOMETRY_FUSED_MEMORY allocations=%u total=%zu peak=%zu first=%zu live=%zu\n",
        allocations,total_bytes,peak_bytes,first_bytes,live_bytes);
    free(rgb);free(rng);return 0;
}
