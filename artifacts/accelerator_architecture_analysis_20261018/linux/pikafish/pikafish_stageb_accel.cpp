#include "pikafish_stageb_accel.h"

#include "pf_mlp_mac_pack.h"
#include "pikafish_mac_runtime.h"

#include <array>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>

#if defined(PIKAFISH_STAGEB_ACCEL)
    #include <fcntl.h>
    #include <sys/mman.h>
    #include <sys/stat.h>
    #include <unistd.h>
#endif

namespace Stockfish::Eval::NNUE::StageBAccel {

namespace {

#if defined(PIKAFISH_STAGEB_ACCEL)
enum class Mode { Disabled, Verify, Enabled };

struct Runtime {
    std::mutex mutex;
    Mode       mode = Mode::Disabled;
    bool       modeParsed = false;
    bool       attempted = false;
    bool       ready = false;
    bool       fallbackReported = false;
    bool       activeReported = false;
    ModelBinding binding{};
    std::array<std::array<std::int32_t, OutputDimensions>, StackCount> biases{};
    std::uint64_t evaluations = 0;
    std::uint64_t jobs = 0;
    std::uint64_t cycles = 0;
    std::uint64_t prepareCalls = 0;
    std::uint64_t copiedBytes = 0;
    std::uint64_t residentHits = 0;
    std::uint64_t prepareNanoseconds = 0;
    std::uint64_t hostNanoseconds = 0;
    std::uint64_t fallbacks = 0;
    std::uint64_t verifyMismatches = 0;
    std::uint64_t checkpoints = 0;
    std::uint64_t checkpointFailures = 0;
    std::uint32_t payloadCrc = 0;
    unsigned lastBucket = 0;
};

constexpr std::uint32_t ResidentMagic = 0x34524650u;  // 'PFR4'
constexpr std::uint32_t ResidentVersion = 0x00010000u;
constexpr std::size_t ResidentCrcOffset = MacRuntime::StageBResidentBytes - 4u;

using Clock = std::chrono::steady_clock;

Runtime& runtime() {
    static Runtime state;
    return state;
}

std::uint32_t read_u32(const std::uint8_t* p) noexcept {
    return static_cast<std::uint32_t>(p[0]) | (static_cast<std::uint32_t>(p[1]) << 8)
         | (static_cast<std::uint32_t>(p[2]) << 16)
         | (static_cast<std::uint32_t>(p[3]) << 24);
}

void write_u32(std::uint8_t* p, std::uint32_t value) noexcept {
    p[0] = static_cast<std::uint8_t>(value);
    p[1] = static_cast<std::uint8_t>(value >> 8);
    p[2] = static_cast<std::uint8_t>(value >> 16);
    p[3] = static_cast<std::uint8_t>(value >> 24);
}

std::int32_t read_i32(const std::uint8_t* p) noexcept {
    const std::uint32_t value = read_u32(p);
    std::int32_t result = 0;
    std::memcpy(&result, &value, sizeof(result));
    return result;
}

std::uint32_t crc32(const std::uint8_t* data, std::size_t bytes) noexcept {
    std::uint32_t crc = 0xffffffffu;
    for (std::size_t i = 0; i < bytes; ++i)
    {
        crc ^= data[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return crc ^ 0xffffffffu;
}

Mode parse_mode() noexcept {
    const char* value = std::getenv("PIKAFISH_STAGEB_ACCEL");
    if (!value || std::strcmp(value, "1") == 0)
        return Mode::Enabled;
    if (std::strcmp(value, "verify") == 0)
        return Mode::Verify;
    return Mode::Disabled;
}

const char* mode_name(Mode mode) noexcept {
    return mode == Mode::Verify ? "verify" : mode == Mode::Enabled ? "1" : "0";
}

void fallback(Runtime& state, const char* reason) noexcept {
    state.ready = false;
    ++state.fallbacks;
    if (!state.fallbackReported)
    {
        state.fallbackReported = true;
        std::fprintf(stderr, "PIKAFISH_STAGEB_CPU_FALLBACK reason=%s\n", reason);
    }
}

std::array<std::uint8_t, MacRuntime::StageBResidentBytes>
make_resident_stamp(const ModelBinding& binding, std::uint32_t payloadCrc) noexcept {
    std::array<std::uint8_t, MacRuntime::StageBResidentBytes> stamp{};
    write_u32(stamp.data() + 0, ResidentMagic);
    write_u32(stamp.data() + 4, ResidentVersion);
    write_u32(stamp.data() + 8, PF_STAGEB_PACK_VERSION);
    write_u32(stamp.data() + 12, PF_STAGEB_PACK_USED_BYTES);
    write_u32(stamp.data() + 16, payloadCrc);
    write_u32(stamp.data() + 20, binding.mlpsBytes);
    write_u32(stamp.data() + 24, binding.mlpsCrc32);
    std::memcpy(stamp.data() + 28, binding.decodedStreamSha256, 32);
    write_u32(stamp.data() + ResidentCrcOffset,
              crc32(stamp.data(), ResidentCrcOffset));
    return stamp;
}

bool resident_matches(const std::uint8_t* ddr, const std::uint8_t* resident,
                      const std::uint8_t* pack,
                      const std::array<std::uint8_t,
                                       MacRuntime::StageBResidentBytes>& expected) noexcept {
    if (!ddr || !resident || std::memcmp(resident, expected.data(), expected.size()) != 0
        || std::memcmp(ddr, pack, PF_STAGEB_H_HEADER_CRC32 + 4u) != 0)
        return false;
    for (unsigned stack = 0; stack < StackCount; ++stack)
        if (std::memcmp(ddr + pf_stageb_stack_offset(stack),
                        pack + pf_stageb_stack_offset(stack),
                        PF_STAGEB_S_FC0_CRC32 + 4u) != 0)
            return false;
    return true;
}

void report_active(Runtime& state) noexcept {
    if (!state.activeReported)
    {
        state.activeReported = true;
        std::fprintf(stderr,
                     "PIKAFISH_STAGEB_ACCEL_ACTIVE bucket=%u jobs=4 mode=%s "
                     "total_jobs=%llu cycles=%llu\n",
                     state.lastBucket, mode_name(state.mode),
                     static_cast<unsigned long long>(state.jobs),
                     static_cast<unsigned long long>(state.cycles));
    }
}

bool validate_pack(const std::uint8_t* pack, std::size_t bytes,
                   const ModelBinding& binding, std::uint32_t& payloadCrc) noexcept {
    if (!pack || bytes != PF_STAGEB_PACK_USED_BYTES
        || read_u32(pack + PF_STAGEB_H_MAGIC) != PF_STAGEB_PACK_MAGIC
        || read_u32(pack + PF_STAGEB_H_VERSION) != PF_STAGEB_PACK_VERSION
        || read_u32(pack + PF_STAGEB_H_HEADER_BYTES) != PF_STAGEB_HEADER_BYTES
        || read_u32(pack + PF_STAGEB_H_USED_BYTES) != PF_STAGEB_PACK_USED_BYTES
        || read_u32(pack + PF_STAGEB_H_STACK_COUNT) != PF_STAGEB_STACK_COUNT
        || read_u32(pack + PF_STAGEB_H_STACK_SLOT_BYTES) != PF_STAGEB_STACK_SLOT_BYTES
        || read_u32(pack + PF_STAGEB_H_STACK_BASE) != PF_STAGEB_STACK_BASE
        || read_u32(pack + PF_STAGEB_H_FC0_OFFSET) != PF_STAGEB_FC0_PACKED_OFFSET
        || read_u32(pack + PF_STAGEB_H_FC0_TILE_BYTES) != PF_STAGEB_FC0_TILE_BYTES
        || read_u32(pack + PF_STAGEB_H_FC0_TILE_COUNT) != PF_STAGEB_FC0_TILE_COUNT
        || read_u32(pack + PF_STAGEB_H_FLAGS)
             != (PF_STAGEB_FLAG_MAC_NATIVE_FC0 | PF_STAGEB_FLAG_ROW_MAJOR_TAIL)
        || read_u32(pack + PF_STAGEB_H_MLPS_BYTES) != binding.mlpsBytes
        || read_u32(pack + PF_STAGEB_H_MLPS_CRC32) != binding.mlpsCrc32
        || std::memcmp(pack + PF_STAGEB_H_DECODED_SHA256, binding.decodedStreamSha256, 32) != 0
        || crc32(pack, PF_STAGEB_H_HEADER_CRC32)
             != read_u32(pack + PF_STAGEB_H_HEADER_CRC32))
        return false;

    payloadCrc = crc32(pack + PF_STAGEB_HEADER_BYTES,
                       PF_STAGEB_PACK_USED_BYTES - PF_STAGEB_HEADER_BYTES);
    if (payloadCrc != read_u32(pack + PF_STAGEB_H_PAYLOAD_CRC32))
        return false;
    for (unsigned stack = 0; stack < PF_STAGEB_STACK_COUNT; ++stack)
    {
        const std::uint8_t* slot = pack + pf_stageb_stack_offset(stack);
        if (read_u32(slot) != PF_STAGEB_STACK_MAGIC || read_u32(slot + 4) != stack
            || read_u32(slot + 8) != PF_STAGEB_STACK_SLOT_BYTES
            || read_u32(slot + 12) != PF_STAGEB_FC0_PACKED_OFFSET
            || read_u32(slot + 16) != PF_STAGEB_FC0_PACKED_BYTES
            || read_u32(slot + 20) != PF_STAGEB_FC0_BIAS_OFFSET
            || read_u32(slot + 24) != PF_STAGEB_FC0_BIAS_BYTES
            || crc32(slot + PF_STAGEB_STACK_HEADER_BYTES,
                     PF_STAGEB_STACK_DATA_END - PF_STAGEB_STACK_HEADER_BYTES)
                 != read_u32(slot + PF_STAGEB_S_DATA_CRC32)
            || crc32(slot + PF_STAGEB_FC0_PACKED_OFFSET,
                     PF_STAGEB_FC0_PACKED_BYTES + PF_STAGEB_FC0_BIAS_BYTES)
                 != read_u32(slot + PF_STAGEB_S_FC0_CRC32))
            return false;
    }
    return true;
}

#endif

}  // namespace

bool prepare(const ModelBinding& binding) noexcept {
#if !defined(PIKAFISH_STAGEB_ACCEL)
    (void) binding;
    return false;
#else
    Runtime& state = runtime();
    std::lock_guard<std::mutex> lock(state.mutex);
    const auto prepareStarted = Clock::now();
    ++state.prepareCalls;
    if (!state.modeParsed)
    {
        state.mode       = parse_mode();
        state.modeParsed = true;
    }
    if (state.mode == Mode::Disabled)
    {
        fallback(state, "disabled-or-invalid-mode");
        return false;
    }
    if (state.attempted)
    {
        if (std::memcmp(&state.binding, &binding, sizeof(binding)) != 0)
            fallback(state, "model-reload");
        return state.ready;
    }
    state.attempted = true;
    state.binding   = binding;

    const char* packPath = std::getenv("PIKAFISH_STAGEB_PACK");
    if (!packPath || !*packPath)
        packPath = "/opt/pikafish/stageb-mac.bin";
    const int fd = open(packPath, O_RDONLY | O_CLOEXEC);
    struct stat status{};
    if (fd < 0 || fstat(fd, &status) != 0
        || status.st_size != static_cast<off_t>(PF_STAGEB_PACK_USED_BYTES))
    {
        if (fd >= 0)
            close(fd);
        fallback(state, "open-size");
        return false;
    }
    const char* backend = std::getenv("PIKAFISH_MAC_BACKEND");
    const bool mmioShadow = backend && std::strcmp(backend, "mmio-shadow") == 0;
    void* mapping = nullptr;
    if (mmioShadow) {
        // NOMMU cannot rely on a private file mapping. Keep one validated
        // userspace copy; the MAC runtime publishes it with 32-bit stores.
        mapping = std::malloc(PF_STAGEB_PACK_USED_BYTES);
        std::size_t copied = 0;
        while (mapping && copied < PF_STAGEB_PACK_USED_BYTES) {
            const ssize_t count = read(fd, static_cast<std::uint8_t*>(mapping) + copied,
                                       PF_STAGEB_PACK_USED_BYTES - copied);
            if (count < 0 && errno == EINTR) continue;
            if (count <= 0) break;
            copied += static_cast<std::size_t>(count);
        }
        if (copied != PF_STAGEB_PACK_USED_BYTES) {
            std::free(mapping);
            mapping = nullptr;
        }
    } else {
        mapping = mmap(nullptr, PF_STAGEB_PACK_USED_BYTES, PROT_READ, MAP_PRIVATE, fd, 0);
        if (mapping == MAP_FAILED) mapping = nullptr;
    }
    close(fd);
    if (!mapping) {
        fallback(state, mmioShadow ? "read-pack" : "mmap-pack");
        return false;
    }
    const auto release = [&] {
        if (mmioShadow) std::free(mapping);
        else munmap(mapping, PF_STAGEB_PACK_USED_BYTES);
    };
    const auto* pack = static_cast<const std::uint8_t*>(mapping);
    std::uint32_t payloadCrc = 0;
    if (!validate_pack(pack, PF_STAGEB_PACK_USED_BYTES, binding, payloadCrc))
    {
        std::fprintf(stderr,
                     "PIKAFISH_STAGEB_BINDING_DIAG mlps=%08x/%08x "
                     "crc=%08x/%08x sha=%08x/%08x "
                     "header=%08x/%08x payload=%08x/%08x\n",
                     read_u32(pack + PF_STAGEB_H_MLPS_BYTES), binding.mlpsBytes,
                     read_u32(pack + PF_STAGEB_H_MLPS_CRC32), binding.mlpsCrc32,
                     read_u32(pack + PF_STAGEB_H_DECODED_SHA256),
                     read_u32(binding.decodedStreamSha256),
                     crc32(pack, PF_STAGEB_H_HEADER_CRC32),
                     read_u32(pack + PF_STAGEB_H_HEADER_CRC32),
                     crc32(pack + PF_STAGEB_HEADER_BYTES,
                           PF_STAGEB_PACK_USED_BYTES - PF_STAGEB_HEADER_BYTES),
                     read_u32(pack + PF_STAGEB_H_PAYLOAD_CRC32));
        release();
        fallback(state, "pfsb-v2-binding");
        return false;
    }

    MacRuntime::Session session(MacRuntime::Client::StageB);
    std::uint8_t* const ddr =
      session.ddr(MacRuntime::StageBModelOffset, MacRuntime::StageBModelBytes);
    std::uint8_t* const resident =
      session.ddr(MacRuntime::StageBResidentOffset, MacRuntime::StageBResidentBytes);
    if (!session || !ddr || !resident)
    {
        release();
        fallback(state, "shared-runtime");
        return false;
    }
    const auto stamp = make_resident_stamp(binding, payloadCrc);
    const bool reused = resident_matches(ddr, resident, pack, stamp);
    if (!reused)
    {
        // Invalidate the tiny commit record before replacing the immutable image.
        // The complete stamp is published only after the model copy and fence.
        std::memset(resident, 0, MacRuntime::StageBResidentBytes);
        std::memcpy(ddr, pack, PF_STAGEB_PACK_USED_BYTES);
        __sync_synchronize();
        std::memcpy(resident, stamp.data(), stamp.size());
        __sync_synchronize();
        state.copiedBytes += PF_STAGEB_PACK_USED_BYTES;
    }
    else
        ++state.residentHits;
    for (unsigned stack = 0; stack < StackCount; ++stack)
    {
        const std::uint8_t* slot = pack + pf_stageb_stack_offset(stack);
        for (unsigned lane = 0; lane < OutputDimensions; ++lane)
            state.biases[stack][lane] =
              read_i32(slot + PF_STAGEB_FC0_BIAS_OFFSET + lane * sizeof(std::int32_t));
    }
    release();
    if(!session.register_model(MacRuntime::StageBModelOffset,PF_STAGEB_PACK_USED_BYTES)) {
        fallback(state,"kernel-resident-register");return false;
    }
    state.ready = true;
    state.payloadCrc = payloadCrc;
    state.prepareNanoseconds += static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - prepareStarted)
        .count());
    std::fprintf(stderr,
                 "PIKAFISH_STAGEB_ACCEL_READY version=%08x stacks=%u mlps_crc32=%08x "
                 "pfsb_crc32=%08x model=%02x%02x%02x%02x mode=%s resident=%s "
                 "copied_bytes=%u\n",
                 static_cast<unsigned>(PF_STAGEB_PACK_VERSION),
                 static_cast<unsigned>(PF_STAGEB_STACK_COUNT),
                 static_cast<unsigned>(binding.mlpsCrc32), static_cast<unsigned>(payloadCrc),
                 binding.decodedStreamSha256[0], binding.decodedStreamSha256[1],
                 binding.decodedStreamSha256[2], binding.decodedStreamSha256[3],
                 mode_name(state.mode), reused ? "reused" : "loaded",
                 reused ? 0u : static_cast<unsigned>(PF_STAGEB_PACK_USED_BYTES));
    return true;
#endif
}

bool fc0(unsigned bucket, const std::uint8_t* input, std::int32_t* output) noexcept {
#if !defined(PIKAFISH_STAGEB_ACCEL)
    (void) bucket;
    (void) input;
    (void) output;
    return false;
#else
    if (!input || !output || bucket >= StackCount)
        return false;
    const auto evaluationStarted = Clock::now();
    Runtime& state = runtime();
    std::lock_guard<std::mutex> lock(state.mutex);
    if (!state.ready || state.mode == Mode::Disabled)
        return false;

    MacRuntime::Session session(MacRuntime::Client::StageB);
    std::uint8_t* const inputScratch =
      session.ddr(MacRuntime::StageBInputOffset, MacRuntime::StageBInputBytes);
    std::uint8_t* const outputScratch =
      session.ddr(MacRuntime::StageBOutputOffset, MacRuntime::StageBOutputBytes);
    if (!session || !inputScratch || !outputScratch)
    {
        fallback(state, "shared-runtime");
        return false;
    }

    std::array<std::uint32_t, OutputDimensions> accumulated{};
    for (unsigned lane = 0; lane < OutputDimensions; ++lane)
        std::memcpy(&accumulated[lane], &state.biases[bucket][lane], sizeof(std::uint32_t));

    std::uint64_t evaluationCycles = 0;
    for (unsigned tile = 0; tile < PF_STAGEB_FC0_TILE_COUNT; ++tile)
    {
        for (unsigned feature = 0; feature < 256; ++feature)
        {
            const std::size_t offset = (feature / 4u) * 8u + (feature % 4u) * 2u;
            inputScratch[offset] = input[tile * 256u + feature];
            inputScratch[offset + 1u] = 0u;
        }
        __sync_synchronize();
        MacRuntime::Job job{};
        job.pixels       = 1;
        job.cin          = 256;
        job.cout         = OutputDimensions;
        job.computeMode  = MacRuntime::ComputeMode::U8S8;
        job.outputFormat = MacRuntime::OutputFormat::I32;
        job.zeroBias     = true;
        job.inputOffset  = MacRuntime::StageBInputOffset;
        job.weightOffset = pf_stageb_fc0_tile_offset(bucket, tile);
        job.biasOffset   = MacRuntime::StageBInputOffset;
        job.outputOffset = MacRuntime::StageBOutputOffset;
        std::uint32_t tileCycles = 0;
        if (!session.submit(job, &tileCycles))
        {
            fallback(state, "mac-submit");
            return false;
        }
        evaluationCycles += tileCycles;
        for (unsigned lane = 0; lane < OutputDimensions; ++lane)
            accumulated[lane] += read_u32(outputScratch + lane * sizeof(std::uint32_t));
    }

    std::array<std::int32_t, OutputDimensions> committed{};
    for (unsigned lane = 0; lane < OutputDimensions; ++lane)
        std::memcpy(&committed[lane], &accumulated[lane], sizeof(std::int32_t));
    std::memcpy(output, committed.data(), sizeof(committed));
    ++state.evaluations;
    state.jobs += PF_STAGEB_FC0_TILE_COUNT;
    state.cycles += evaluationCycles;
    state.hostNanoseconds += static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - evaluationStarted)
        .count());
    state.lastBucket = bucket;
    if (state.mode == Mode::Enabled)
        report_active(state);
    return true;
#endif
}

bool verify_mode() noexcept {
#if !defined(PIKAFISH_STAGEB_ACCEL)
    return false;
#else
    Runtime& state = runtime();
    std::lock_guard<std::mutex> lock(state.mutex);
    return state.ready && state.mode == Mode::Verify;
#endif
}

void verify(unsigned bucket, const std::int32_t* hardware,
            const std::int32_t* officialCpu) noexcept {
#if defined(PIKAFISH_STAGEB_ACCEL)
    if (!hardware || !officialCpu)
        return;
    Runtime& state = runtime();
    std::lock_guard<std::mutex> lock(state.mutex);
    if (!state.ready || state.mode != Mode::Verify)
        return;
    for (unsigned lane = 0; lane < OutputDimensions; ++lane)
        if (hardware[lane] != officialCpu[lane])
        {
            ++state.verifyMismatches;
            std::fprintf(stderr,
                         "PIKAFISH_STAGEB_ACCEL_MISMATCH bucket=%u lane=%u hardware=%d cpu=%d\n",
                         bucket, lane, hardware[lane], officialCpu[lane]);
            fallback(state, "shadow-mismatch");
            return;
        }
    report_active(state);
#else
    (void) bucket;
    (void) hardware;
    (void) officialCpu;
#endif
}

bool checkpoint() noexcept {
#if !defined(PIKAFISH_STAGEB_ACCEL)
    return true;
#else
    Runtime& state = runtime();
    std::lock_guard<std::mutex> lock(state.mutex);
    // A production new-game boundary calls this unconditionally.  Builds or
    // processes that never enabled Stage B have no resident image to audit.
    if (!state.attempted || state.mode == Mode::Disabled)
        return true;
    ++state.checkpoints;
    if (!state.ready)
    {
        ++state.checkpointFailures;
        return false;
    }

    MacRuntime::Session session(MacRuntime::Client::StageB);
    const std::uint8_t* const ddr =
      session.ddr(MacRuntime::StageBModelOffset, MacRuntime::StageBModelBytes);
    const std::uint8_t* const resident =
      session.ddr(MacRuntime::StageBResidentOffset, MacRuntime::StageBResidentBytes);
    std::uint32_t payloadCrc = 0;
    const auto expected = make_resident_stamp(state.binding, state.payloadCrc);
    const bool accountingValid = state.jobs == state.evaluations * PF_STAGEB_FC0_TILE_COUNT;
    const bool imageValid = session && ddr && resident
                         && std::memcmp(resident, expected.data(), expected.size()) == 0
                         && validate_pack(ddr, PF_STAGEB_PACK_USED_BYTES,
                                          state.binding, payloadCrc)
                         && payloadCrc == state.payloadCrc;
    if (!accountingValid || !imageValid)
    {
        ++state.checkpointFailures;
        fallback(state, accountingValid ? "resident-integrity" : "accounting-invariant");
        return false;
    }

    std::fprintf(stderr,
                 "PIKAFISH_STAGEB_CHECKPOINT_PASS checks=%llu evaluations=%llu "
                 "jobs=%llu pfsb_crc32=%08x\n",
                 static_cast<unsigned long long>(state.checkpoints),
                 static_cast<unsigned long long>(state.evaluations),
                 static_cast<unsigned long long>(state.jobs),
                 static_cast<unsigned>(payloadCrc));
    return true;
#endif
}

Statistics statistics() noexcept {
#if !defined(PIKAFISH_STAGEB_ACCEL)
    return {};
#else
    Runtime& state = runtime();
    std::lock_guard<std::mutex> lock(state.mutex);
    Statistics result{};
    result.prepareCalls = state.prepareCalls;
    result.copiedBytes = state.copiedBytes;
    result.residentHits = state.residentHits;
    result.prepareNanoseconds = state.prepareNanoseconds;
    result.evaluations = state.evaluations;
    result.jobs = state.jobs;
    result.macCycles = state.cycles;
    result.hostNanoseconds = state.hostNanoseconds;
    result.fallbacks = state.fallbacks;
    result.verifyMismatches = state.verifyMismatches;
    result.checkpoints = state.checkpoints;
    result.checkpointFailures = state.checkpointFailures;
    return result;
#endif
}

void report_statistics() noexcept {
#if defined(PIKAFISH_STAGEB_ACCEL)
    const Statistics value = statistics();
    std::fprintf(stderr,
                 "PIKAFISH_STAGEB_ACCEL_STATS prepares=%llu copied_bytes=%llu "
                 "resident_hits=%llu prepare_us=%llu evaluations=%llu jobs=%llu "
                 "mac_cycles=%llu host_us=%llu fallbacks=%llu mismatches=%llu\n",
                 static_cast<unsigned long long>(value.prepareCalls),
                 static_cast<unsigned long long>(value.copiedBytes),
                 static_cast<unsigned long long>(value.residentHits),
                 static_cast<unsigned long long>(value.prepareNanoseconds / 1000u),
                 static_cast<unsigned long long>(value.evaluations),
                 static_cast<unsigned long long>(value.jobs),
                 static_cast<unsigned long long>(value.macCycles),
                 static_cast<unsigned long long>(value.hostNanoseconds / 1000u),
                 static_cast<unsigned long long>(value.fallbacks),
                 static_cast<unsigned long long>(value.verifyMismatches));
    std::fprintf(stderr,
                 "PIKAFISH_STAGEB_HEALTH checkpoints=%llu checkpoint_failures=%llu\n",
                 static_cast<unsigned long long>(value.checkpoints),
                 static_cast<unsigned long long>(value.checkpointFailures));
#endif
}

#if defined(PIKAFISH_STAGEB_TESTING)
void reset_for_test() noexcept {
#if defined(PIKAFISH_STAGEB_ACCEL)
    Runtime& state = runtime();
    std::lock_guard<std::mutex> lock(state.mutex);
    state.mode = Mode::Disabled;
    state.modeParsed = false;
    state.attempted = false;
    state.ready = false;
    state.fallbackReported = false;
    state.activeReported = false;
    state.binding = {};
    state.biases = {};
    state.evaluations = 0;
    state.jobs = 0;
    state.cycles = 0;
    state.prepareCalls = 0;
    state.copiedBytes = 0;
    state.residentHits = 0;
    state.prepareNanoseconds = 0;
    state.hostNanoseconds = 0;
    state.fallbacks = 0;
    state.verifyMismatches = 0;
    state.checkpoints = 0;
    state.checkpointFailures = 0;
    state.payloadCrc = 0;
    state.lastBucket = 0;
#endif
}
#endif

}  // namespace Stockfish::Eval::NNUE::StageBAccel
