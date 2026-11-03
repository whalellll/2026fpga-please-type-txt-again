#ifndef PIKAFISH_STAGEA_ACCEL_H_INCLUDED
#define PIKAFISH_STAGEA_ACCEL_H_INCLUDED

#include <cstddef>
#include <cstdint>

namespace Stockfish::Eval::NNUE::StageAAccel {

constexpr std::size_t L1              = 1024;
constexpr std::size_t TileWidth       = 256;
constexpr std::size_t MaxTerms        = 256;
constexpr std::size_t MaxInputBytes   = 512;
constexpr std::size_t MaxWeightBytes  = 65536;

bool encode_gather_descriptors(std::uint32_t* descriptors, std::size_t capacity,
    const std::int8_t* const* rows, const std::int8_t* coefficients,
    std::size_t count, std::uintptr_t threatBase, std::uintptr_t psqBase) noexcept;
bool bind_gather_model(const void* threat, std::size_t threatBytes, std::uint64_t threatPhysical,
    const void* psq, std::size_t psqBytes, std::uint64_t psqPhysical) noexcept;
void materialize() noexcept;

// Pure layout transform shared by the runtime and the host regression.
// Each row points at one official feature-major [1024] int8 weight row.
bool pack_tile(std::uint8_t*             input,
               std::size_t               inputCapacity,
               std::uint8_t*             weights,
               std::size_t               weightCapacity,
               const std::int8_t* const* rows,
               const std::int8_t*        coefficients,
               std::size_t               count,
               unsigned                  tile) noexcept;

// Four 32-byte feature rows per MAC weight line. Requires the row-major
// layout mode in the dense MAC DMA loader.
bool pack_tile_rowmajor(std::uint8_t*             input,
                        std::size_t               inputCapacity,
                        std::uint8_t*             weights,
                        std::size_t               weightCapacity,
                        const std::int8_t* const* rows,
                        const std::int8_t*        coefficients,
                        std::size_t               count,
                        unsigned                  tile) noexcept;

// out = base + sum(coefficients[i] * rows[i]). The hardware path is used only
// when it is available and the request is large enough to amortize packing.
// false means the caller must execute its existing scalar/SIMD fallback.
bool apply(const std::int16_t*            base,
           std::int16_t*                  out,
           const std::int8_t* const*      rows,
           const std::int8_t*             coefficients,
           std::size_t                    count, int view = -1) noexcept;

}  // namespace Stockfish::Eval::NNUE::StageAAccel

#endif
