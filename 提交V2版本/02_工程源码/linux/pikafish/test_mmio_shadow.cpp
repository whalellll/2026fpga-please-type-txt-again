#include "pikafish_mmio_shadow.h"

#include <array>
#include <cstdint>
#include <cstdio>

using Stockfish::Eval::NNUE::MacRuntime::MmioShadow::collect;
using Stockfish::Eval::NNUE::MacRuntime::MmioShadow::publish;

int main() {
    std::array<std::uint8_t, 64> shadow{};
    std::array<std::uint32_t, 16> physical{};
    for (std::size_t i = 0; i < shadow.size(); ++i)
        shadow[i] = static_cast<std::uint8_t>(i * 7u + 3u);
    if (!publish(physical.data(), shadow.data(), 16, 24, shadow.size()))
        return 1;
    for (std::size_t i = 0; i < physical.size(); ++i) {
        if (i < 4 || i >= 10) {
            if (physical[i] != 0)
                return 2;
        } else {
            const std::size_t p = i * 4;
            const std::uint32_t expected = std::uint32_t(shadow[p]) |
                (std::uint32_t(shadow[p + 1]) << 8) |
                (std::uint32_t(shadow[p + 2]) << 16) |
                (std::uint32_t(shadow[p + 3]) << 24);
            if (physical[i] != expected)
                return 3;
        }
    }
    shadow.fill(0);
    if (!collect(physical.data(), shadow.data(), 16, 24, shadow.size()))
        return 4;
    for (std::size_t i = 0; i < shadow.size(); ++i) {
        const std::uint8_t expected = i >= 16 && i < 40 ?
            static_cast<std::uint8_t>(i * 7u + 3u) : 0u;
        if (shadow[i] != expected)
            return 5;
    }
    if (publish(physical.data(), shadow.data(), 2, 4, shadow.size()) ||
        publish(physical.data(), shadow.data(), 0, 5, shadow.size()) ||
        collect(physical.data(), shadow.data(), 60, 8, shadow.size()))
        return 6;
    std::puts("PIKAFISH_MMIO_SHADOW_PASS");
    return 0;
}
