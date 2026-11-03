#ifndef PIKAFISH_MAC_BACKEND_POLICY_H
#define PIKAFISH_MAC_BACKEND_POLICY_H
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <cstring>
namespace Stockfish::Eval::NNUE::MacRuntime {
struct BackendPolicy {
    bool mmioShadow=false,requireDriver=false;
    std::uint32_t requiredFeatures=0;
};
inline bool backend_policy(const char* backend,const char* device,const char* strict,
                           const char* features,BackendPolicy& out) noexcept {
    out={};
    out.mmioShadow=backend && std::strcmp(backend,"mmio-shadow")==0;
    const bool driver=backend && std::strcmp(backend,"driver")==0;
    if(backend && *backend && !out.mmioShadow && !driver)return false;
    if(features && *features) {
        char* end=nullptr;
        if(*features<'0' || *features>'9')return false;
        errno=0;
        const auto value=std::strtoul(features,&end,0);
        if(errno || end==features || *end || value>UINT32_MAX)return false;
        out.requiredFeatures=static_cast<std::uint32_t>(value);
    }
    out.requireDriver=driver || (device && *device) || out.requiredFeatures ||
        (strict && std::strcmp(strict,"0")!=0);
    return !(out.requireDriver && out.mmioShadow);
}
}
#endif
