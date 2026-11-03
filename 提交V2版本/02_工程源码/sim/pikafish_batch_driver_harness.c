/* Prefix for executing the actual extracted kernel batch transaction. */
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include "pango_mac_uapi.h"
#undef assert
#define assert(c) do { if(!(c)){fprintf(stderr,"CHECK_FAILED %s:%d: %s\n",__FILE__,__LINE__,#c);exit(1);} } while(0)
typedef uint8_t u8;typedef uint32_t u32;typedef int64_t ktime_t;
#define __iomem
#define GFP_KERNEL 0
#define BIT(x) (1u<<(x))
struct mutex { int held; };
struct pango_mac_file;
struct pango_mac_dev { bool batch_supported,batch_resident_supported;u32 batch_epoch,batch_valid;struct pango_mac_file *batch_owner;u8 *regs,*scratch;u32 scratch_bus;size_t scratch_bytes;struct mutex run_lock;struct pango_mac_file *resident_owner,*vision_owner; };
struct pango_mac_file { struct pango_mac_dev *mac;u8 *shadow,*model_snapshot;struct pango_mac_batch_snapshot *batch_snapshot;u32 model_offset,model_bytes,nnue_tag[2];struct pango_mac_nnue_cache_stats nnue_stats; };
static struct pango_mac_dev mac;
static u8 registers[512],scratch[1048576],shadow[1048576],model[0x91000];
static struct pango_mac_file ctx,foreign;
static unsigned starts,invalidates,restores,yields;
static unsigned copyout_bytes;
static unsigned copyout_calls;
static unsigned input_snapshot_bytes,input_publish_bytes;
static unsigned input_publish_calls;
static bool execution_error,stall,mutate_shadow,allocation_error,bad_count;
static ktime_t ticks;
static unsigned allocations,frees;
static bool lock_error;
/* Keep these visible when the candidate no longer calls them. */
void *kvzalloc(size_t n,int flags){(void)flags;allocations++;return allocation_error?NULL:calloc(1,n);}
void kvfree(void *p){frees++;free(p);}
static int mutex_lock_interruptible(struct mutex *m){assert(!m->held);if(lock_error)return -EINTR;m->held=1;return 0;}
static void mutex_unlock(struct mutex *m){assert(m->held);m->held=0;}
static void cond_resched(void){assert(mac.run_lock.held);yields++;}
static void cpu_relax(void){}
static void mb(void){}
static void wmb(void){}
static void rmb(void){}
static ktime_t ktime_get(void){ticks+=10;return ticks;}
static ktime_t ktime_add_us(ktime_t a,u32 b){return a+b;}
static int ktime_compare(ktime_t a,ktime_t b){return (a>b)-(a<b);}
static u32 load32(const void *p){u32 v;memcpy(&v,p,4);return v;}
static void store32(void *p,u32 v){memcpy(p,&v,4);}
static void execute(void){
 u32 count=load32(registers+0x94),config=load32(registers+0x9c),i,lane,j;
 u32 list=load32(registers+0x90)-mac.scratch_bus;
 static int16_t local[8][1024];
 if(!(config&BIT(10)))memset(local,0,sizeof(local));
 assert(mac.run_lock.held);starts++;
 if(stall){store32(registers+0x8c,1);return;}
 for(i=0;i<count;i++){
  u32 *entry=(u32 *)(scratch+list+i*32);
  for(j=4;j<8;j++)assert(entry[j]==0); /* reused list padding must not leak */
  const int16_t *base=entry[0]>=mac.scratch_bus+PANGO_MAC_BATCH_CONTEXT?
   local[(entry[0]-mac.scratch_bus-PANGO_MAC_BATCH_CONTEXT)/2048]:
   (int16_t *)(scratch+entry[0]-mac.scratch_bus);
  const u32 *descriptors=(u32 *)(scratch+entry[1]-mac.scratch_bus);
  for(lane=0;lane<1024;lane++){
   unsigned sum=(uint16_t)base[lane];
   for(j=0;j<entry[2];j++){
    int value=(int)((descriptors[j]&65535u)+lane)%127-63;
    sum+=descriptors[j]&0x80000000u?-value:value;
   }
   {uint16_t bits=(uint16_t)sum;memcpy(&local[i][lane],&bits,2);}
  }
 }
 if(!execution_error)for(i=0;i<count;i++){
  u32 *entry=(u32 *)(scratch+list+i*32);
  memcpy(scratch+entry[3]-mac.scratch_bus,local[i],2048);
 }
 store32(registers+0x8c,execution_error?6:2);
 store32(registers+0xa0,9000);store32(registers+0xa4,bad_count?0:count);
 store32(registers+0xbc,count*512);
 if(config&BIT(9)){
  int value=0;
  for(lane=0;lane<1024;lane++)value+=local[config&7][lane]*3+local[(config>>4)&7][lane]*5;
  store32(registers+0xa8,(u32)value);
 }
 store32(registers+0x1c4,3);store32(registers+0x1c8,0);
}
static u32 readl(const void *p){return load32(p);}
static void writel(u32 v,void *p){
 ptrdiff_t offset=(u8 *)p-registers;store32(p,v);
 if(offset==0x188 && v==64)invalidates++;
 if(offset==0x88 && v==1)execute();
 /* Boundary-stop request intentionally leaves BUSY until mocked drain. */
}
static void memcpy_toio(void *to,const void *from,size_t n){
 assert(mac.run_lock.held);
 if((uintptr_t)to>=(uintptr_t)(scratch+PANGO_MAC_BATCH_INPUT) &&
    (uintptr_t)to<(uintptr_t)(scratch+PANGO_MAC_BATCH_INPUT+16384)){input_publish_bytes+=(unsigned)n;input_publish_calls++;}
 if(mutate_shadow){mutate_shadow=false;store32(shadow+PANGO_MAC_BATCH_DESCRIPTORS,0x00010000);}
 memcpy(to,from,n);
}
static void memcpy_fromio(void *to,const void *from,size_t n){assert(mac.run_lock.held);copyout_bytes+=(unsigned)n;copyout_calls++;memcpy(to,from,n);}
static void pango_mac_copy_data(void *to,void *physical,const void *from,size_t n){
 assert(mac.run_lock.held);assert(!to && physical==scratch && n==sizeof(model));
 memcpy(physical,from,n);restores++;
}
static void pango_mac_invalidate_range(struct pango_mac_dev *m,u32 offset,u32 bytes){
 if(m->resident_owner && pango_mac_ranges_overlap(m->resident_owner->model_offset,m->resident_owner->model_bytes,offset,bytes))m->resident_owner=NULL;
}
static bool pango_mac_engines_busy(struct pango_mac_dev *m){return (load32(m->regs+0x8c)&1)!=0;}
static void *batch_memcpy(void *to,const void *from,size_t n){
 uintptr_t start=(uintptr_t)(shadow+PANGO_MAC_BATCH_INPUT),p=(uintptr_t)from;
 if(p>=start && p<start+16384u)input_snapshot_bytes+=(unsigned)n;
 return memcpy(to,from,n);
}
#define memcpy batch_memcpy
#define pango_mac_toio32 memcpy_toio
#define pango_mac_fromio32 memcpy_fromio
/* ACTUAL_KERNEL_BATCH_INSERT */
#undef memcpy
static int run_checked(struct pango_mac_file *c,struct pango_mac_batch *b){
#ifdef PANGO_TEST_REUSED_SNAPSHOT
 unsigned a=allocations,f=frees;
#endif
 int ret=pango_mac_run_batch(c,b);
#ifdef PANGO_TEST_REUSED_SNAPSHOT
 assert(allocations==a && frees==f); /* all success/error paths allocation-free */
#endif
 return ret;
}
static struct pango_mac_batch request(void){
 struct pango_mac_batch b={0};unsigned i;
 b.abi_version=1;b.count=2;b.flags=1;b.first=0;b.second=1;b.bucket=3;
 b.update[0].parent=PANGO_MAC_BATCH_EXTERNAL;b.update[0].terms=1;
 b.update[1].parent=0;b.update[1].terms=0;
 for(i=0;i<1024;i++){int16_t v=(int16_t)(i*71);memcpy(shadow+PANGO_MAC_BATCH_INPUT+i*2,&v,2);}
 store32(shadow+PANGO_MAC_BATCH_DESCRIPTORS,0);
 memset(shadow+PANGO_MAC_BATCH_OUTPUT,0xa5,16384);
 return b;
}
static void initialize(void){
 memset(&ctx,0,sizeof(ctx));memset(&foreign,0,sizeof(foreign));memset(registers,0,sizeof(registers));
 mac=(struct pango_mac_dev){.batch_supported=true,.regs=registers,.scratch=scratch,.scratch_bus=0x1b000000,.scratch_bytes=sizeof(scratch)};
 ctx.mac=&mac;ctx.shadow=shadow;ctx.model_snapshot=model;ctx.model_bytes=sizeof(model);
#ifdef PANGO_TEST_REUSED_SNAPSHOT
 ctx.batch_snapshot=malloc(sizeof(*ctx.batch_snapshot));assert(ctx.batch_snapshot);
 memset(ctx.batch_snapshot,0xa5,sizeof(*ctx.batch_snapshot));
#endif
 foreign.model_offset=PANGO_MAC_BATCH_LIST;foreign.model_bytes=64;
 mac.resident_owner=&foreign;starts=invalidates=restores=yields=0;ticks=0;
 execution_error=stall=mutate_shadow=allocation_error=bad_count=lock_error=false;
}
int main(void){
 struct pango_mac_batch b;unsigned i,before;
 initialize();b=request();mutate_shadow=true;
 assert(run_checked(&ctx,&b)==0 && !mac.run_lock.held && starts==1 && restores==1 && invalidates==1);
#ifdef PANGO_TEST_INPUT_DIRECT
 assert(input_snapshot_bytes==0);
#else
 assert(input_snapshot_bytes==2048);
#endif
 assert(mac.resident_owner==&ctx && ctx.nnue_stats.runs==1 && ctx.nnue_stats.hits==1);
 assert(input_publish_bytes==2048);
 for(i=0;i<1024;i++){
  int16_t value,other;uint16_t expected=(uint16_t)((uint16_t)(i*71)+(int)(i%127)-63);
  memcpy(&value,shadow+PANGO_MAC_BATCH_OUTPUT+i*2,2);memcpy(&other,shadow+PANGO_MAC_BATCH_OUTPUT+2048+i*2,2);
  assert((uint16_t)value==expected && other==value);
 }
 before=starts;b=request();b.update[1].parent=1;
 assert(run_checked(&ctx,&b)==-EINVAL && starts==before && !mac.run_lock.held);
 b=request();store32(shadow+PANGO_MAC_BATCH_DESCRIPTORS,0x00010000);
 assert(run_checked(&ctx,&b)==-EINVAL && starts==before && !mac.run_lock.held);
 b=request();ctx.model_offset=PANGO_MAC_BATCH_LIST;
 assert(run_checked(&ctx,&b)==-EINVAL && starts==before);ctx.model_offset=0;
 b=request();execution_error=true;
 assert(run_checked(&ctx,&b)==-EIO && shadow[PANGO_MAC_BATCH_OUTPUT]==0xa5 && !mac.run_lock.held);
 execution_error=false;b=request();bad_count=true;
 assert(run_checked(&ctx,&b)==-EIO && shadow[PANGO_MAC_BATCH_OUTPUT]==0xa5);bad_count=false;
 b=request();stall=true;b.timeout_us=1;
 assert(run_checked(&ctx,&b)==-ETIMEDOUT && pango_mac_engines_busy(&mac) && shadow[PANGO_MAC_BATCH_OUTPUT]==0xa5);
 b=request();assert(run_checked(&ctx,&b)==-EBUSY && !mac.run_lock.held);
 stall=false;store32(registers+0x8c,0);assert(run_checked(&ctx,&b)==0);
#ifdef PANGO_TEST_REUSED_SNAPSHOT
 b=request();lock_error=true;before=starts;
 assert(run_checked(&ctx,&b)==-EINTR && starts==before && !mac.run_lock.held);lock_error=false;
 /* Failure of the general allocator after probe cannot affect submissions. */
 allocation_error=true;
 for(i=0;i<100;i++){
  unsigned j,k;int16_t expected[1024];
  b=request();b.count=i%2?1:8;b.second=b.count-1;
  for(j=0;j<b.count;j++){
   b.update[j].parent=j?j-1:PANGO_MAC_BATCH_EXTERNAL;
   b.update[j].terms=i%3?0:256;
   for(k=0;k<b.update[j].terms;k++)store32(shadow+PANGO_MAC_BATCH_DESCRIPTORS+j*1024+k*4,k|((k%2)<<31));
  }
  for(k=0;k<1024;k++){
   unsigned sum=(uint16_t)(k*71);
   for(j=0;j<b.count;j++){
    unsigned term;for(term=0;term<b.update[j].terms;term++){
     int delta=(int)((term+k)%127)-63;sum+=term%2?-delta:delta;
    }
   }
   {uint16_t bits=(uint16_t)sum;memcpy(&expected[k],&bits,2);}
  }
  assert(run_checked(&ctx,&b)==0 && !mac.run_lock.held);
  assert(!memcmp(shadow+PANGO_MAC_BATCH_OUTPUT+(b.count-1)*2048,expected,2048));
 }
 {
  struct pango_mac_batch_snapshot *saved=ctx.batch_snapshot;
  ctx.batch_snapshot=NULL;b=request();before=starts;
  assert(run_checked(&ctx,&b)==-ENOMEM && starts==before && !mac.run_lock.held);
  ctx.batch_snapshot=saved;
 }
 {
  struct pango_mac_file peer=ctx;
  struct pango_mac_batch_snapshot *saved=malloc(sizeof(*saved));assert(saved);
  peer.shadow=malloc(sizeof(shadow));assert(peer.shadow);
  peer.batch_snapshot=malloc(sizeof(*saved));assert(peer.batch_snapshot);
  memset(peer.batch_snapshot,0x5a,sizeof(*saved));
  b=request();memcpy(peer.shadow,shadow,sizeof(shadow));
  memset(peer.shadow+PANGO_MAC_BATCH_INPUT,0,2048);
  memcpy(saved,ctx.batch_snapshot,sizeof(*saved));
  assert(run_checked(&peer,&b)==0 && mac.resident_owner==&peer);
  assert(!memcmp(saved,ctx.batch_snapshot,sizeof(*saved)));
  {int16_t v;memcpy(&v,peer.shadow+PANGO_MAC_BATCH_OUTPUT,2);assert(v==-63);}
  b=request();assert(run_checked(&ctx,&b)==0 && mac.resident_owner==&ctx);
  free(saved);free(peer.batch_snapshot);free(peer.shadow);
 }
 puts("ACTUAL_BATCH_DRIVER_REUSED_POISONED_SNAPSHOT_100_VARIABLE_BATCHES_NO_HOT_ALLOCATION_PASS");
#else
 b=request();allocation_error=true;assert(run_checked(&ctx,&b)==-ENOMEM && !mac.run_lock.held);
#endif
 {
  unsigned full,masked;int32_t score;
  b=request();full=copyout_bytes;mac.vision_owner=&ctx;
  assert(run_checked(&ctx,&b)==0 && !mac.vision_owner);score=b.score;full=copyout_bytes-full;assert(full==4096);
  b=request();b.flags|=PANGO_MAC_BATCH_COPYOUT_MASK;b.reserved[0]=0;masked=copyout_bytes;
  assert(run_checked(&ctx,&b)==0 && b.score==(u32)score && b.export_words==1024);
  assert(copyout_bytes==masked && shadow[PANGO_MAC_BATCH_OUTPUT]==0xa5);
  b=request();b.flags|=PANGO_MAC_BATCH_COPYOUT_MASK;b.reserved[0]=2;masked=copyout_bytes;
  assert(run_checked(&ctx,&b)==0 && b.score==(u32)score && copyout_bytes==masked+2048);
  assert(shadow[PANGO_MAC_BATCH_OUTPUT]==0xa5 && shadow[PANGO_MAC_BATCH_OUTPUT+2048]!=0xa5);
  b=request();b.flags|=PANGO_MAC_BATCH_COPYOUT_MASK;b.reserved[0]=4;
  assert(run_checked(&ctx,&b)==-EINVAL);
  puts("BATCH_MASK_SCORE_UNCHANGED_COPYOUT_4096_TO_ZERO_PARTIAL_2048_AND_INVALID_MASK_PASS");
 }
 // Eight independent external bases; a bad final descriptor publishes nothing.
 {
  unsigned j,published=input_publish_bytes;
  b=request();b.count=8;b.second=7;
  for(j=0;j<8;j++){
   b.update[j].parent=PANGO_MAC_BATCH_EXTERNAL;b.update[j].terms=1;
   memcpy(shadow+PANGO_MAC_BATCH_INPUT+j*2048,shadow+PANGO_MAC_BATCH_INPUT,2048);
   store32(shadow+PANGO_MAC_BATCH_DESCRIPTORS+j*1024,j);
  }
  store32(shadow+PANGO_MAC_BATCH_DESCRIPTORS+7*1024,0x10000);
  before=starts;assert(run_checked(&ctx,&b)==-EINVAL && starts==before);
  assert(input_publish_bytes==published);
  store32(shadow+PANGO_MAC_BATCH_DESCRIPTORS+7*1024,7);
  assert(run_checked(&ctx,&b)==0 && input_publish_bytes==published+16384);
  for(j=0;j<8;j++)for(i=0;i<1024;i++){
   int16_t value;uint16_t expected=(uint16_t)((uint16_t)(i*71)+(int)((j+i)%127)-63);
   memcpy(&value,shadow+PANGO_MAC_BATCH_OUTPUT+j*2048+i*2,2);assert((uint16_t)value==expected);
  }
 }
 puts("BATCH_EIGHT_EXTERNAL_BASES_AND_LATE_INVALID_DESCRIPTOR_NO_PUBLICATION_PASS");
 {
  unsigned count,mask,cases=0;
  for(count=1;count<=8;count++)for(mask=0;mask<(1u<<count);mask++){
   unsigned j,slot,expected_calls=0,expected_bytes=0,old_calls=copyout_calls,old_bytes=copyout_bytes;
   b=request();b.count=count;b.second=count-1;
   memset(b.update,0,sizeof(b.update));
   for(j=0;j<count;j++){
    b.update[j].parent=j?j-1:PANGO_MAC_BATCH_EXTERNAL;
    b.update[j].terms=0;
   }
   b.flags|=PANGO_MAC_BATCH_COPYOUT_MASK;b.reserved[0]=mask;
   for(j=0;j<count;j++)if(mask&(1u<<j)){
    expected_bytes+=2048;
#ifdef PANGO_TEST_COPYOUT_COALESCED
    expected_calls+=j==0 || !(mask&(1u<<(j-1)));
#else
    expected_calls++;
#endif
   }
   assert(run_checked(&ctx,&b)==0);
   assert(copyout_calls-old_calls==expected_calls && copyout_bytes-old_bytes==expected_bytes);
   for(slot=0;slot<count;slot++)for(j=0;j<2048;j++){
    u8 expected=mask&(1u<<slot)?shadow[PANGO_MAC_BATCH_INPUT+j]:0xa5;
    assert(shadow[PANGO_MAC_BATCH_OUTPUT+slot*2048+j]==expected);
   }
   cases++;
  }
  printf("BATCH_ALL_COPYOUT_MASKS_PASS cases=%u coalesced=%u\n",cases,
#ifdef PANGO_TEST_COPYOUT_COALESCED
  1u
#else
  0u
#endif
  );
 }
 {
  unsigned count,pattern,cases=0;
  for(count=1;count<=8;count++)for(pattern=0;pattern<(1u<<(count-1));pattern++){
   unsigned j,bytes=0,calls=0,old_bytes=input_publish_bytes,old_calls=input_publish_calls;
   b=request();b.count=count;b.second=count-1;memset(b.update,0,sizeof(b.update));
   for(j=0;j<count;j++){
    bool external=j==0 || (pattern&(1u<<(j-1)));
    b.update[j].parent=external?PANGO_MAC_BATCH_EXTERNAL:j-1;
    if(external){
     memcpy(shadow+PANGO_MAC_BATCH_INPUT+j*2048,shadow+PANGO_MAC_BATCH_INPUT,2048);bytes+=2048;
#ifdef PANGO_TEST_COPYOUT_COALESCED
     calls+=j==0 || b.update[j-1].parent!=PANGO_MAC_BATCH_EXTERNAL;
#else
     calls++;
#endif
    }
   }
   assert(run_checked(&ctx,&b)==0);
   assert(input_publish_calls-old_calls==calls && input_publish_bytes-old_bytes==bytes);
   for(j=0;j<count;j++)assert(!memcmp(shadow+PANGO_MAC_BATCH_OUTPUT+j*2048,shadow+PANGO_MAC_BATCH_INPUT,2048));
   cases++;
  }
  printf("BATCH_ALL_EXTERNAL_LOCAL_PATTERNS_PASS cases=%u\n",cases);
 }
 {
  u32 cookie,hit_cookie;unsigned published;
  int16_t expected[1024];
  b=request();b.flags|=PANGO_MAC_BATCH_RESIDENT;
  before=starts;assert(run_checked(&ctx,&b)==-EOPNOTSUPP && starts==before);
  mac.batch_resident_supported=true;
  b=request();b.flags|=PANGO_MAC_BATCH_RESIDENT;
  assert(run_checked(&ctx,&b)==0 && b.reserved[1] && b.reserved[2]==0 && b.reserved[3]==3);
  cookie=b.reserved[1];memcpy(expected,shadow+PANGO_MAC_BATCH_OUTPUT+2048,2048);
  b=request();b.flags|=PANGO_MAC_BATCH_RESIDENT;b.reserved[1]=cookie;
  b.update[0].parent=PANGO_MAC_BATCH_RESIDENT_PARENT(1);b.update[0].terms=0;
  memcpy(shadow+PANGO_MAC_BATCH_INPUT,expected,2048);published=input_publish_bytes;
  assert(run_checked(&ctx,&b)==0 && b.reserved[2]==1 && b.reserved[1]!=cookie);
  assert(input_publish_bytes==published && !memcmp(shadow+PANGO_MAC_BATCH_OUTPUT,expected,2048));
  hit_cookie=b.reserved[1];
  b=request();b.flags|=PANGO_MAC_BATCH_RESIDENT;b.reserved[1]=cookie;
  b.update[0].parent=PANGO_MAC_BATCH_RESIDENT_PARENT(1);b.update[0].terms=0;
  memcpy(shadow+PANGO_MAC_BATCH_INPUT,expected,2048);published=input_publish_bytes;
  assert(run_checked(&ctx,&b)==0 && b.reserved[2]==0 && input_publish_bytes==published+2048);
  assert(!memcmp(shadow+PANGO_MAC_BATCH_OUTPUT,expected,2048));
  cookie=b.reserved[1];assert(cookie!=hit_cookie);
  {
   struct pango_mac_file peer=ctx;
   peer.shadow=calloc(1,sizeof(shadow));peer.batch_snapshot=calloc(1,sizeof(*peer.batch_snapshot));assert(peer.shadow && peer.batch_snapshot);
   b=request();b.count=1;b.second=0;memset(b.update,0,sizeof(b.update));b.update[0].parent=PANGO_MAC_BATCH_EXTERNAL;
   memset(peer.shadow+PANGO_MAC_BATCH_INPUT,0x33,2048);
   assert(run_checked(&peer,&b)==0 && !mac.batch_owner);
   b=request();b.flags|=PANGO_MAC_BATCH_RESIDENT;b.reserved[1]=cookie;
   b.update[0].parent=PANGO_MAC_BATCH_RESIDENT_PARENT(1);b.update[0].terms=0;
   memcpy(shadow+PANGO_MAC_BATCH_INPUT,expected,2048);published=input_publish_bytes;
   assert(run_checked(&ctx,&b)==0 && !b.reserved[2] && input_publish_bytes==published+2048);
   assert(!memcmp(shadow+PANGO_MAC_BATCH_OUTPUT,expected,2048));
   free(peer.shadow);free(peer.batch_snapshot);
  }
  b=request();b.flags|=PANGO_MAC_BATCH_RESIDENT;b.update[1].parent=PANGO_MAC_BATCH_RESIDENT_PARENT(0);
  before=starts;published=input_publish_bytes;
  assert(run_checked(&ctx,&b)==-EINVAL && starts==before && input_publish_bytes==published);
  b=request();b.flags|=PANGO_MAC_BATCH_RESIDENT;execution_error=true;
  assert(run_checked(&ctx,&b)==-EIO && !mac.batch_owner && !mac.batch_valid && shadow[PANGO_MAC_BATCH_OUTPUT]==0xa5);
  execution_error=false;b=request();b.flags|=PANGO_MAC_BATCH_RESIDENT;
  assert(run_checked(&ctx,&b)==0 && mac.batch_owner==&ctx);
  mac.batch_epoch=~0u;b=request();b.flags|=PANGO_MAC_BATCH_RESIDENT;before=starts;
  assert(run_checked(&ctx,&b)==-EOVERFLOW && starts==before);
  puts("ACCUM_RESIDENT_DRIVER_HIT_BYTES_ZERO_STALE_AND_FOREIGN_SHADOW_RECOVERY_CONFLICT_ERROR_AND_WRAP_PASS");
 }
 printf("BATCH_INPUT_COPY_FIRST_EXTERNAL_SNAPSHOT_BYTES=%u snapshot_struct_bytes=%zu\n",
#ifdef PANGO_TEST_INPUT_DIRECT
  0u,
#else
  2048u,
#endif
  sizeof(struct pango_mac_batch_snapshot));
 puts("ACTUAL_BATCH_DRIVER_SNAPSHOT_MODEL_OWNER_PUBLICATION_TIMEOUT_DRAIN_AND_RECOVERY_PASS");
#ifdef PANGO_TEST_REUSED_SNAPSHOT
 free(ctx.batch_snapshot);
#endif
 return 0;
}
