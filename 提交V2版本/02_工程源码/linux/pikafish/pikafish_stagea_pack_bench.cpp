#include <array>
#include <chrono>
#include <cstdint>
#include <cstdio>

#include "pikafish_stagea_accel.h"

int main() {
    using namespace Stockfish::Eval::NNUE;
    std::array<std::int8_t, StageAAccel::MaxTerms * StageAAccel::L1> storage{};
    std::array<const std::int8_t*, StageAAccel::MaxTerms> rows{};
    std::array<std::int8_t, StageAAccel::MaxTerms> coefficients{};
    std::array<std::uint8_t, StageAAccel::MaxInputBytes> input{};
    std::array<std::uint8_t, StageAAccel::MaxWeightBytes> weights{};
    for (unsigned feature = 0; feature < rows.size(); ++feature) {
        rows[feature] = storage.data() + feature * StageAAccel::L1;
        coefficients[feature] = feature & 1 ? -1 : 1;
        for (unsigned lane = 0; lane < StageAAccel::L1; ++lane)
            storage[feature * StageAAccel::L1 + lane] =
                static_cast<std::int8_t>((feature * 31 + lane * 7) & 255);
    }
    constexpr unsigned rounds = 500;
    constexpr unsigned terms = 32;
    for (unsigned layout = 0; layout < 2; ++layout) {
        std::uint64_t checksum = 0;
        const auto started = std::chrono::steady_clock::now();
        for (unsigned repeat = 0; repeat < rounds; ++repeat)
            for (unsigned tile = 0; tile < StageAAccel::L1 / StageAAccel::TileWidth; ++tile) {
                const bool ok = layout == 0
                  ? StageAAccel::pack_tile(input.data(), input.size(), weights.data(),
                                            weights.size(), rows.data(), coefficients.data(),
                                            terms, tile)
                  : StageAAccel::pack_tile_rowmajor(input.data(), input.size(), weights.data(),
                                                     weights.size(), rows.data(),
                                                     coefficients.data(), terms, tile);
                if (!ok)
                    return 1;
                checksum += weights[(repeat * 29 + tile * 127) % 8192];
            }
        const auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now() - started).count();
        std::printf("STAGEA_PACK_BENCH layout=%s calls=%zu total_us=%lld us_per_call=%.3f checksum=%llu\n",
                    layout == 0 ? "interleaved" : "rowmajor",
                    rounds * (StageAAccel::L1 / StageAAccel::TileWidth),
                    static_cast<long long>(elapsed),
                    double(elapsed) / (rounds * (StageAAccel::L1 / StageAAccel::TileWidth)),
                    static_cast<unsigned long long>(checksum));
    }
}
