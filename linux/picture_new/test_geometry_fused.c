/* Compare all three fused consumer arrays with the unchanged box-sum path. */
#include GEOMETRY_SOURCE
#include <assert.h>
#if defined(XQ_GEOMETRY_CANCEL) && XQ_GEOMETRY_CANCEL
#define SELECTED(...) box_sum_selected(__VA_ARGS__,NULL)
#define FUSED(...) box_sum_fused(__VA_ARGS__,NULL)
#else
#define SELECTED(...) box_sum_selected(__VA_ARGS__)
#define FUSED(...) box_sum_fused(__VA_ARGS__)
#endif
static uint32_t random_state=0xb4317692u;
static uint32_t next_word(void)
{random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;return random_state;}
static void one(unsigned width,unsigned height,unsigned pattern)
{
    size_t n=(size_t)width*height;
    double *a=malloc(n*8),*b=malloc(n*8),*tmp=malloc(n*8),*sa=malloc(n*8),*sb=malloc(n*8);
    uint8_t *mask=malloc(n);uint16_t *counts=malloc(n*2);
    assert(a && b && tmp && sa && sb && mask && counts);
    for(size_t i=0;i<n;i++){
        a[i]=b[i]=(next_word()%256)*.299+(next_word()%256)*.587+(next_word()%256)*.114;
        mask[i]=pattern==0?0:pattern==1?1:(i%width>width/4 && i%width<3*width/4 && i/width>height/4 && i/width<3*height/4)?0:1;
    }
    assert(SELECTED(a,15,15,tmp,width,height,NULL,mask,NULL));
    for(size_t i=0;i<n;i++){
        if(mask[i]==0){a[i]=0;continue;}
        double contrast=xqgeom_div(tmp[i],961)-a[i]-5;
        a[i]=contrast<=0?0:contrast>=60?1:xqgeom_div(contrast,60);
    }
    assert(FUSED(b,15,15,b,width,height,NULL,mask,NULL,1));
    assert(!memcmp(a,b,n*8));
    assert(xqgeom_mask8_sum(mask,1,13,counts,width,height));
    assert(SELECTED(a,1,13,tmp,width,height,counts,NULL,NULL));
    for(size_t i=0;i<n;i++)sa[i]=counts[i]<48?-1:xqgeom_div(tmp[i],(unsigned)counts[i]);
    assert(FUSED(b,1,13,sb,width,height,counts,NULL,NULL,2));
    assert(!memcmp(sa,sb,n*8));
    assert(xqgeom_mask8_sum(mask,13,1,counts,width,height));
    assert(SELECTED(a,13,1,tmp,width,height,counts,mask,sa));
    for(size_t i=0;i<n;i++)sa[i]=sa[i]<0 || counts[i]<48 || mask[i]<.5?0:fmin(sa[i],xqgeom_div(tmp[i],(unsigned)counts[i]));
    assert(FUSED(b,13,1,sb,width,height,counts,mask,sb,3));
    assert(!memcmp(sa,sb,n*8));
    free(a);free(b);free(tmp);free(sa);free(sb);free(mask);free(counts);
}
int main(void)
{
    const unsigned shapes[][2]={{1,1},{2,3},{31,17},{320,192},{607,473},{1280,720}};
    for(unsigned i=0;i<sizeof(shapes)/sizeof(*shapes);i++)for(unsigned pattern=0;pattern<3;pattern++)
        one(shapes[i][0],shapes[i][1],pattern);
    puts("GEOMETRY_FUSED_18_SHAPES_MASKS_ALL_THREE_ARRAYS_ALIAS_EXACT_PASS_NOT_BOARD");
    return 0;
}
