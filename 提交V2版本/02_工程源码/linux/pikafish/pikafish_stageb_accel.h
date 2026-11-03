#ifndef PIKAFISH_STAGEB_ACCEL_H_INCLUDED
#define PIKAFISH_STAGEB_ACCEL_H_INCLUDED

#include <cstddef>
#include <cstdint>

namespace Stockfish::Eval::NNUE::StageBAccel {

constexpr std::size_t InputDimensions  = 1024;
constexpr std::size_t OutputDimensions = 32;
constexpr std::size_t StackCount       = 16;

struct ModelBinding {
    std::uint8_t  decodedStreamSha256[32]{};
    std::uint32_t mlpsBytes = 0;
    std::uint32_t mlpsCrc32 = 0;
};

struct Statistics {
    std::uint64_t prepareCalls = 0;
    std::uint64_t copiedBytes = 0;
    std::uint64_t residentHits = 0;
    std::uint64_t prepareNanoseconds = 0;
    std::uint64_t evaluations = 0;
    std::uint64_t jobs = 0;
    std::uint64_t macCycles = 0;
    std::uint64_t hostNanoseconds = 0;
    std::uint64_t fallbacks = 0;
    std::uint64_t verifyMismatches = 0;
    std::uint64_t checkpoints = 0;
    std::uint64_t checkpointFailures = 0;
};

// Called only after the PFF1 header, sections and MLPS CRC have passed. A
// failure is non-fatal and permanently leaves Stage B on the official CPU FC0.
bool prepare(const ModelBinding& binding) noexcept;

// Returns true only after all four hardware tiles completed and output[32]
// was committed. false requires a complete official CPU FC0 recomputation.
bool fc0(unsigned bucket, const std::uint8_t* input, std::int32_t* output) noexcept;

bool forward_accumulators(unsigned bucket, const std::int16_t* first,
                          const std::int16_t* second, const std::uint8_t* token) noexcept;
bool consume_pipeline(unsigned bucket, const std::uint8_t* token, std::int32_t& score) noexcept;
void verify_pipeline(unsigned bucket, const std::uint8_t* token, std::int32_t cpu) noexcept;

bool verify_mode() noexcept;
void verify(unsigned bucket, const std::int32_t* hardware,
            const std::int32_t* officialCpu) noexcept;

// Revalidates the complete immutable PFSB image in shared DDR, its resident
// commit record, the model binding and accounting invariants. This is an
// game/soak boundary operation, not part of the per-node hot path. It is a
// successful no-op when Stage B was never enabled. A failure permanently
// disables Stage B for the process; callers continue through the official
// CPU FC0 path.
bool checkpoint() noexcept;

Statistics statistics() noexcept;
void report_statistics() noexcept;

#if defined(PIKAFISH_STAGEB_TESTING)
void reset_for_test() noexcept;
#endif

}  // namespace Stockfish::Eval::NNUE::StageBAccel

#endif
