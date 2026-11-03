#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include "pikafish_stagea_accel.h"
using namespace Stockfish::Eval::NNUE::StageAAccel;
int main() {
    constexpr std::uintptr_t threat=0x20002000,psq=0x22f45000;
    auto ptr=[](std::uintptr_t p){return reinterpret_cast<const std::int8_t*>(p);};
    std::array<const std::int8_t*,4> rows{ptr(threat),ptr(threat+45546*1024u),ptr(psq+16535*1024u),ptr(psq)};
    std::array<std::int8_t,4> signs{1,-1,1,-1};
    std::array<std::uint32_t,4> desc{};
    assert(encode_gather_descriptors(desc.data(),desc.size(),rows.data(),signs.data(),4,threat,psq));
    assert(desc[0]==0 && desc[1]==(0x80000000u|45546) && desc[2]==(0x40000000u|16535) && desc[3]==0xc0000000u);
    rows[0]=ptr(threat+1);assert(!encode_gather_descriptors(desc.data(),4,rows.data(),signs.data(),4,threat,psq));
    rows[0]=ptr(threat+45547*1024u);assert(!encode_gather_descriptors(desc.data(),4,rows.data(),signs.data(),4,threat,psq));
    rows[0]=ptr(psq+16536*1024u);assert(!encode_gather_descriptors(desc.data(),4,rows.data(),signs.data(),4,threat,psq));
    rows[0]=ptr(threat);signs[0]=0;assert(!encode_gather_descriptors(desc.data(),4,rows.data(),signs.data(),4,threat,psq));
    signs[0]=2;assert(!encode_gather_descriptors(desc.data(),4,rows.data(),signs.data(),4,threat,psq));
    signs[0]=1;assert(!encode_gather_descriptors(desc.data(),3,rows.data(),signs.data(),4,threat,psq));
    assert(!bind_gather_model(ptr(threat),45547*1024u,0x10002004,ptr(psq),16536*1024u,0x12f45000));
    assert(bind_gather_model(ptr(threat),45547*1024u,0x10002000,ptr(psq),16536*1024u,0x12f45000));
    std::puts("STAGEA_GATHER_DESCRIPTORS_PASS");
}
