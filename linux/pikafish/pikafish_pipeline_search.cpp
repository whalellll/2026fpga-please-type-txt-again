#include "pf_mlp_mac_pack.h"
#include "pikafish_embedded.h"
#include "pikafish_stageb_accel.h"
#include "pikafish_mac_runtime.h"

#include <array>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <thread>

namespace {

constexpr std::array<const char*, 3> Positions = {
  "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
  "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C2C4/9/RNBAKABNR b - - 0 1",
  "r1bakabnr/9/1cn4c1/p1p1p1p1p/9/9/P1P1P1P1P/1C2C1N2/9/RNBAKAB1R w - - 2 2",
};

[[noreturn]] void fail(const char* reason) {
    std::fprintf(stderr, "PIKAFISH_PIPELINE_SEARCH_FAIL reason=%s\n", reason);
    std::exit(1);
}

std::uint32_t read_u32(const std::uint8_t* p) {
    return static_cast<std::uint32_t>(p[0]) | (static_cast<std::uint32_t>(p[1]) << 8)
         | (static_cast<std::uint32_t>(p[2]) << 16)
         | (static_cast<std::uint32_t>(p[3]) << 24);
}

void prepare_stageb() {
    const char* path = std::getenv("PIKAFISH_STAGEB_PACK");
    if (!path || !*path)
        path = "/opt/pikafish/stageb-mac.bin";
    std::ifstream input(path, std::ios::binary);
    std::array<std::uint8_t, PF_STAGEB_H_HEADER_CRC32 + 4u> header{};
    input.read(reinterpret_cast<char*>(header.data()), header.size());
    if (!input || read_u32(header.data() + PF_STAGEB_H_MAGIC) != PF_STAGEB_PACK_MAGIC)
        fail("pfsb-header");
    Stockfish::Eval::NNUE::StageBAccel::ModelBinding binding{};
    std::memcpy(binding.decodedStreamSha256,
                header.data() + PF_STAGEB_H_DECODED_SHA256,
                sizeof(binding.decodedStreamSha256));
    binding.mlpsBytes = read_u32(header.data() + PF_STAGEB_H_MLPS_BYTES);
    binding.mlpsCrc32 = read_u32(header.data() + PF_STAGEB_H_MLPS_CRC32);
    const char* mode = std::getenv("PIKAFISH_STAGEB_ACCEL");
    const bool enabled = !mode || std::strcmp(mode, "verify") == 0
                      || std::strcmp(mode, "1") == 0;
    if (Stockfish::Eval::NNUE::StageBAccel::prepare(binding) != enabled)
        fail("stageb-prepare");
}

unsigned parse_nodes() {
    const char* text = std::getenv("PIKAFISH_PHASE4_NODES");
    if (!text || !*text)
        return 128;
    char* end = nullptr;
    const unsigned long value = std::strtoul(text, &end, 10);
    if (end == text || *end != '\0' || value < 16 || value > 1000000)
        fail("nodes");
    return static_cast<unsigned>(value);
}

}  // namespace

extern "C" int xiangqi_pikafish_gui_main(void) {
    const char* mode = std::getenv("PIKAFISH_STAGEB_ACCEL");
    if (!mode || !*mode)
        mode = "1";
    const char* model = std::getenv("PIKAFISH_PHASE4_MODEL");
    if (!model || !*model)
        model = "pff1-view:0x10000000:68122688";
    const unsigned nodes = parse_nodes();

    prepare_stageb();
    if (!pikafish_embedded_start(model, 8))
        fail("engine-start");
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::minutes(15);
    for (;;)
    {
        const int status = pikafish_embedded_status();
        if (status == PIKAFISH_EMBEDDED_READY)
            break;
        if (status == PIKAFISH_EMBEDDED_FAILED)
            fail("engine-load");
        if (std::chrono::steady_clock::now() >= deadline)
            fail("engine-timeout");
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }

    for (unsigned index = 0; index < Positions.size(); ++index)
    {
        pikafish_embedded_new_game();
        pikafish_embedded_result_t result{};
        if (!pikafish_embedded_search_nodes(Positions[index], nodes, &result))
            fail("fixed-nodes-search");
        const std::uint64_t nps = static_cast<std::uint64_t>(result.nodes) * 1000u
                                / (result.elapsed_ms ? result.elapsed_ms : 1u);
        std::printf(
          "PIKAFISH_PIPELINE_SEARCH mode=%s case=%u bestmove=%s ponder=%s "
          "score=%d wdl=%u,%u,%u nodes=%u elapsed_ms=%u nps=%llu\n",
          mode, index, result.bestmove, result.ponder, result.score_cp,
          result.wins, result.draws, result.losses, result.nodes, result.elapsed_ms,
          static_cast<unsigned long long>(nps));
        std::fflush(stdout);
    }
    const auto stage=Stockfish::Eval::NNUE::StageBAccel::statistics();
    const auto mac=Stockfish::Eval::NNUE::MacRuntime::statistics();
    const char* pipeline=std::getenv("PIKAFISH_NNUE_PIPELINE");
    const bool chain=pipeline && std::strcmp(pipeline,"1")==0;
    if(stage.fallbacks || stage.verifyMismatches || mac.fused || mac.pipelineFailures)
        fail("hardware-fallback-or-mismatch");
    if(std::strcmp(mode,"0")!=0) {
        if(chain && !mac.pipelineCompleted)fail("pipeline-not-exercised");
        if(!chain && !stage.evaluations)fail("legacy-not-exercised");
        if(!mac.gatherCompleted)fail("gather-not-exercised");
    }
    Stockfish::Eval::NNUE::StageBAccel::report_statistics();
    pikafish_embedded_stop();
    std::printf("PIKAFISH_PIPELINE_SEARCH_PASS mode=%s cases=%zu nodes=%u\n",
                mode, Positions.size(), nodes);
    return 0;
}
