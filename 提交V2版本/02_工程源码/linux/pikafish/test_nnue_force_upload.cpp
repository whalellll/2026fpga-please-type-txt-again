#define ioctl test_ioctl
#include "pikafish_mac_runtime.cpp"
#undef ioctl
#include <cassert>
#include <cstdarg>
namespace R=Stockfish::Eval::NNUE::MacRuntime;
static unsigned uploads, runs, firstView;
static const std::int16_t* expected[2];
extern "C" int test_ioctl(int, unsigned long request, ...) noexcept {
    va_list ap;va_start(ap,request);void* arg=va_arg(ap,void*);va_end(ap);
    if(request==PANGO_MAC_IOC_NNUE_UPLOAD) {
        auto& u=*static_cast<pango_mac_nnue_upload*>(arg);
        assert(u.view<2 && uploads<2);
        assert(std::memcmp(R::runtime().ddr+u.source_offset,expected[uploads],2048)==0);
        u.tag=100+uploads;++uploads;return 0;
    }
    if(request==PANGO_MAC_IOC_RUN_NNUE) {
        auto& j=*static_cast<pango_mac_nnue_job*>(arg);
        assert(j.first_view==firstView && j.bucket==11);
        j.score=2392;j.jobs=6;j.cycles=31441;++runs;return 0;
    }
    errno=EINVAL;return -1;
}
int main() {
    static std::uint8_t ddr[R::DdrBytes]{};
    std::int16_t a[1024],b[1024];
    for(unsigned i=0;i<1024;++i){a[i]=std::int16_t(i-512);b[i]=std::int16_t(600-i);}
    const char* setting=std::getenv("PIKAFISH_NNUE_FORCE_UPLOAD");
    const bool force=setting && std::strcmp(setting,"1")==0;
    for(bool swap:{false,true}) {
        auto& s=R::runtime();s.attempted=true;s.ready=true;s.fused=false;
        s.driverManaged=true;s.pipelineSupported=true;s.residentRegistered=true;
        s.deviceFd=123;s.ddr=ddr;s.batchEnabled=false;
        expected[0]=a;expected[1]=b;uploads=0;runs=0;
        for(unsigned v=0;v<2;++v) {
            auto& c=s.accumulators[v];c.identity=expected[v^unsigned(swap)];c.tag=v+1;
            std::memcpy(c.snapshot.data(),c.identity,2048);
        }
        firstView=force?0:unsigned(swap);
        R::Session session(R::Client::StageB);std::int32_t score=0;
        assert(session.pipeline(11,a,b,score) && score==2392);
        assert(runs==1 && uploads==(force?2u:0u));
    }
    std::printf("NNUE_FORCE_UPLOAD_DRIVER_MOCK_PASS cases=2 force=%u\n",force?1u:0u);
}
