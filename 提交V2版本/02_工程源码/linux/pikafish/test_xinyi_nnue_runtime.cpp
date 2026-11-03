#include "pikafish_mac_runtime.h"
#include "pikafish_stagea_accel.h"
#include "pango_mac_uapi.h"
#include <array>
#include <cassert>
#include <cstdarg>
#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <cstdio>
#include <sys/mman.h>
using namespace Stockfish::Eval::NNUE::MacRuntime;
static std::array<unsigned char,DdrBytes> shadow;
static std::array<std::array<short,1024>,2> physical;
static unsigned tags[2],generation=0,uploads=0,gathers=0,runs=0;
static bool foreign_owner=false;
static bool fail_job=false;
static int gather_seed=0;
static unsigned ordinary_gathers=0;
static unsigned device_opens=0,devmem_opens=0;
extern "C" int __wrap_open(const char* path,int,...){
    if(!strcmp(path,"/dev/mem")){devmem_opens++;errno=EACCES;return -1;}
    device_opens++;
    if(std::getenv("MOCK_OPEN_FAIL")){errno=ENOENT;return -1;}
    return 71;
}
extern "C" int __wrap_close(int){return 0;}
extern "C" void* __wrap_mmap(void*,size_t bytes,int,int,int,off_t){assert(bytes==DdrBytes);return shadow.data();}
extern "C" int __wrap_munmap(void*,size_t){return 0;}
static int score(const short* a,const short* b){
    int result=0;for(unsigned i=0;i<1024;i++)result+=a[i]*3+b[i]*5;return result;
}
extern "C" int __wrap_ioctl(int fd,unsigned long request,...){
    assert(fd==71);va_list args;va_start(args,request);void* p=va_arg(args,void*);va_end(args);
    if(request==PANGO_MAC_IOC_GET_INFO){
        auto& v=*static_cast<pango_mac_info*>(p);v.abi_version=PANGO_MAC_ABI_VERSION;
        const bool dedicated=std::getenv("MOCK_PIKAFISH_DEDICATED")!=nullptr;
        v.device_id=dedicated?PANGO_MAC_PIKAFISH_ID:PANGO_MAC_ID;
        v.device_version=dedicated?PANGO_MAC_PIKAFISH_VERSION:PANGO_MAC_VERSION;v.scratch_bytes=DdrBytes;
        v.features=PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED|
            PANGO_MAC_FEATURE_STAGEA_GATHER|PANGO_MAC_FEATURE_RESIDENT_MODEL|PANGO_MAC_FEATURE_NNUE_PIPELINE;
        if(dedicated)v.features|=PANGO_MAC_FEATURE_PIKAFISH_DEDICATED;
        if(std::getenv("MOCK_MISSING_PIPELINE"))v.features&=~PANGO_MAC_FEATURE_NNUE_PIPELINE;
        if(std::getenv("MOCK_MISSING_FEATURE"))v.features&=~PANGO_MAC_FEATURE_RESIDENT_MODEL;
    }else if(request==PANGO_MAC_IOC_NNUE_CACHE_STATS){
        auto& v=*static_cast<pango_mac_nnue_cache_stats*>(p);v.abi_version=1;v.runs=runs;v.hits=0;v.read_words=runs*8801;
    }else if(request==PANGO_MAC_IOC_REGISTER_MODEL){tags[0]=tags[1]=0;
    }else if(request==PANGO_MAC_IOC_NNUE_UPLOAD){
        auto& v=*static_cast<pango_mac_nnue_upload*>(p);assert(pango_mac_nnue_upload_valid(&v,DdrBytes));
        memcpy(physical[v.view].data(),shadow.data()+v.source_offset,2048);
        tags[v.view]=v.tag=++generation;++uploads;
    }else if(request==PANGO_MAC_IOC_RUN_STAGEA_LINK){
        auto& v=*static_cast<pango_mac_stagea_link*>(p);assert(v.view<2 && !v.tag);
        for(unsigned i=0;i<1024;i++)physical[v.view][i]=short(int(i%201)-100+gather_seed);
        memcpy(shadow.data()+StageAOutputOffset,physical[v.view].data(),2048);
        tags[v.view]=v.tag=++generation;v.job.cycles=300;v.job.status=2;++gathers;
    }else if(request==PANGO_MAC_IOC_RUN_STAGEA){
        auto& v=*static_cast<pango_mac_stagea_job*>(p);
        std::array<short,1024> result;
        for(unsigned i=0;i<1024;i++)result[i]=short(int(i%201)-100+gather_seed);
        memcpy(shadow.data()+StageAOutputOffset,result.data(),2048);
        v.cycles=300;v.status=2;++ordinary_gathers;
    }else if(request==PANGO_MAC_IOC_RUN_NNUE){
        auto& v=*static_cast<pango_mac_nnue_job*>(p);assert(pango_mac_nnue_job_valid(&v));
        if(fail_job){fail_job=false;errno=EIO;return -1;}
        if(foreign_owner){foreign_owner=false;tags[0]=++generation;}
        if(tags[0]!=v.tag0 || tags[1]!=v.tag1){errno=ESTALE;return -1;}
        v.score=score(physical[v.first_view].data(),physical[v.first_view^1].data());
        v.cycles=17000;v.status=2;v.jobs=6;++runs;
    }else assert(!"unexpected ioctl");
    return 0;
}
int main(int argc,char **argv){
    setenv("PIKAFISH_MAC_BACKEND","driver",1);
    setenv("PIKAFISH_MAC_REQUIRE_DRIVER","1",1);
    setenv("PIKAFISH_MAC_REQUIRE_FEATURES","0x60",1);
    if(argc==2){
        if(!strcmp(argv[1],"missing-feature"))setenv("MOCK_MISSING_FEATURE","1",1);
        else if(!strcmp(argv[1],"missing-pipeline")){
            setenv("MOCK_PIKAFISH_DEDICATED","1",1);setenv("MOCK_MISSING_PIPELINE","1",1);
        } else if(!strcmp(argv[1],"open-failure"))setenv("MOCK_OPEN_FAIL","1",1);
        else if(!strcmp(argv[1],"invalid-features"))setenv("PIKAFISH_MAC_REQUIRE_FEATURES","0x60garbage",1);
        else if(!strcmp(argv[1],"invalid-backend"))setenv("PIKAFISH_MAC_BACKEND","legacy-devmem",1);
        else if(!strcmp(argv[1],"strict-mmio-conflict"))setenv("PIKAFISH_MAC_BACKEND","mmio-shadow",1);
        else return 2;
        Session s(Client::StageB);assert(!s);assert(!devmem_opens);
        if(!strcmp(argv[1],"invalid-features") || !strcmp(argv[1],"invalid-backend") ||
           !strcmp(argv[1],"strict-mmio-conflict"))assert(!device_opens);
        printf("XINYI_NNUE_STRICT_POLICY_REJECT_PASS case=%s devmem_opens=0\n",argv[1]);return 0;
    }
    assert(argc==1);
    setenv("PIKAFISH_NNUE_PIPELINE","1",1);
    std::array<short,1024> a{},b{},c{};
    for(unsigned i=0;i<1024;i++){a[i]=short(i%191-95);b[i]=short(i%127);c[i]=short(-int(i%47));}
    {
        Session s(Client::StageB);assert(s);assert(s.register_model(0,StageBModelBytes));
        int result=0;assert(s.pipeline(0,a.data(),b.data(),result));assert(result==score(a.data(),b.data()));assert(uploads==2);
        assert(s.pipeline(15,b.data(),a.data(),result));assert(result==score(b.data(),a.data()));assert(uploads==2);
        a[500]+=5;assert(s.pipeline(3,a.data(),b.data(),result));assert(result==score(a.data(),b.data()));assert(uploads==3);
        assert(s.pipeline(7,c.data(),a.data(),result));assert(result==score(c.data(),a.data()));assert(uploads==4);
        foreign_owner=true;assert(s.pipeline(2,c.data(),a.data(),result));
        assert(result==score(c.data(),a.data()));assert(uploads==6);
        fail_job=true;assert(!s.pipeline(2,c.data(),a.data(),result));
        assert(s.pipeline(2,c.data(),a.data(),result));assert(result==score(c.data(),a.data()));assert(uploads==8);
        assert(!s.pipeline(16,c.data(),a.data(),result));
    }
    {
        Session s(Client::StageA);assert(s);assert(s.gather(1,nullptr,b.data(),1));
        assert(physical[1][10]==-90);
        memcpy(b.data(),shadow.data()+StageAOutputOffset,2048);
    }
    {
        Session s(Client::StageB);int result=0;
        assert(s.pipeline(1,a.data(),b.data(),result));assert(result==score(a.data(),b.data()));
    }
    auto v=statistics();assert(v.pipelineCompleted==runs && v.pipelineUploads==uploads && v.pipelineFailures==1);
    if(std::getenv("MOCK_PIKAFISH_DEDICATED"))assert(v.dedicated && v.cacheStatsValid && v.cacheRuns==runs && v.cacheReadWords==runs*8801);
    assert(gathers==1 && runs==7 && v.pipelineRetries==1);
    // Drive the actual StageA frontend, including a refresh-cache intermediate.
    // The descriptor mock never dereferences the immutable model table address.
    namespace A=Stockfish::Eval::NNUE::StageAAccel;
    auto threat=reinterpret_cast<const std::int8_t*>(0x10000000u);
    auto psq=reinterpret_cast<const std::int8_t*>(0x20000000u);
    assert(A::bind_gather_model(threat,45547u*1024u,0x10002000u,psq,16536u*1024u,0x12f45000u));
    const std::int8_t* rows[]={threat};const std::int8_t coefficients[]={1};
    std::array<short,1024> white{},black{},intermediate{};
    gather_seed=5;assert(A::apply(a.data(),white.data(),rows,coefficients,1,0));
    const unsigned white_tag=tags[0];auto saved_white=physical[0];
    gather_seed=1000;assert(A::apply(a.data(),intermediate.data(),rows,coefficients,1));
    assert(tags[0]==white_tag && physical[0]==saved_white && ordinary_gathers==1);
    gather_seed=9;assert(A::apply(a.data(),black.data(),rows,coefficients,1,1));
    const unsigned before_uploads=uploads;
    {
        Session s(Client::StageB);int result=0;
        assert(s.pipeline(5,white.data(),black.data(),result));
        assert(result==score(white.data(),black.data()) && uploads==before_uploads);
    }
    puts("NNUE_STAGEA_BOTH_PERSPECTIVES_REFRESH_INTERMEDIATE_ZERO_REUPLOAD_PASS");
    printf("NNUE_PIPELINE_RUNTIME_CONTEXT_ORDER_POINTER_REUSE_STALE_AND_GATHER_PASS uploads=%u jobs=%u\n",uploads,runs*6);
}
