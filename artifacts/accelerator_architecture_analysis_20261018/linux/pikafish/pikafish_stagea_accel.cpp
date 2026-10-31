#include "pikafish_stagea_accel.h"
#include "pikafish_mac_runtime.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <mutex>

namespace Stockfish::Eval::NNUE::StageAAccel {

namespace {

// GCC's may_alias types permit word access to the byte-backed PFF1 view.
// The runtime alignment check below keeps RV32 halfword/word loads aligned.
using AliasU16 = std::uint16_t __attribute__((__may_alias__));
using AliasU32 = std::uint32_t __attribute__((__may_alias__));
static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__);

constexpr std::size_t   DefaultMinTerms    = 8;
std::atomic<std::uintptr_t> gatherThreat{0},gatherPsq{0};
std::mutex gatherBindingMutex;

static_assert(MaxInputBytes <= MacRuntime::StageAInputBytes);
static_assert(MaxWeightBytes <= MacRuntime::StageAWeightBytes);
static_assert(TileWidth * sizeof(std::int32_t) <= MacRuntime::StageAOutputBytes);

std::size_t input_bytes(std::size_t count) noexcept {
    return ((count + 3u) / 4u) * 8u;
}

std::size_t weight_bytes(std::size_t count) noexcept {
    return 8u * ((count + 3u) / 4u) * 128u;
}

#if defined(PIKAFISH_STAGEA_ACCEL)
std::size_t minimum_terms() noexcept {
    static const std::size_t value = [] {
        if (const char* threshold = std::getenv("PIKAFISH_STAGEA_MIN_TERMS"))
        {
            char*               end    = nullptr;
            const unsigned long parsed = std::strtoul(threshold, &end, 10);
            if (end != threshold && *end == '\0' && parsed >= 1 && parsed <= MaxTerms)
                return static_cast<std::size_t>(parsed);
        }
        return DefaultMinTerms;
    }();
    return value;
}

bool stage_a_enabled() noexcept {
    const char* enabled = std::getenv("PIKAFISH_STAGEA_ACCEL");
    return !enabled || std::strcmp(enabled, "0") != 0;
}
#endif

}  // namespace

bool encode_gather_descriptors(std::uint32_t* descriptors, std::size_t capacity,
    const std::int8_t* const* rows, const std::int8_t* coefficients,
    std::size_t count, std::uintptr_t threatBase, std::uintptr_t psqBase) noexcept {
    if (!descriptors || !rows || !coefficients || !count || count>MaxTerms ||
        capacity<count || !threatBase || !psqBase) return false;
    for (std::size_t i=0;i<count;i++) {
        if (coefficients[i]!=1 && coefficients[i]!=-1) return false;
        const auto address=reinterpret_cast<std::uintptr_t>(rows[i]);
        std::uintptr_t offset;
        std::uint32_t table;
        if(address>=threatBase && address-threatBase<45547u*1024u) {
            offset=address-threatBase;table=0;
        } else if(address>=psqBase && address-psqBase<16536u*1024u) {
            offset=address-psqBase;table=0x40000000u;
        } else return false;
        if(offset%1024u) return false;
        descriptors[i]=table|static_cast<std::uint32_t>(offset/1024u)|
            (coefficients[i]<0 ? 0x80000000u : 0u);
    }
    return true;
}

bool bind_gather_model(const void* threat, std::size_t threatBytes, std::uint64_t threatPhysical,
    const void* psq, std::size_t psqBytes, std::uint64_t psqPhysical) noexcept {
    const auto t=reinterpret_cast<std::uintptr_t>(threat),p=reinterpret_cast<std::uintptr_t>(psq);
    if(!t || !p || (t|p)%1024u || threatBytes!=45547u*1024u || psqBytes!=16536u*1024u ||
       threatPhysical!=0x10002000u || psqPhysical!=0x12f45000u ||
       t>std::numeric_limits<std::uintptr_t>::max()-threatBytes ||
       p>std::numeric_limits<std::uintptr_t>::max()-psqBytes) return false;
    std::lock_guard<std::mutex> lock(gatherBindingMutex);
    if((gatherThreat.load()!=0 && gatherThreat.load()!=t) ||
       (gatherPsq.load()!=0 && gatherPsq.load()!=p)) return false;
    gatherPsq.store(p,std::memory_order_release);
    gatherThreat.store(t,std::memory_order_release);
    return true;
}

bool pack_tile(std::uint8_t*             input,
               std::size_t               inputCapacity,
               std::uint8_t*             weights,
               std::size_t               weightCapacity,
               const std::int8_t* const* rows,
               const std::int8_t*        coefficients,
               std::size_t               count,
               unsigned                  tile) noexcept {
    if (!input || !weights || !rows || !coefficients || count == 0 || count > MaxTerms
        || tile >= L1 / TileWidth || inputCapacity < input_bytes(count)
        || weightCapacity < weight_bytes(count))
        return false;

    const std::size_t ciTiles = (count + 3u) / 4u;
    const bool alignedOutput = (reinterpret_cast<std::uintptr_t>(weights) & 3u) == 0u;
    bool alignedPairs = alignedOutput;
    bool alignedWords = alignedOutput;
    for (std::size_t feature = 0; feature < count; ++feature)
    {
        if (!rows[feature] || (coefficients[feature] != 1 && coefficients[feature] != -1))
            return false;
        alignedPairs &= (reinterpret_cast<std::uintptr_t>(rows[feature]) & 1u) == 0u;
        alignedWords &= (reinterpret_cast<std::uintptr_t>(rows[feature]) & 3u) == 0u;
    }

    // The MAC consumes four input slots per ci tile. Write every byte once,
    // including the high byte and the final tile's padding, instead of first
    // clearing the complete scratch range and then overwriting most of it.
    for (std::size_t feature = 0; feature < ciTiles * 4u; ++feature)
    {
        const std::size_t offset = (feature / 4u) * 8u + (feature % 4u) * 2u;
        input[offset] = feature < count
                        ? static_cast<std::uint8_t>(coefficients[feature])
                        : 0u;
        input[offset + 1u] = 0u;
    }

    const std::size_t laneBase = static_cast<std::size_t>(tile) * TileWidth;
    for (std::size_t coTile = 0; coTile < 8; ++coTile)
        for (std::size_t ciTile = 0; ciTile < ciTiles; ++ciTile)
        {
            const std::size_t firstFeature = ciTile * 4u;
            const std::size_t line = (coTile * ciTiles + ciTile) * 128u;
            const std::size_t firstLane = laneBase + coTile * 32u;
            if (firstFeature + 4u <= count)
            {
                const std::int8_t* const r0 = rows[firstFeature];
                const std::int8_t* const r1 = rows[firstFeature + 1u];
                const std::int8_t* const r2 = rows[firstFeature + 2u];
                const std::int8_t* const r3 = rows[firstFeature + 3u];
                // One aligned row load supplies two adjacent MAC lane pairs.
                if (alignedWords)
                    for (std::size_t pair = 0; pair < 16; pair += 2)
                    {
                        const std::size_t lane = firstLane + pair * 2u;
                        const auto v0 = *reinterpret_cast<const AliasU32*>(r0 + lane);
                        const auto v1 = *reinterpret_cast<const AliasU32*>(r1 + lane);
                        const auto v2 = *reinterpret_cast<const AliasU32*>(r2 + lane);
                        const auto v3 = *reinterpret_cast<const AliasU32*>(r3 + lane);
                        auto* const words = reinterpret_cast<AliasU32*>(
                          weights + line + pair * 8u);
                        words[0] = (v0 & 0xffffu) | (v1 << 16);
                        words[1] = (v2 & 0xffffu) | (v3 << 16);
                        words[2] = (v0 >> 16) | (v1 & 0xffff0000u);
                        words[3] = (v2 >> 16) | (v3 & 0xffff0000u);
                    }
                else for (std::size_t pair = 0; pair < 16; ++pair)
                {
                    const std::size_t lane = firstLane + pair * 2u;
                    std::uint8_t* const dest = weights + line + pair * 8u;
                    if (alignedPairs)
                    {
                        const auto v0 = *reinterpret_cast<const AliasU16*>(r0 + lane);
                        const auto v1 = *reinterpret_cast<const AliasU16*>(r1 + lane);
                        const auto v2 = *reinterpret_cast<const AliasU16*>(r2 + lane);
                        const auto v3 = *reinterpret_cast<const AliasU16*>(r3 + lane);
                        auto* const words = reinterpret_cast<AliasU32*>(dest);
                        words[0] = static_cast<std::uint32_t>(v0)
                                 | (static_cast<std::uint32_t>(v1) << 16);
                        words[1] = static_cast<std::uint32_t>(v2)
                                 | (static_cast<std::uint32_t>(v3) << 16);
                    }
                    else
                    {
                        dest[0] = static_cast<std::uint8_t>(r0[lane]);
                        dest[1] = static_cast<std::uint8_t>(r0[lane + 1u]);
                        dest[2] = static_cast<std::uint8_t>(r1[lane]);
                        dest[3] = static_cast<std::uint8_t>(r1[lane + 1u]);
                        dest[4] = static_cast<std::uint8_t>(r2[lane]);
                        dest[5] = static_cast<std::uint8_t>(r2[lane + 1u]);
                        dest[6] = static_cast<std::uint8_t>(r3[lane]);
                        dest[7] = static_cast<std::uint8_t>(r3[lane + 1u]);
                    }
                }
            }
            else
                for (std::size_t pair = 0; pair < 16; ++pair)
                    for (std::size_t ci = 0; ci < 4; ++ci)
                    {
                        const std::size_t feature = firstFeature + ci;
                        const std::size_t slot = line + (pair * 4u + ci) * 2u;
                        const std::size_t lane = firstLane + pair * 2u;
                        weights[slot] = feature < count
                                          ? static_cast<std::uint8_t>(rows[feature][lane])
                                          : 0u;
                        weights[slot + 1u] = feature < count
                                               ? static_cast<std::uint8_t>(rows[feature][lane + 1u])
                                               : 0u;
                    }
        }
    return true;
}

bool pack_tile_rowmajor(std::uint8_t*             input,
                        std::size_t               inputCapacity,
                        std::uint8_t*             weights,
                        std::size_t               weightCapacity,
                        const std::int8_t* const* rows,
                        const std::int8_t*        coefficients,
                        std::size_t               count,
                        unsigned                  tile) noexcept {
    if (!input || !weights || !rows || !coefficients || count == 0 || count > MaxTerms
        || tile >= L1 / TileWidth || inputCapacity < input_bytes(count)
        || weightCapacity < weight_bytes(count))
        return false;
    const std::size_t ciTiles = (count + 3u) / 4u;
    for (std::size_t feature = 0; feature < count; ++feature)
        if (!rows[feature] || (coefficients[feature] != 1 && coefficients[feature] != -1))
            return false;
    for (std::size_t feature = 0; feature < ciTiles * 4u; ++feature)
    {
        const std::size_t offset = (feature / 4u) * 8u + (feature % 4u) * 2u;
        input[offset] = feature < count
                      ? static_cast<std::uint8_t>(coefficients[feature]) : 0u;
        input[offset + 1u] = 0u;
    }
    const std::size_t laneBase = static_cast<std::size_t>(tile) * TileWidth;
    for (std::size_t coTile = 0; coTile < 8; ++coTile)
        for (std::size_t ciTile = 0; ciTile < ciTiles; ++ciTile)
            for (std::size_t ci = 0; ci < 4; ++ci)
            {
                const std::size_t feature = ciTile * 4u + ci;
                std::uint8_t* const dest = weights +
                  (coTile * ciTiles + ciTile) * 128u + ci * 32u;
                if (feature < count)
                    std::memcpy(dest, rows[feature] + laneBase + coTile * 32u, 32u);
                else
                    std::memset(dest, 0, 32u);
            }
    return true;
}

bool apply(const std::int16_t*            base,
           std::int16_t*                  out,
           const std::int8_t* const*      rows,
           const std::int8_t*             coefficients,
           std::size_t                    count) noexcept {
#if !defined(PIKAFISH_STAGEA_ACCEL)
    (void) base;
    (void) out;
    (void) rows;
    (void) coefficients;
    (void) count;
    return false;
#else
    if (!base || !out || !rows || !coefficients || count == 0 || count > MaxTerms)
        return false;

    if (!stage_a_enabled())
        return false;

    MacRuntime::Session session(MacRuntime::Client::StageA);
    if (!session)
        return false;

    const auto threat=gatherThreat.load(std::memory_order_acquire);
    const auto psq=gatherPsq.load(std::memory_order_acquire);
    if(session.gather_available() && threat && psq) {
        auto* descriptors=reinterpret_cast<std::uint32_t*>(
            session.ddr(MacRuntime::StageAWeightOffset,count*sizeof(std::uint32_t)));
        auto* parent=session.ddr(MacRuntime::StageAInputOffset,MacRuntime::StageAGatherBaseBytes);
        auto* result=session.ddr(MacRuntime::StageAOutputOffset,MacRuntime::StageAGatherOutputBytes);
        if(!descriptors || !parent || !result ||
           !encode_gather_descriptors(descriptors,count,rows,coefficients,count,threat,psq)) return false;
        std::memcpy(parent,base,MacRuntime::StageAGatherBaseBytes);
        std::uint32_t cycles=0;
        if(!session.gather(static_cast<std::uint32_t>(count),&cycles)) return false;
        std::memcpy(out,result,MacRuntime::StageAGatherOutputBytes);
        static std::atomic<bool> reported{false};
        if(!reported.exchange(true)) std::fprintf(stderr,
            "PIKAFISH_STAGEA_GATHER_ACTIVE terms=%u lanes=1024 cycles=%u backend=driver\n",
            static_cast<unsigned>(count),static_cast<unsigned>(cycles));
        return true;
    }
    if(count<minimum_terms()) return false;
    std::uint8_t* const input =
      session.ddr(MacRuntime::StageAInputOffset, MacRuntime::StageAInputBytes);
    std::uint8_t* const weights =
      session.ddr(MacRuntime::StageAWeightOffset, MacRuntime::StageAWeightBytes);
    std::uint8_t* const output =
      session.ddr(MacRuntime::StageAOutputOffset, MacRuntime::StageAOutputBytes);
    if (!input || !weights || !output)
        return false;

    std::array<std::int32_t, TileWidth> tileResult{};
    std::uint32_t lastCycles = 0;
    for (unsigned tile = 0; tile < L1 / TileWidth; ++tile)
    {
        if (!pack_tile(input, MaxInputBytes, weights, MaxWeightBytes,
                       rows, coefficients, count, tile))
            return false;
        __sync_synchronize();
        MacRuntime::Job job{};
        job.pixels       = 1;
        job.cin          = static_cast<std::uint16_t>(count);
        job.cout         = static_cast<std::uint16_t>(TileWidth);
        job.computeMode  = MacRuntime::ComputeMode::S8S8;
        job.outputFormat = MacRuntime::OutputFormat::I32;
        job.zeroBias     = true;
        job.inputOffset  = MacRuntime::StageAInputOffset;
        job.weightOffset = MacRuntime::StageAWeightOffset;
        job.biasOffset   = MacRuntime::StageAInputOffset;
        job.outputOffset = MacRuntime::StageAOutputOffset;
        if (!session.submit(job, &lastCycles))
        {
            return false;
        }
        __sync_synchronize();
        std::memcpy(tileResult.data(), output, TileWidth * sizeof(std::int32_t));
        const std::size_t baseLane = static_cast<std::size_t>(tile) * TileWidth;
        for (std::size_t lane = 0; lane < TileWidth; ++lane)
        {
            const std::uint32_t sum = static_cast<std::uint16_t>(base[baseLane + lane])
                                    + static_cast<std::uint32_t>(tileResult[lane]);
            out[baseLane + lane] = static_cast<std::int16_t>(sum & 0xffffu);
        }
    }
    static std::atomic<bool> activeReported{false};
    if (!activeReported.exchange(true))
    {
        std::fprintf(stderr,
                     "PIKAFISH_STAGEA_ACCEL_ACTIVE terms=%u tiles=%u last_cycles=%u\n",
                     static_cast<unsigned>(count),
                     static_cast<unsigned>(L1 / TileWidth),
                     static_cast<unsigned>(lastCycles));
    }
    return true;
#endif
}

}  // namespace Stockfish::Eval::NNUE::StageAAccel
