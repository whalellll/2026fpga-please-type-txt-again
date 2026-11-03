#include "pikafish_mac_backend_policy.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
using namespace Stockfish::Eval::NNUE::MacRuntime;
int main() {
    BackendPolicy p;
    assert(backend_policy(nullptr,nullptr,nullptr,nullptr,p) && !p.requireDriver);
    assert(backend_policy("driver",nullptr,nullptr,"0x60",p) && p.requireDriver && p.requiredFeatures==0x60);
    assert(backend_policy(nullptr,"/dev/test",nullptr,nullptr,p) && p.requireDriver);
    assert(backend_policy("mmio-shadow",nullptr,"0",nullptr,p) && p.mmioShadow);
    assert(!backend_policy("mmio-shadow",nullptr,"1",nullptr,p));
    assert(!backend_policy("mmio-shadow",nullptr,nullptr,"0x60",p));
    assert(!backend_policy("legacy-devmem",nullptr,nullptr,nullptr,p));
    for(const char* invalid: {"-1","+1","0x60garbage","4294967296"," 96","\t96"})
        assert(!backend_policy("driver",nullptr,nullptr,invalid,p));
    std::puts("PIKAFISH_MAC_BACKEND_POLICY_TEST_PASS");
}
