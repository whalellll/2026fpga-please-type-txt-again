#include "pf_mlp_mac_pack.h"
#include "pikafish_mac_runtime.h"
#include "pikafish_stageb_accel.h"

#include <array>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

namespace {

using Stockfish::Eval::NNUE::MacRuntime::Client;
using Stockfish::Eval::NNUE::StageBAccel::ModelBinding;

constexpr unsigned InputDimensions  = 1024;
constexpr unsigned OutputDimensions = 32;

[[noreturn]] void fail(const char* reason) {
    std::fprintf(stderr, "PIKAFISH_STAGEB_PHASE4_FAIL reason=%s\n", reason);
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
    std::uint32_t state = 0x9e3779b9u ^ (bucket * 0x45d9f3bu) ^ iteration;
    for (auto& value : input)
    {
        state = state * 1664525u + 1013904223u;
        value = static_cast<std::uint8_t>((state >> 24) & 127u);
    }
}

void compare_one(const std::vector<std::uint8_t>& pack, unsigned bucket,
                 unsigned iteration, bool verify) {
    std::array<std::uint8_t, InputDimensions> input{};
    std::array<std::int32_t, OutputDimensions> expected{};
    std::array<std::int32_t, OutputDimensions> actual{};
    fill_input(input, bucket, iteration);
    reference_fc0(pack, bucket, input, expected);
    if (!Stockfish::Eval::NNUE::StageBAccel::fc0(bucket, input.data(), actual.data()))
        fail("fc0-fallback");
    if (actual != expected)
        fail("fc0-mismatch");
    if (verify)
        Stockfish::Eval::NNUE::StageBAccel::verify(bucket, actual.data(), expected.data());
}

void set_environment(const char* packPath, const char* mode, const char* fault) {
    if (setenv("PIKAFISH_STAGEB_PACK", packPath, 1) != 0)
        fail("setenv");
    if (mode)
    {
        if (setenv("PIKAFISH_STAGEB_ACCEL", mode, 1) != 0)
            fail("setenv-mode");
    }
    else
        unsetenv("PIKAFISH_STAGEB_ACCEL");
    if (fault)
    {
        if (setenv("PIKAFISH_MAC_FAULT", fault, 1) != 0)
            fail("setenv-fault");
    }
    else
        unsetenv("PIKAFISH_MAC_FAULT");
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 3)
        fail("usage");
    const std::string scenario = argv[1];
    const auto pack = read_file(argv[2]);
    const ModelBinding binding = binding_from_pack(pack);

    if (scenario == "disabled")
    {
        set_environment(argv[2], "0", nullptr);
        if (Stockfish::Eval::NNUE::StageBAccel::prepare(binding))
            fail("disabled-prepare");
        std::puts("PIKAFISH_STAGEB_PHASE4_MODE_PASS mode=0");
        return 0;
    }

    const char* fault = nullptr;
    if (scenario == "fault-busy")
        fault = "busy";
    else if (scenario == "fault-error")
        fault = "error";
    else if (scenario == "fault-timeout")
        fault = "timeout";
    const bool verify      = scenario == "verify";
    const bool defaultMode = scenario == "default";
    set_environment(argv[2], defaultMode ? nullptr : verify ? "verify" : "1", fault);
    if (!Stockfish::Eval::NNUE::StageBAccel::prepare(binding))
        fail("prepare");

    if (fault)
    {
        std::array<std::uint8_t, InputDimensions> input{};
        std::array<std::int32_t, OutputDimensions> output{};
        if (Stockfish::Eval::NNUE::StageBAccel::fc0(0, input.data(), output.data()))
            fail("fault-not-fused");
        if (Stockfish::Eval::NNUE::StageBAccel::fc0(0, input.data(), output.data()))
            fail("fault-second-submit");
        const auto mac = Stockfish::Eval::NNUE::MacRuntime::statistics();
        const auto stageB = Stockfish::Eval::NNUE::StageBAccel::statistics();
        if (!mac.fused || mac.failed[static_cast<unsigned>(Client::StageB)] != 1
            || stageB.fallbacks != 1)
            fail("fault-statistics");
        std::printf("PIKAFISH_STAGEB_PHASE4_FAULT_PASS fault=%s\n", fault);
        return 0;
    }

    if (scenario == "reuse")
    {
        Stockfish::Eval::NNUE::StageBAccel::reset_for_test();
        if (!Stockfish::Eval::NNUE::StageBAccel::prepare(binding))
            fail("reuse-prepare");
        const auto stats = Stockfish::Eval::NNUE::StageBAccel::statistics();
        if (stats.residentHits != 1 || stats.copiedBytes != 0)
            fail("resident-not-reused");
        std::puts("PIKAFISH_STAGEB_PHASE4_RESIDENT_PASS copied_bytes=0 hits=1");
        return 0;
    }

    if (scenario == "threads")
    {
        constexpr unsigned ThreadCount = 8;
        constexpr unsigned Iterations  = 32;
        std::atomic<bool> failed{false};
        std::array<std::thread, ThreadCount> threads;
        for (unsigned thread = 0; thread < ThreadCount; ++thread)
            threads[thread] = std::thread([&, thread] {
                for (unsigned iteration = 0; iteration < Iterations; ++iteration)
                {
                    std::array<std::uint8_t, InputDimensions> input{};
                    std::array<std::int32_t, OutputDimensions> expected{};
                    std::array<std::int32_t, OutputDimensions> actual{};
                    const unsigned bucket = (thread * 5u + iteration) % PF_STAGEB_STACK_COUNT;
                    fill_input(input, bucket, thread * Iterations + iteration);
                    reference_fc0(pack, bucket, input, expected);
                    if (!Stockfish::Eval::NNUE::StageBAccel::fc0(
                          bucket, input.data(), actual.data())
                        || actual != expected)
                        failed.store(true, std::memory_order_relaxed);
                }
            });
        for (auto& thread : threads)
            thread.join();
        const auto stats = Stockfish::Eval::NNUE::StageBAccel::statistics();
        if (failed.load(std::memory_order_relaxed)
            || stats.evaluations != ThreadCount * Iterations
            || stats.jobs != ThreadCount * Iterations * PF_STAGEB_FC0_TILE_COUNT)
            fail("thread-stress");
        std::printf("PIKAFISH_STAGEB_PHASE4_THREADS_PASS threads=%u evaluations=%u jobs=%u\n",
                    ThreadCount, ThreadCount * Iterations,
                    ThreadCount * Iterations * PF_STAGEB_FC0_TILE_COUNT);
        return 0;
    }

    if (scenario != "verify" && scenario != "enabled" && scenario != "default")
        fail("scenario");
    for (unsigned bucket = 0; bucket < PF_STAGEB_STACK_COUNT; ++bucket)
        for (unsigned iteration = 0; iteration < 8; ++iteration)
            compare_one(pack, bucket, iteration, verify);
    const auto stats = Stockfish::Eval::NNUE::StageBAccel::statistics();
    if (stats.evaluations != PF_STAGEB_STACK_COUNT * 8u
        || stats.jobs != PF_STAGEB_STACK_COUNT * 8u * PF_STAGEB_FC0_TILE_COUNT
        || stats.fallbacks != 0 || stats.verifyMismatches != 0)
        fail("normal-statistics");
    Stockfish::Eval::NNUE::StageBAccel::report_statistics();
    std::printf("PIKAFISH_STAGEB_PHASE4_MODE_PASS mode=%s evaluations=%llu jobs=%llu\n",
                defaultMode ? "default-1" : verify ? "verify" : "1",
                static_cast<unsigned long long>(stats.evaluations),
                static_cast<unsigned long long>(stats.jobs));
    return 0;
}
