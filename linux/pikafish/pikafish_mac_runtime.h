#ifndef PIKAFISH_MAC_RUNTIME_H_INCLUDED
#define PIKAFISH_MAC_RUNTIME_H_INCLUDED

#include <cstddef>
#include <cstdint>

namespace Stockfish::Eval::NNUE::MacRuntime {

constexpr std::uint32_t RegisterPhysical = 0x1fe10000u;
constexpr std::uint32_t DdrBusBase       = 0x1b000000u;
constexpr std::uint32_t DdrCpuAlias      = 0x9b000000u;
constexpr std::size_t   DdrBytes         = 0x00100000u;

constexpr std::size_t StageBModelOffset  = 0x00000000u;
constexpr std::size_t StageBModelBytes   = 0x00091000u;
constexpr std::size_t StageAInputOffset  = 0x000a0000u;
constexpr std::size_t StageAInputBytes   = 0x00000200u;
constexpr std::size_t StageAWeightOffset = 0x000a1000u;
constexpr std::size_t StageAWeightBytes  = 0x00010000u;
constexpr std::size_t StageAOutputOffset = 0x000b2000u;
constexpr std::size_t StageAOutputBytes  = 0x00000400u;
constexpr std::size_t StageAGatherBaseBytes = 2048;
constexpr std::size_t StageAGatherOutputBytes = 2048;
constexpr std::size_t StageBInputOffset  = 0x000f0000u;
constexpr std::size_t StageBInputBytes   = 0x00001000u;
constexpr std::size_t StageBOutputOffset = 0x000f1000u;
constexpr std::size_t StageBOutputBytes  = 0x00001000u;
constexpr std::size_t StageBResidentOffset = 0x000f2000u;
constexpr std::size_t StageBResidentBytes  = 0x00000040u;

static_assert(StageBModelOffset + StageBModelBytes <= StageAInputOffset);
static_assert(StageAInputOffset + StageAInputBytes <= StageAWeightOffset);
static_assert(StageAWeightOffset + StageAWeightBytes <= StageAOutputOffset);
static_assert(StageAOutputOffset + StageAOutputBytes <= StageBInputOffset);
static_assert(StageBInputOffset + StageBInputBytes <= StageBOutputOffset);
static_assert(StageBOutputOffset + StageBOutputBytes <= StageBResidentOffset);
static_assert(StageBResidentOffset + StageBResidentBytes <= DdrBytes);

enum class Client : std::uint8_t { StageA, StageB };

enum class ComputeMode : std::uint8_t { S16S16 = 0, S8S8 = 1, U8S8 = 2 };
enum class OutputFormat : std::uint8_t { S8 = 0, U8 = 1, S16 = 2, I32 = 3 };

struct Job {
    std::uint16_t pixels       = 0;
    std::uint16_t cin          = 0;
    std::uint16_t cout         = 0;
    std::uint8_t  outShift     = 0;
    ComputeMode   computeMode  = ComputeMode::S16S16;
    OutputFormat  outputFormat = OutputFormat::I32;
    bool          zeroBias     = false;
    std::size_t   inputOffset  = 0;
    std::size_t   weightOffset = 0;
    std::size_t   biasOffset   = 0;
    std::size_t   outputOffset = 0;
};

struct Statistics {
    bool          ready = false;
    bool          fused = false;
    bool          residentRegistered = false;
    std::uint64_t gatherCompleted = 0;
    std::uint64_t gatherCycles = 0;
    std::uint64_t gatherTerms = 0;
    std::uint64_t gatherHostNanoseconds = 0;
    std::uint64_t pipelineCompleted = 0;
    std::uint64_t pipelineCycles = 0;
    std::uint64_t pipelineUploads = 0;
    std::uint64_t pipelineFailures = 0;
    std::uint64_t pipelineRetries = 0;
    bool dedicated = false, cacheStatsValid = false;
    std::uint64_t cacheRuns=0,cacheHits=0,cacheReadWords=0,cacheModelRestores=0,cacheErrors=0;
    bool batchEnabled=false;
    bool batchResidentEnabled=false;
    std::uint64_t batchResidentRequested=0,batchResidentHits=0;
    std::uint64_t batchCalls=0,batchUpdates=0,batchHostNanoseconds=0,batchCycles=0;
    std::uint64_t batchExternalReadWords=0,batchLocalReadWords=0,batchExportWords=0;
    std::uint64_t batchCpuCopyoutBytes=0,batchSkippedIdentityBytes=0,batchDriverCopyoutBytes=0;
    std::uint64_t submitted[2]{};
    std::uint64_t completed[2]{};
    std::uint64_t failed[2]{};
};

// A session owns the single process-wide MAC lock for its complete lifetime.
// Callers therefore keep packing, all related submissions and result copying
// atomic with respect to every Stage A and Stage B client.
class Session final {
   public:
    explicit Session(Client client) noexcept;
    ~Session();

    Session(const Session&)            = delete;
    Session& operator=(const Session&) = delete;

    explicit operator bool() const noexcept { return ready_; }
    std::uint8_t* ddr(std::size_t offset, std::size_t bytes) const noexcept;
    bool submit(const Job& job, std::uint32_t* cycles = nullptr) noexcept;
    bool gather_available() const noexcept;
    bool gather(std::uint32_t terms, std::uint32_t* cycles = nullptr,
                const std::int16_t* accumulator = nullptr, unsigned view = 2) noexcept;
    bool register_model(std::size_t offset,std::size_t bytes) noexcept;
    bool pipeline_available() const noexcept;
    bool batch_available() const noexcept;
    bool queue_gather(const std::int16_t* base,std::int16_t* out,
                      const std::uint32_t* descriptors,std::uint32_t terms) noexcept;
    bool flush_batch(bool evaluate=false,unsigned bucket=0,
                      const std::int16_t* first=nullptr,const std::int16_t* second=nullptr,
                      std::int32_t* score=nullptr) noexcept;
    bool pipeline(unsigned bucket, const std::int16_t* first,
                  const std::int16_t* second, std::int32_t& score) noexcept;

   private:
    Client client_ = Client::StageA;
    bool   locked_ = false;
    bool   ready_  = false;
};

Statistics statistics() noexcept;

}  // namespace Stockfish::Eval::NNUE::MacRuntime

#endif
