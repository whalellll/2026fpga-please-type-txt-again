#include "pf_mlp_mac_pack.h"
#include "pikafish_mac_runtime.h"
#include "pikafish_stageb_accel.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

namespace {

using Stockfish::Eval::NNUE::StageBAccel::ModelBinding;

constexpr unsigned InputDimensions  = 1024;
constexpr unsigned OutputDimensions = 32;

[[noreturn]] void fail(const char* reason) {
    std::fprintf(stderr, "PIKAFISH_STAGEB_PHASE5_FAIL reason=%s\n", reason);
    std::exit(1);
}

std::uint32_t read_u32(const std::uint8_t* p) {
    return static_cast<std::uint32_t>(p[0]) | (static_cast<std::uint32_t>(p[1]) << 8)
         | (static_cast<std::uint32_t>(p[2]) << 16)
         | (static_cast<std::uint32_t>(p[3]) << 24);
}

std::vector<std::uint8_t> read_file(const char* path) {
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    if (!input)
        fail("pack-open");
    const std::streamoff length = input.tellg();
    if (length != static_cast<std::streamoff>(PF_STAGEB_PACK_USED_BYTES))
        fail("pack-size");
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(length));
    input.seekg(0);
    input.read(reinterpret_cast<char*>(bytes.data()), length);
    if (!input)
        fail("pack-read");
    return bytes;
}

ModelBinding binding_from_pack(const std::vector<std::uint8_t>& pack) {
    ModelBinding binding{};
    std::memcpy(binding.decodedStreamSha256, pack.data() + PF_STAGEB_H_DECODED_SHA256,
                sizeof(binding.decodedStreamSha256));
    binding.mlpsBytes = read_u32(pack.data() + PF_STAGEB_H_MLPS_BYTES);
    binding.mlpsCrc32 = read_u32(pack.data() + PF_STAGEB_H_MLPS_CRC32);
    return binding;
}

std::size_t native_weight_offset(unsigned lane, unsigned feature) {
    const unsigned tile   = feature / 256u;
    const unsigned within = feature % 256u;
    const unsigned ciTile = within / 4u;
    const unsigned ci     = within % 4u;
    const unsigned pair   = lane / 2u;
    const unsigned parity = lane % 2u;
    return PF_STAGEB_FC0_PACKED_OFFSET + tile * PF_STAGEB_FC0_TILE_BYTES
         + ciTile * 128u + (pair * 4u + ci) * 2u + parity;
}

void reference_fc0(const std::vector<std::uint8_t>& pack, unsigned bucket,
                   const std::array<std::uint8_t, InputDimensions>& input,
                   std::array<std::int32_t, OutputDimensions>& output) {
    const std::uint8_t* slot = pack.data() + pf_stageb_stack_offset(bucket);
    for (unsigned lane = 0; lane < OutputDimensions; ++lane)
    {
        std::uint32_t sum = read_u32(slot + PF_STAGEB_FC0_BIAS_OFFSET + lane * 4u);
        for (unsigned feature = 0; feature < InputDimensions; ++feature)
        {
            const auto weight = static_cast<std::int8_t>(
              slot[native_weight_offset(lane, feature)]);
            sum += static_cast<std::uint32_t>(static_cast<std::int32_t>(weight)
                                              * input[feature]);
        }
        std::memcpy(&output[lane], &sum, sizeof(sum));
    }
}

void fill_input(std::array<std::uint8_t, InputDimensions>& input,
                unsigned bucket, unsigned iteration) {
    std::uint32_t state = 0x243f6a88u ^ (bucket * 0x9e3779b9u) ^ iteration;
    for (auto& value : input)
    {
        state = state * 1664525u + 1013904223u;
        value = static_cast<std::uint8_t>((state >> 24) & 127u);
    }
}

void run_one(const std::vector<std::uint8_t>& pack, unsigned bucket,
             unsigned iteration) {
    std::array<std::uint8_t, InputDimensions> input{};
    std::array<std::int32_t, OutputDimensions> expected{};
    std::array<std::int32_t, OutputDimensions> actual{};
    fill_input(input, bucket, iteration);
    reference_fc0(pack, bucket, input, expected);
    if (!Stockfish::Eval::NNUE::StageBAccel::fc0(bucket, input.data(), actual.data()))
        fail("fc0-fallback");
    if (actual != expected)
        fail("fc0-mismatch");
}

void configure(const char* packPath) {
    if (setenv("PIKAFISH_STAGEB_PACK", packPath, 1) != 0
        || setenv("PIKAFISH_STAGEB_ACCEL", "1", 1) != 0)
        fail("setenv");
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 3)
        fail("usage");
    const std::string scenario = argv[1];
    const auto pack = read_file(argv[2]);
    if (!Stockfish::Eval::NNUE::StageBAccel::checkpoint())
        fail("inactive-checkpoint");
    const auto inactiveStats = Stockfish::Eval::NNUE::StageBAccel::statistics();
    if (inactiveStats.checkpoints != 0 || inactiveStats.checkpointFailures != 0)
        fail("inactive-checkpoint-statistics");
    configure(argv[2]);
    if (!Stockfish::Eval::NNUE::StageBAccel::prepare(binding_from_pack(pack)))
        fail("prepare");
    if (!Stockfish::Eval::NNUE::StageBAccel::checkpoint())
        fail("initial-checkpoint");

    if (scenario == "soak")
    {
        constexpr unsigned Rounds = 16;
        for (unsigned round = 0; round < Rounds; ++round)
        {
            for (unsigned bucket = 0; bucket < PF_STAGEB_STACK_COUNT; ++bucket)
                run_one(pack, bucket, round);
            if (!Stockfish::Eval::NNUE::StageBAccel::checkpoint())
                fail("soak-checkpoint");
        }
        const auto stats = Stockfish::Eval::NNUE::StageBAccel::statistics();
        if (stats.evaluations != Rounds * PF_STAGEB_STACK_COUNT
            || stats.jobs != stats.evaluations * PF_STAGEB_FC0_TILE_COUNT
            || stats.checkpoints != Rounds + 1u || stats.checkpointFailures != 0
            || stats.fallbacks != 0 || stats.verifyMismatches != 0)
            fail("soak-statistics");
        std::printf("PIKAFISH_STAGEB_PHASE5_SOAK_PASS rounds=%u evaluations=%llu "
                    "jobs=%llu checkpoints=%llu\n",
                    Rounds, static_cast<unsigned long long>(stats.evaluations),
                    static_cast<unsigned long long>(stats.jobs),
                    static_cast<unsigned long long>(stats.checkpoints));
        return 0;
    }

    if (scenario == "corrupt-model")
    {
        {
            Stockfish::Eval::NNUE::MacRuntime::Session session(
              Stockfish::Eval::NNUE::MacRuntime::Client::StageB);
            auto* const model = session.ddr(
              Stockfish::Eval::NNUE::MacRuntime::StageBModelOffset,
              Stockfish::Eval::NNUE::MacRuntime::StageBModelBytes);
            if (!session || !model)
                fail("corrupt-map");
            model[pf_stageb_stack_offset(0) + PF_STAGEB_FC0_PACKED_OFFSET + 17u] ^= 0x80u;
        }
        if (Stockfish::Eval::NNUE::StageBAccel::checkpoint())
            fail("corruption-not-detected");
        std::array<std::uint8_t, InputDimensions> input{};
        std::array<std::int32_t, OutputDimensions> output{};
        if (Stockfish::Eval::NNUE::StageBAccel::fc0(0, input.data(), output.data()))
            fail("corruption-not-fallback");
        const auto stats = Stockfish::Eval::NNUE::StageBAccel::statistics();
        if (stats.checkpoints != 2 || stats.checkpointFailures != 1
            || stats.fallbacks != 1 || stats.evaluations != 0 || stats.jobs != 0)
            fail("corruption-statistics");
        std::puts("PIKAFISH_STAGEB_PHASE5_CORRUPTION_PASS fallback=1 checkpoint_failures=1");
        return 0;
    }

    fail("scenario");
}
