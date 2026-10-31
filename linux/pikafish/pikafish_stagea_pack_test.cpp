#include "pikafish_stagea_accel.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <vector>

using namespace Stockfish::Eval::NNUE;

static std::int8_t packed_input(const std::uint8_t* input, std::size_t feature) {
    return static_cast<std::int8_t>(input[(feature / 4u) * 8u + (feature % 4u) * 2u]);
}

static std::int8_t packed_weight(const std::uint8_t* weights,
                                 std::size_t         count,
                                 std::size_t         feature,
                                 std::size_t         lane) {
    const std::size_t ciTiles = (count + 3u) / 4u;
    const std::size_t coTile  = lane / 32u;
    const std::size_t pair    = (lane % 32u) / 2u;
    const std::size_t parity  = lane & 1u;
    const std::size_t ciTile  = feature / 4u;
    const std::size_t ci      = feature % 4u;
    const std::size_t slot = (coTile * ciTiles + ciTile) * 128u
                           + (pair * 4u + ci) * 2u + parity;
    return static_cast<std::int8_t>(weights[slot]);
}

static std::int8_t rowmajor_weight(const std::uint8_t* weights,
                                   std::size_t count, std::size_t feature,
                                   std::size_t lane) {
    const std::size_t ciTiles = (count + 3u) / 4u;
    const std::size_t coTile = lane / 32u;
    const std::size_t ciTile = feature / 4u;
    const std::size_t ci = feature % 4u;
    return static_cast<std::int8_t>(
      weights[(coTile * ciTiles + ciTile) * 128u + ci * 32u + lane % 32u]);
}

int main() {
    constexpr std::array<std::size_t, 12> Counts = {1, 2, 3, 4, 5, 8, 31, 32, 33, 64, 132, 256};
    std::vector<std::int8_t> storage(StageAAccel::MaxTerms * StageAAccel::L1);
    std::array<const std::int8_t*, StageAAccel::MaxTerms> rows{};
    std::array<std::int8_t, StageAAccel::MaxTerms> coefficients{};
    std::array<std::uint8_t, StageAAccel::MaxInputBytes> input{};
    std::array<std::uint8_t, StageAAccel::MaxWeightBytes + 1> weights{};
    std::array<std::uint8_t, StageAAccel::MaxWeightBytes + 1> rowMajorWeights{};

    for (std::size_t feature = 0; feature < StageAAccel::MaxTerms; ++feature)
    {
        rows[feature]         = storage.data() + feature * StageAAccel::L1;
        coefficients[feature] = feature % 3u == 0 ? -1 : 1;
        for (std::size_t lane = 0; lane < StageAAccel::L1; ++lane)
            storage[feature * StageAAccel::L1 + lane] =
              static_cast<std::int8_t>((feature * 17u + lane * 29u + 11u) & 0xffu);
    }

    for (std::size_t count : Counts)
        for (unsigned tile = 0; tile < StageAAccel::L1 / StageAAccel::TileWidth; ++tile)
          for (unsigned offset = 0; offset < 2; ++offset)
        {
            input.fill(0xa5u);
            weights.fill(0xa5u);
            std::uint8_t* const packedWeights = weights.data() + offset;
            if (!StageAAccel::pack_tile(input.data(), input.size(), packedWeights,
                                        weights.size() - offset, rows.data(), coefficients.data(), count,
                                        tile))
                return 1;
            rowMajorWeights.fill(0xa5u);
            std::uint8_t* const rowMajor = rowMajorWeights.data() + offset;
            if (!StageAAccel::pack_tile_rowmajor(input.data(), input.size(), rowMajor,
                                                  rowMajorWeights.size() - offset,
                                                  rows.data(), coefficients.data(), count,
                                                  tile))
                return 6;
            const std::size_t paddedCount = ((count + 3u) / 4u) * 4u;
            for (std::size_t feature = 0; feature < paddedCount; ++feature)
            {
                const std::size_t offset = (feature / 4u) * 8u + (feature % 4u) * 2u;
                if (input[offset + 1u] != 0u
                    || (feature >= count && input[offset] != 0u))
                    return 4;
                if (feature >= count)
                    for (std::size_t lane = 0; lane < StageAAccel::TileWidth; ++lane)
                        if (packed_weight(packedWeights, count, feature, lane) != 0)
                            return 5;
                if (feature >= count)
                    for (std::size_t lane = 0; lane < StageAAccel::TileWidth; ++lane)
                        if (rowmajor_weight(rowMajor, count, feature, lane) != 0)
                            return 7;
            }
            for (std::size_t lane = 0; lane < StageAAccel::TileWidth; ++lane)
            {
                std::int32_t packed = 0;
                std::int32_t direct = 0;
                for (std::size_t feature = 0; feature < count; ++feature)
                {
                    packed += static_cast<std::int32_t>(packed_input(input.data(), feature))
                            * static_cast<std::int32_t>(
                                packed_weight(packedWeights, count, feature, lane));
                    direct += static_cast<std::int32_t>(coefficients[feature])
                            * static_cast<std::int32_t>(
                                rows[feature][tile * StageAAccel::TileWidth + lane]);
                }
                if (packed != direct)
                {
                    std::fprintf(stderr,
                                 "FAIL count=%u tile=%u lane=%u packed=%d direct=%d\n",
                                 static_cast<unsigned>(count), tile,
                                 static_cast<unsigned>(lane), packed, direct);
                    return 2;
                }
                for (std::size_t feature = 0; feature < count; ++feature)
                    if (rowmajor_weight(rowMajor, count, feature, lane)
                        != packed_weight(packedWeights, count, feature, lane))
                        return 8;
            }
        }

    if (StageAAccel::pack_tile(input.data(), input.size(), weights.data(), weights.size(),
                               rows.data(), coefficients.data(), 0, 0)
        || StageAAccel::pack_tile(input.data(), input.size(), weights.data(), weights.size(),
                                  rows.data(), coefficients.data(),
                                  StageAAccel::MaxTerms + 1, 0)
        || StageAAccel::pack_tile(input.data(), input.size(), weights.data(), weights.size(),
                                  rows.data(), coefficients.data(), 1, 4))
        return 3;

    if (StageAAccel::pack_tile_rowmajor(input.data(), input.size(), rowMajorWeights.data(),
                                        rowMajorWeights.size(), rows.data(), coefficients.data(), 0, 0)
        || StageAAccel::pack_tile_rowmajor(input.data(), input.size(), rowMajorWeights.data(),
                                           rowMajorWeights.size(), rows.data(), coefficients.data(),
                                           StageAAccel::MaxTerms + 1, 0)
        || StageAAccel::pack_tile_rowmajor(input.data(), input.size(), rowMajorWeights.data(),
                                           rowMajorWeights.size(), rows.data(), coefficients.data(), 1, 4)
        || StageAAccel::pack_tile_rowmajor(input.data(), input.size(), rowMajorWeights.data(),
                                           127, rows.data(), coefficients.data(), 4, 0))
        return 9;

    // Exercise both fallback alignments after the word-oriented fast path:
    // halfword-aligned rows at +2 and byte-only rows at +1.
    for (std::size_t sourceOffset : {2u, 1u})
    {
        for (std::size_t feature = 0; feature < 4; ++feature)
            rows[feature] = storage.data() + feature * StageAAccel::L1 + sourceOffset;
        for (unsigned tile = 0; tile < StageAAccel::L1 / StageAAccel::TileWidth; ++tile)
        {
            if (!StageAAccel::pack_tile(input.data(), input.size(), weights.data(),
                                        weights.size(), rows.data(), coefficients.data(), 4, tile))
                return 10;
            for (std::size_t lane = 0; lane < StageAAccel::TileWidth; ++lane)
                for (std::size_t feature = 0; feature < 4; ++feature)
                    if (packed_weight(weights.data(), 4, feature, lane)
                        != rows[feature][tile * StageAAccel::TileWidth + lane])
                        return 11;
        }
    }

    std::puts("PIKAFISH_STAGEA_PACK_TEST_PASS counts=12 tiles=48 alignments=2 lanes=24576");
    return 0;
}
