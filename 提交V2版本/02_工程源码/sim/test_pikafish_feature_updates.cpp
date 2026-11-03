#include "pikafish_feature_updates.h"
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <vector>

namespace A = Stockfish::Eval::NNUE::StageAAccel;

int main() {
    // Independent legacy pointer-to-descriptor encoder is the differential oracle.
    const auto* psq = reinterpret_cast<const std::int8_t*>(0x20000000u);
    const auto* threat = reinterpret_cast<const std::int8_t*>(0x10000000u);
    std::uint32_t seed = 0x5f38a12u;
    unsigned cases = 0;
    for (unsigned n = 0; n <= 256; ++n) {
        A::FeatureUpdates terms(psq, threat);
        std::array<const std::int8_t*, 256> rows;
        std::array<std::int8_t, 256> signs;
        std::array<std::uint32_t, 256> expected;
        for (unsigned i = 0; i < n; ++i) {
            seed = seed * 1664525u + 1013904223u;
            bool useThreat = (seed & 0x10000u) != 0;
            auto* table = useThreat ? threat : psq;
            unsigned limit = useThreat ? 45547 : 16536;
            unsigned index = (seed >> 1) % limit;
            std::int8_t sign = seed & 1 ? 1 : -1;
            assert(terms.append(std::array<unsigned, 1>{index}, table, sign));
            rows[i] = table + index * 1024u;
            signs[i] = sign;
        }
        assert(terms.size() == n);
        if (n) {
            assert(A::encode_gather_descriptors(expected.data(), 256, rows.data(),
                                                signs.data(), n,
                                                reinterpret_cast<std::uintptr_t>(threat),
                                                reinterpret_cast<std::uintptr_t>(psq)));
            for (unsigned i = 0; i < n; ++i) assert(terms.data()[i] == expected[i]);
        }
        if (n == 256) {
            assert(!terms.append(std::array<unsigned, 1>{0}, psq, 1));
            assert(terms.size() == 256);
        }
        ++cases;
    }
    // Every row including both boundaries, both tables and both signs.
    for (auto* table : {psq, threat}) {
        unsigned limit = table == psq ? 16536 : 45547;
        for (unsigned index = 0; index < limit; ++index) {
            for (int sign : {-1, 1}) {
                A::FeatureUpdates terms(psq, threat);
                assert(terms.append(std::array<unsigned, 1>{index}, table, sign));
                unsigned expected = index | (table == psq ? 0x40000000u : 0u)
                    | (sign < 0 ? 0x80000000u : 0u);
                assert(terms.size() == 1 && terms.data()[0] == expected);
                ++cases;
            }
        }
    }
    A::FeatureUpdates terms(psq, threat);
    assert(terms.append(std::array<unsigned, 1>{7}, psq, 1));
    assert(!terms.append(std::array<unsigned, 2>{1, 16536}, psq, 1));
    assert(!terms.append(std::array<int, 1>{-1}, threat, 1));
    assert(!terms.append(std::array<unsigned, 1>{45547}, threat, -1));
    assert(!terms.append(std::array<unsigned, 1>{0}, psq, 0));
    assert(!terms.append(std::array<unsigned, 1>{0}, psq + 1024, 1));
    assert(!terms.append(std::vector<unsigned>(257, 0), psq, 1));
    assert(terms.size() == 1 && terms.data()[0] == 0x40000007u);
    assert(terms.append(std::array<unsigned, 1>{3}, threat, -1));
    assert(terms.size() == 2 && terms.data()[1] == 0x80000003u);
    std::printf("FEATURE_UPDATES_ALL_ROWS_SIGNS_CAPACITY_AND_INVALID_APPEND_PASS cases=%u\n", cases);
}
