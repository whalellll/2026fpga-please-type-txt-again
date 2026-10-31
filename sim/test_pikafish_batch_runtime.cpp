#include "pikafish_mac_runtime.h"
#include "pikafish_stagea_accel.h"
#include "pikafish_feature_updates.h"
#include "pango_mac_uapi.h"
#include <array>
#include <cassert>
#include <cstdarg>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <cerrno>
#include <sys/mman.h>
using namespace Stockfish::Eval::NNUE::MacRuntime;
namespace A=Stockfish::Eval::NNUE::StageAAccel;
static std::array<unsigned char,DdrBytes> shadow;
static unsigned calls=0,updates=0,local_parents=0;
static unsigned epoch=0,valid_slots=0,resident_hits=0;
static bool evict_resident=false;
static std::array<std::array<short,1024>,8> resident;
static int row(unsigned descriptor,unsigned lane){
    int value=int(((descriptor&65535u)*7+lane*3)%251)-125;
    return descriptor&0x80000000u?-value:value;
}
static int refscore(const short* a,const short* b){
    int value=0;for(unsigned i=0;i<1024;i++)value+=int(a[i])*3+int(b[i])*5;return value;
}
static void reference(std::array<short,1024>& out,const std::array<short,1024>& base,
                      const unsigned* descriptors,unsigned count){
    for(unsigned lane=0;lane<1024;lane++){
        unsigned sum=static_cast<unsigned short>(base[lane]);
        for(unsigned j=0;j<count;j++)sum+=row(descriptors[j],lane);
        const unsigned short bits=static_cast<unsigned short>(sum);
        memcpy(&out[lane],&bits,2);
    }
}
extern "C" int __wrap_open(const char*,int,...){return 71;}
extern "C" int __wrap_close(int){return 0;}
extern "C" void* __wrap_mmap(void*,size_t n,int,int,int,off_t){assert(n==DdrBytes);return shadow.data();}
extern "C" int __wrap_munmap(void*,size_t){return 0;}
extern "C" int __wrap_ioctl(int fd,unsigned long cmd,...){
 assert(fd==71);va_list args;va_start(args,cmd);void* pointer=va_arg(args,void*);va_end(args);
 if(cmd==PANGO_MAC_IOC_GET_INFO){
  auto& info=*static_cast<pango_mac_info*>(pointer);
  info.abi_version=1;info.device_id=PANGO_MAC_PIKAFISH_ID;info.device_version=PANGO_MAC_PIKAFISH_VERSION;
  info.scratch_bytes=DdrBytes;info.features=PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED|
    PANGO_MAC_FEATURE_STAGEA_GATHER|PANGO_MAC_FEATURE_RESIDENT_MODEL|PANGO_MAC_FEATURE_NNUE_PIPELINE|
    PANGO_MAC_FEATURE_PIKAFISH_DEDICATED|PANGO_MAC_FEATURE_NNUE_BATCH;
  if(!getenv("TEST_OLD_COPYOUT_DRIVER"))info.features|=PANGO_MAC_FEATURE_BATCH_COPYOUT_MASK;
  if(getenv("TEST_RESIDENT_DRIVER"))info.features|=PANGO_MAC_FEATURE_BATCH_RESIDENT;
  if(getenv("TEST_SINGLE_GATHER"))info.features&=~PANGO_MAC_FEATURE_NNUE_BATCH;
 }else if(cmd==PANGO_MAC_IOC_REGISTER_MODEL){
 }else if(cmd==PANGO_MAC_IOC_NNUE_CACHE_STATS){
  auto& stats=*static_cast<pango_mac_nnue_cache_stats*>(pointer);stats.abi_version=1;
 }else if(cmd==PANGO_MAC_IOC_RUN_STAGEA){
  auto& j=*static_cast<pango_mac_stagea_job*>(pointer);
  assert(pango_mac_stagea_job_valid(&j,DdrBytes));
  std::array<short,1024> base{},out{};
  memcpy(base.data(),shadow.data()+j.base_offset,2048);
  auto* descriptors=reinterpret_cast<const unsigned*>(shadow.data()+j.descriptor_offset);
  reference(out,base,descriptors,j.terms);
  memcpy(shadow.data()+j.output_offset,out.data(),2048);
  j.status=2;j.cycles=123;
 }else if(cmd==PANGO_MAC_IOC_RUN_BATCH){
  auto& b=*static_cast<pango_mac_batch*>(pointer);assert(pango_mac_batch_valid(&b));
  const bool retain=(b.flags&PANGO_MAC_BATCH_RESIDENT) && b.reserved[1]==epoch && !evict_resident;
  evict_resident=false;if(!retain)valid_slots=0;
  auto& local=resident;unsigned hitmask=0;
  for(unsigned i=0;i<b.count;i++){
   std::array<short,1024> base{};
   if(b.update[i].parent==PANGO_MAC_BATCH_EXTERNAL)memcpy(base.data(),shadow.data()+PANGO_MAC_BATCH_INPUT+i*2048,2048);
   else if(pango_mac_batch_parent_resident(b.update[i].parent)){
    const unsigned slot=b.update[i].parent&7u;
    if(retain && (valid_slots&(1u<<slot))){base=local[slot];hitmask|=1u<<i;++resident_hits;}
    else memcpy(base.data(),shadow.data()+PANGO_MAC_BATCH_INPUT+i*2048,2048);
   }else {base=local[b.update[i].parent];++local_parents;}
   const auto* descriptors=reinterpret_cast<const unsigned*>(shadow.data()+PANGO_MAC_BATCH_DESCRIPTORS+i*1024);
   reference(local[i],base,descriptors,b.update[i].terms);
   if(!(b.flags&PANGO_MAC_BATCH_COPYOUT_MASK) || (b.reserved[0]&(1u<<i)))
       memcpy(shadow.data()+PANGO_MAC_BATCH_OUTPUT+i*2048,local[i].data(),2048);
   else memset(shadow.data()+PANGO_MAC_BATCH_OUTPUT+i*2048,0xa7,2048);
  }
  if(b.flags&PANGO_MAC_BATCH_EVALUATE)b.score=refscore(local[b.first].data(),local[b.second].data());
  b.status=2;b.cycles=12345;b.jobs=b.count;b.export_words=b.count*512;
  valid_slots|=(1u<<b.count)-1;++epoch;
  if(b.flags&PANGO_MAC_BATCH_RESIDENT){b.reserved[1]=epoch;b.reserved[2]=hitmask;b.reserved[3]=valid_slots;}
  ++calls;updates+=b.count;
 }else assert(!"unexpected old single-job ioctl in batch mode");
 return 0;
}
int main(){
 setenv("PIKAFISH_NNUE_PIPELINE","1",1);setenv("PIKAFISH_NNUE_BATCH","1",1);
 if(getenv("TEST_SINGLE_GATHER")){
  auto* t=reinterpret_cast<const signed char*>(0x10000000u);
  auto* p=reinterpret_cast<const signed char*>(0x20000000u);
  assert(A::bind_gather_model(t,45547u*1024u,0x10002000u,p,16536u*1024u,0x12f45000u));
  A::FeatureUpdates terms(p,t);
  assert(terms.append(std::array<unsigned,2>{0,45546},t,1));
  assert(terms.append(std::array<unsigned,1>{16535},p,-1));
  const unsigned d[]={0,45546,0xc0004097u};
  std::array<short,1024> base{},expected{},out{};
  for(unsigned i=0;i<1024;i++)base[i]=static_cast<short>(i*71);
  reference(expected,base,d,3);
  assert(terms.apply(base.data(),out.data()) && out==expected);
  reference(expected,expected,d,3);
  assert(terms.apply(out.data(),out.data()) && out==expected);
  A::FeatureUpdates empty(p,t);assert(!empty.apply(base.data(),out.data()));
  puts("DIRECT_INDEX_SINGLE_GATHER_AND_INPLACE_PASS");return 0;
 }
 {Session s(Client::StageB);assert(s && s.register_model(0,StageBModelBytes) && s.batch_available());}
 auto threat=reinterpret_cast<const signed char*>(0x10000000u);
 auto psq=reinterpret_cast<const signed char*>(0x20000000u);
 assert(A::bind_gather_model(threat,45547u*1024u,0x10002000u,psq,16536u*1024u,0x12f45000u));
 const signed char* rows[]={threat,psq+5*1024,threat+3*1024};
 const signed char coefficients[]={1,-1,1};
 const unsigned descriptors[]={0,0xc0000005u,3};
 std::array<short,1024> base{},a{},b{},c{},expected_a{},expected_b{};
 for(unsigned i=0;i<1024;i++)base[i]=static_cast<short>(i*67);
 reference(expected_a,base,descriptors,3);reference(expected_b,expected_a,descriptors,3);
 assert(A::apply(base.data(),a.data(),rows,coefficients,3,0));
 assert(A::apply(a.data(),b.data(),rows,coefficients,3,1));
 assert(A::apply(b.data(),c.data(),rows,coefficients,0));
 assert(calls==0 && a!=expected_a); // All three updates really are deferred.
 {Session s(Client::StageB);int score=0;assert(s.pipeline(2,c.data(),a.data(),score));assert(score==refscore(expected_b.data(),expected_a.data()));}
 assert(calls==1 && updates==3 && local_parents==2);
 assert(a==expected_a && b==expected_b && c==expected_b);
 // A scalar fallback first materializes pending outputs, including in-place updates.
 assert(A::apply(a.data(),a.data(),rows,coefficients,3));A::materialize();
 reference(expected_a,expected_a,descriptors,3);assert(a==expected_a && calls==2);
 // More than8 dependencies flush safely, then continue from the published CPU snapshot.
 for(unsigned n=0;n<10;n++){
  assert(A::apply(a.data(),a.data(),rows,coefficients,3));reference(expected_a,expected_a,descriptors,3);
 }
 {Session s(Client::StageB);int score=0;assert(s.pipeline(15,a.data(),base.data(),score));assert(score==refscore(expected_a.data(),base.data()));}
 assert(a==expected_a && calls==4);
 // No updates: imports current CPU state, never trusts a pointer-only old context.
 const auto before_identity=statistics();
 base[123]^=17;
 {Session s(Client::StageB);int score=0;assert(s.pipeline(0,base.data(),a.data(),score));assert(score==refscore(base.data(),a.data()));}
 const auto stats=statistics();assert(stats.batchEnabled && stats.batchCalls==calls && stats.batchUpdates==updates);
 assert(stats.batchCpuCopyoutBytes==before_identity.batchCpuCopyoutBytes);
 assert(stats.batchSkippedIdentityBytes-before_identity.batchSkippedIdentityBytes==4096);
 assert(stats.batchDriverCopyoutBytes-before_identity.batchDriverCopyoutBytes==(getenv("TEST_OLD_COPYOUT_DRIVER")?4096u:0u));
 /* An explicitly queued identity retains the old deferred snapshot contract.
  * Only synthetic imports created inside pipeline() may omit publication. */
 {const auto snapshot=base;Session s(Client::StageA);
  assert(s.queue_gather(base.data(),base.data(),nullptr,0));base[0]^=7;
  assert(s.flush_batch());assert(base==snapshot);}
 const auto final_stats=statistics();
 // New index path must produce the same deferred dependency/alias results.
 A::FeatureUpdates direct(psq,threat);
 assert(direct.append(std::array<unsigned,1>{0},threat,1));
 assert(direct.append(std::array<unsigned,1>{5},psq,-1));
 assert(direct.append(std::array<unsigned,1>{3},threat,1));
 reference(expected_a,base,descriptors,3);
 assert(direct.apply(base.data(),a.data(),0));
 assert(direct.apply(a.data(),b.data(),1));
 reference(expected_b,expected_a,descriptors,3);
 {Session s(Client::StageB);int score=0;
  assert(s.pipeline(4,b.data(),a.data(),score));
  assert(score==refscore(expected_b.data(),expected_a.data()));}
 assert(a==expected_a && b==expected_b);
 A::FeatureUpdates empty(psq,threat);
 assert(empty.apply(b.data(),b.data()));A::materialize();assert(b==expected_b);
 const char *resident_option=std::getenv("PIKAFISH_ACCUM_RESIDENT");
 assert(statistics().batchResidentEnabled==(getenv("TEST_RESIDENT_DRIVER") && resident_option && std::strcmp(resident_option,"1")==0));
 if(statistics().batchResidentEnabled){
  const auto original=b;
  {Session s(Client::StageA);assert(s.queue_gather(b.data(),a.data(),nullptr,0));}
  b[0]^=31;evict_resident=true;
  {Session s(Client::StageA);assert(s.flush_batch());}
  assert(a==original); // Eviction must restore enqueue-time shadow, not b now.
  const auto before_hit=statistics();
  {Session s(Client::StageA);assert(s.queue_gather(a.data(),b.data(),nullptr,0));assert(s.flush_batch());}
  assert(b==original && statistics().batchResidentHits==before_hit.batchResidentHits+1);
  const auto before_change=statistics();b[2]^=19;
  {Session s(Client::StageA);assert(s.queue_gather(b.data(),c.data(),nullptr,0));assert(s.flush_batch());}
  assert(c==b && statistics().batchResidentRequested==before_change.batchResidentRequested);
  const auto before_clobber=statistics();
  {Session s(Client::StageA);assert(s.queue_gather(base.data(),a.data(),nullptr,0));
   assert(s.queue_gather(c.data(),b.data(),nullptr,0));assert(s.flush_batch());}
  assert(b==c && statistics().batchResidentRequested==before_clobber.batchResidentRequested);
  const auto before_alias=statistics();
  {Session s(Client::StageA);auto* output=s.ddr(PANGO_MAC_BATCH_OUTPUT+2048,2048);assert(output);
   b[3]^=41;memcpy(output,b.data(),2048);assert(s.queue_gather(b.data(),c.data(),nullptr,0));assert(s.flush_batch());}
  assert(c==b && statistics().batchResidentRequested==before_alias.batchResidentRequested);
  printf("ACCUM_RESIDENT_RUNTIME_HIT_EVICTION_SHADOW_SNAPSHOT_POINTER_CHANGE_CLOBBER_AND_MAPPING_PASS hits=%u\n",resident_hits);
 }
 setenv("PIKAFISH_STAGEA_ACCEL","0",1);
 assert(!direct.apply(base.data(),a.data()));
 setenv("PIKAFISH_STAGEA_ACCEL","1",1);
 assert(!direct.apply(nullptr,a.data()));
 puts("DIRECT_INDEX_BATCH_DEPENDENCY_ZERO_TERMS_ALIAS_AND_DISABLED_PASS");
 printf("PIKAFISH_COPYOUT cpu_bytes=%llu skipped_identity_bytes=%llu driver_requested_bytes=%llu\n",
  (unsigned long long)final_stats.batchCpuCopyoutBytes,(unsigned long long)final_stats.batchSkippedIdentityBytes,(unsigned long long)final_stats.batchDriverCopyoutBytes);
 pango_mac_batch valid{};valid.abi_version=1;valid.count=1;valid.update[0].parent=PANGO_MAC_BATCH_EXTERNAL;
 assert(pango_mac_batch_valid(&valid));
 auto bad=valid;bad.update[0].parent=0;assert(!pango_mac_batch_valid(&bad));
 bad=valid;bad.update[0].terms=257;assert(!pango_mac_batch_valid(&bad));
 bad=valid;bad.count=9;assert(!pango_mac_batch_valid(&bad));
 bad=valid;bad.flags=8;assert(!pango_mac_batch_valid(&bad));
 bad=valid;bad.flags=PANGO_MAC_BATCH_COPYOUT_MASK;bad.reserved[0]=2;assert(!pango_mac_batch_valid(&bad));
 bad.reserved[0]=0;assert(pango_mac_batch_valid(&bad));
 bad=valid;bad.reserved[4]=1;assert(!pango_mac_batch_valid(&bad));
 bad=valid;bad.flags=1;bad.first=1;assert(!pango_mac_batch_valid(&bad));
 bad=valid;bad.update[1].terms=1;assert(!pango_mac_batch_valid(&bad));
 printf("PIKAFISH_BATCH_RUNTIME_DEFER_ALIAS_FLUSH_CAPACITY_POINTER_REUSE_AND_ABI_PASS calls=%u updates=%u local_parents=%u\n",calls,updates,local_parents);
}
