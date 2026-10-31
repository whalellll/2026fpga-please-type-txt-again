/* Fixed-point CTC prefix beam, 4 slots, no command phrase whitelist. */
#include "xqvoice_decode.h"
#include "xqvoice_tables.h"
#include <stdlib.h>
#include <string.h>
#include <limits.h>

#define NEG INT32_MIN
#define CAP 512u
#ifndef XQV_CTC_BEAM
#define XQV_CTC_BEAM 4u
#endif
#if XQV_CTC_BEAM < 1 || XQV_CTC_BEAM > 32
#error Invalid CTC beam width
#endif
typedef struct {uint32_t key;int32_t blank,nonblank,total;unsigned order;} Entry;
static int32_t add(int32_t a,int32_t b) {
    int32_t high,low;unsigned index,rem;int64_t delta;
    if(a==NEG)return b;
    if(b==NEG)return a;
    high=a>b?a:b;low=a>b?b:a;delta=(int64_t)high-low;
    if(delta>=(INT64_C(16)<<16))return high;
    index=(unsigned)delta>>8;rem=(unsigned)delta&255u;
    return high+xq_logadd_q16[index]+(int32_t)(((int64_t)(xq_logadd_q16[index+1u]-xq_logadd_q16[index])*rem+128)>>8);
}
static int update(Entry *entries,unsigned *count,int16_t hash[1024],uint32_t key,int32_t pb,int32_t pn) {
    unsigned slot=(key*UINT32_C(2654435761))>>22;
    while(hash[slot]>=0 && entries[(unsigned)hash[slot]].key!=key)slot=(slot+1u)&1023u;
    if(hash[slot]<0) {
        if(*count>=CAP)return -1;
        hash[slot]=(int16_t)(*count);
        entries[*count].key=key;entries[*count].blank=NEG;entries[*count].nonblank=NEG;entries[*count].order=*count;
        (*count)++;
    }
    if(pb!=NEG)entries[(unsigned)hash[slot]].blank=add(entries[(unsigned)hash[slot]].blank,pb);
    if(pn!=NEG)entries[(unsigned)hash[slot]].nonblank=add(entries[(unsigned)hash[slot]].nonblank,pn);
    return 0;
}
static int compare(const void *a,const void *b) {
    const Entry *x=(const Entry*)a,*y=(const Entry*)b;
    if(x->total!=y->total)return x->total>y->total?-1:1;
    return x->order<y->order?-1:x->order>y->order;
}
static int worse(const Entry *a,const Entry *b) {
    return a->total<b->total || (a->total==b->total && a->order>b->order);
}
static void sift_worst(Entry *heap,unsigned n,unsigned root) {
    Entry value=heap[root];
    for(;;) {
        unsigned child=root*2u+1u;
        if(child>=n)break;
        if(child+1u<n && worse(heap+child+1u,heap+child))child++;
        if(!worse(heap+child,&value))break;
        heap[root]=heap[child];root=child;
    }
    heap[root]=value;
}
static unsigned select_beams(Entry beams[32],const Entry *entries,unsigned count) {
    unsigned n=count<XQV_CTC_BEAM?count:XQV_CTC_BEAM,i;
    memcpy(beams,entries,n*sizeof(Entry));
    for(i=n/2u;i>0;i--)sift_worst(beams,n,i-1u);
    for(i=n;i<count;i++)if(worse(beams,entries+i)) {
        beams[0]=entries[i];sift_worst(beams,n,0);
    }
    /* Same total/order comparator as the original full sort. */
    qsort(beams,n,sizeof(Entry),compare);
    return n;
}
static int lex_greater(uint32_t a,uint32_t b) {
    unsigned i;
    for(i=0;i<4;i++) {
        unsigned x=(a>>(i*5))&31u,y=(b>>(i*5))&31u;
        if(x!=y)return x>y;
    }
    return 0;
}
int xqvoice_decode(const int32_t *logits_q8,unsigned frames,char text[32]) {
    static const char *const vocab[22]={"","车","马","炮","兵","卒","帅","将","仕","相","一","二","三","四","五","六","七","八","九","进","退","平"};
    Entry beams[32],next[CAP];int16_t hash[1024];unsigned nbeams=1,t,i,j,count;
    int32_t best=NEG;uint32_t winner=0;
    if(!logits_q8 || !text || frames<1u || frames>100u)return -1;
    beams[0].key=0;beams[0].blank=0;beams[0].nonblank=NEG;beams[0].total=0;
    for(t=0;t<frames;t++) {
        int32_t score[22];count=0;
        for(i=0;i<1024u;i++)hash[i]=-1;
        for(i=0;i<22u;i++) {
            if(logits_q8[t*22u+i]<-32768 || logits_q8[t*22u+i]>32767)return -2;
            score[i]=logits_q8[t*22u+i]*256;
        }
        for(i=0;i<nbeams;i++) {
            Entry *e=beams+i;unsigned length=e->key>>24;
            int32_t total=e->total; /* Already computed before this beam was selected. */
            if(update(next,&count,hash,e->key,total+score[0],NEG))return -3;
            if(length) {
                unsigned last=(e->key>>((length-1u)*5u))&31u;
                if(update(next,&count,hash,e->key,NEG,e->nonblank==NEG?NEG:e->nonblank+score[last]))return -3;
            }
            if(length<4u) {
                unsigned first=length==0u?1u:length==2u?19u:10u;
                unsigned end=length==0u?10u:length==2u?22u:19u;
                for(j=first;j<end;j++) {
                    uint32_t key=(e->key&0xffffffu)|(j<<(length*5u))|((length+1u)<<24);
                    unsigned last=length?(e->key>>((length-1u)*5u))&31u:0;
                    int32_t source=length && last==j?e->blank:total;
                    if(update(next,&count,hash,key,NEG,source==NEG?NEG:source+score[j]))return -3;
                }
            }
        }
        for(i=0;i<count;i++)next[i].total=add(next[i].blank,next[i].nonblank);
        nbeams=select_beams(beams,next,count);
    }
    for(i=0;i<nbeams;i++)if((beams[i].key>>24)==4u &&
        (beams[i].total>best || (beams[i].total==best && lex_greater(beams[i].key,winner)))) {
        best=beams[i].total;winner=beams[i].key;
    }
    text[0]=0;
    if(best==NEG)return 0;
    /* Red-side contract: reject unsupported names; never rename them. */
    if((winner&31u)==5u || (winner&31u)==7u)return 0;
    for(i=0;i<4u;i++)strcat(text,vocab[(winner>>(i*5u))&31u]);
    return 1;
}
