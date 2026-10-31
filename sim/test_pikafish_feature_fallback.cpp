#include "pikafish_feature_updates.h"
#include "pikafish_mac_runtime.h"
#include "pango_mac_uapi.h"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <cstdarg>
namespace A = Stockfish::Eval::NNUE::StageAAccel;
static std::array<unsigned char, 1048576> shadow;
extern "C" int __wrap_open(const char*,int,...){return 71;}
extern "C" int __wrap_close(int){return 0;}
extern "C" void* __wrap_mmap(void*,std::size_t n,int,int,int,long){assert(n==shadow.size());return shadow.data();}
extern "C" int __wrap_munmap(void*,std::size_t){return 0;}
extern "C" int __wrap_ioctl(int fd,unsigned long command,...){
    assert(fd==71);va_list args;va_start(args,command);void* p=va_arg(args,void*);va_end(args);
    if(command==PANGO_MAC_IOC_GET_INFO){
        auto& info=*static_cast<pango_mac_info*>(p);
        info.abi_version=1;info.device_id=PANGO_MAC_ID;info.device_version=PANGO_MAC_VERSION;
        info.scratch_bytes=shadow.size();info.features=PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED;
    }else{
        assert(command==PANGO_MAC_IOC_RUN);
        auto& j=*static_cast<pango_mac_job*>(p);
        assert(j.pixels==1 && j.cout==256 && j.zero_bias);
        unsigned tiles=(j.cin+3)/4;
        for(unsigned lane=0;lane<256;lane++){
            int sum=0;
            for(unsigned term=0;term<j.cin;term++){
                int x=static_cast<std::int8_t>(shadow[j.input_offset+term/4*8+term%4*2]);
                unsigned at=((lane/32)*tiles+term/4)*128+((lane%32)/2*4+term%4)*2+lane%2;
                int w=static_cast<std::int8_t>(shadow[j.weight_offset+at]);sum+=x*w;
            }
            std::memcpy(shadow.data()+j.output_offset+lane*4,&sum,4);
        }
        j.status=2;j.cycles=100;
    }
    return 0;
}
int main() {
    setenv("PIKAFISH_STAGEA_MIN_TERMS", "1", 1);
    std::vector<std::int8_t> psq(16536u*1024u), threat(45547u*1024u);
    for (unsigned row = 0; row < 256; ++row)
        for (unsigned lane = 0; lane < 1024; ++lane) {
            psq[row*1024+lane] = static_cast<std::int8_t>((row*29+lane*11)%255-127);
            threat[row*1024+lane] = static_cast<std::int8_t>((row*3+lane*37)%255-127);
        }
    for (unsigned count : {1, 3, 8, 31, 256}) {
        A::FeatureUpdates terms(psq.data(), threat.data());
        std::array<short, 1024> base{}, out{}, expected{};
        for (unsigned lane = 0; lane < 1024; ++lane) base[lane] = static_cast<short>(lane*97);
        for (unsigned row = 0; row < count; ++row)
            assert(terms.append(std::array<unsigned, 1>{row}, row%2 ? psq.data() : threat.data(), row%3 ? 1 : -1));
        for (unsigned lane = 0; lane < 1024; ++lane) {
            unsigned sum = static_cast<unsigned short>(base[lane]);
            for (unsigned row = 0; row < count; ++row) {
                int value = (row%2 ? psq : threat)[row*1024+lane];
                sum += row%3 ? value : -value;
            }
            auto bits = static_cast<unsigned short>(sum);
            std::memcpy(&expected[lane], &bits, 2);
        }
        assert(terms.apply(base.data(), out.data()) && out == expected);
        assert(terms.apply(base.data(), base.data()) && base == expected);
    }
    std::puts("DIRECT_INDEX_LEGACY_DENSE_FALLBACK_WRAP16_AND_INPLACE_PASS");
}
