#include "portable_u128.h"

#include <cstdint>
#include <iostream>

using Stockfish::PortableUInt128;

namespace {

using Native = unsigned __int128;
using u64    = std::uint64_t;

u64 next_random(u64& state) {
    state ^= state << 13;
    state ^= state >> 7;
    state ^= state << 17;
    return state;
}

Native native_value(u64 low, u64 high) {
    return (Native(high) << 64) | Native(low);
}

bool equal(PortableUInt128 actual, Native expected) {
    return actual.low() == static_cast<u64>(expected)
        && actual.high() == static_cast<u64>(expected >> 64);
}

}  // namespace

int main() {
    u64 state = 0x51a7c3e29b4d680fULL;

    for (unsigned i = 0; i < 200000; ++i)
    {
        const u64 aLow  = next_random(state);
        const u64 aHigh = next_random(state);
        const u64 bLow  = next_random(state);
        const u64 bHigh = next_random(state);
        const auto a    = (PortableUInt128(aHigh) << 64) | PortableUInt128(aLow);
        const auto b    = (PortableUInt128(bHigh) << 64) | PortableUInt128(bLow);
        const Native na = native_value(aLow, aHigh);
        const Native nb = native_value(bLow, bHigh);
        const unsigned shift = static_cast<unsigned>(next_random(state) % 128);

        if (!equal(a + b, na + nb) || !equal(a - b, na - nb) || !equal(a * b, na * nb)
            || !equal(a & b, na & nb) || !equal(a | b, na | nb) || !equal(a ^ b, na ^ nb)
            || !equal(~a, ~na) || !equal(-a, -na) || !equal(a << shift, na << shift)
            || !equal(a >> shift, na >> shift) || bool(a) != bool(na)
            || (a < b) != (na < nb))
        {
            std::cerr << "portable u128 mismatch at vector " << i << '\n';
            return 1;
        }
    }

    std::cout << "PIKAFISH_PORTABLE_U128_PASS vectors=200000\n";
    return 0;
}
