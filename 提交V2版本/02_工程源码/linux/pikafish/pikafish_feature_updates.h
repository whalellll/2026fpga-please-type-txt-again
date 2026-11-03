#ifndef PIKAFISH_FEATURE_UPDATES_H_INCLUDED
#define PIKAFISH_FEATURE_UPDATES_H_INCLUDED

#include "pikafish_stagea_accel.h"
#include <array>
#include <cstddef>
#include <cstdint>

namespace Stockfish::Eval::NNUE::StageAAccel {

// Same public descriptor format as Stage A; no weight-pointer round trip.
// Only [0,count_) is initialized/read. Fallback reconstructs the legacy rows
// lazily, retaining older devices and scalar materialization semantics.
class FeatureUpdates {
    std::array<std::uint32_t, MaxTerms> descriptors_;
    const std::int8_t* psq_;
    const std::int8_t* threat_;
    std::size_t count_ = 0;

public:
    FeatureUpdates(const std::int8_t* psq, const std::int8_t* threat) noexcept
        : psq_(psq), threat_(threat) {}

    template<typename List>
    bool append(const List& indices, const std::int8_t* weights, int coefficient) noexcept {
        const auto size = static_cast<std::size_t>(indices.size());
        if ((coefficient != 1 && coefficient != -1) || size > MaxTerms - count_
            || !weights || (weights != psq_ && weights != threat_))
            return false;
        const bool psq = weights == psq_;
        const std::uint32_t limit = psq ? 16536u : 45547u;
        const std::uint32_t flags = (psq ? 0x40000000u : 0u)
            | (coefficient < 0 ? 0x80000000u : 0u);
        // Commit count only after every index passes bounds checking.
        for (std::size_t i = 0; i < size; ++i) {
            const auto index = static_cast<std::uint64_t>(indices[i]);
            if (index >= limit) return false;
            descriptors_[count_ + i] = flags | static_cast<std::uint32_t>(index);
        }
        count_ += size;
        return true;
    }

    const std::uint32_t* data() const noexcept { return descriptors_.data(); }
    std::size_t size() const noexcept { return count_; }
    bool apply(const std::int16_t* base, std::int16_t* out, int view = -1) const noexcept;
};

} // namespace Stockfish::Eval::NNUE::StageAAccel
#endif
