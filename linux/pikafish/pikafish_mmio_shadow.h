#ifndef PIKAFISH_MMIO_SHADOW_H_INCLUDED
#define PIKAFISH_MMIO_SHADOW_H_INCLUDED

#include <cstddef>
#include <cstdint>
#include <cstring>

// The V3.5 uncached DDR alias accepts aligned word accesses. Keep all byte
// packing in ordinary RAM and cross the alias with full 32-bit transfers.
namespace Stockfish::Eval::NNUE::MacRuntime::MmioShadow {

inline bool aligned_range(std::size_t offset, std::size_t bytes,
                          std::size_t capacity) noexcept {
    return (offset & 3u) == 0u && (bytes & 3u) == 0u &&
           offset <= capacity && bytes <= capacity - offset;
}

inline bool publish(volatile std::uint32_t* physical,
                    const std::uint8_t* shadow, std::size_t offset,
                    std::size_t bytes, std::size_t capacity) noexcept {
    if (!physical || !shadow || !aligned_range(offset, bytes, capacity))
        return false;
    for (std::size_t i = 0; i < bytes; i += 4u) {
        std::uint32_t word;
        std::memcpy(&word, shadow + offset + i, sizeof(word));
        physical[(offset + i) / 4u] = word;
    }
    __sync_synchronize();
    return true;
}

inline bool collect(const volatile std::uint32_t* physical,
                    std::uint8_t* shadow, std::size_t offset,
                    std::size_t bytes, std::size_t capacity) noexcept {
    if (!physical || !shadow || !aligned_range(offset, bytes, capacity))
        return false;
    __sync_synchronize();
    for (std::size_t i = 0; i < bytes; i += 4u) {
        const std::uint32_t word = physical[(offset + i) / 4u];
        std::memcpy(shadow + offset + i, &word, sizeof(word));
    }
    return true;
}

}  // namespace Stockfish::Eval::NNUE::MacRuntime::MmioShadow

#endif
