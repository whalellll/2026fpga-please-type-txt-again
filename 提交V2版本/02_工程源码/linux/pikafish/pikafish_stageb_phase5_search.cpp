#include "pf_mlp_mac_pack.h"
#include "pikafish_embedded.h"
#include "pikafish_stageb_accel.h"

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

constexpr std::array<const char*, 8> Positions = {
  "2bakab2/9/c3c1n2/p3p1p1p/1npr5/2P2NP2/P3P3P/2CCB4/4A4/1NBAKR3 b - - 1 1",
  "2bak4/4a4/1c2b1n2/pC1cp1N1p/1n5r1/P1P2RP2/4P3P/N2CB4/4A4/2BAK4 b - - 10 10",
  "3ak4/1c2a4/4b1C2/p1c1p3p/9/PCP2RP1P/4P4/N1n1B4/4r4/2B2K3 b - - 1 21",
  "4k4/1c2a4/4b1C2/p1c1p3p/2P6/PC3RP1P/4P4/N1n1B4/3r5/2B2K3 b - - 4 26",
  "4k4/4a4/4b1C2/p3p3p/2c2P3/P7P/4P4/Nc6r/5K3/1R7 b - - 7 38",
  "4k4/4a4/4b1C2/p3p3p/2c2r3/P3P3P/9/Nc2K4/9/1R7 b - - 1 43",
  "4k4/9/5a1C1/p7p/6b2/PN2r3P/7C1/1c1K5/c8/R8 b - - 9 53",
  "5k3/9/3a5/p7p/6b2/Pr6P/3C5/1c1K5/c3R4/9 b - - 7 57",
};

constexpr const char* CompleteGameFen =
  "3k5/2R1R4/9/9/3P5/9/9/9/9/3K5 w - - 0 1";

[[noreturn]] void fail(const char* reason) {
    std::fprintf(stderr, "PIKAFISH_STAGEB_PHASE5_SEARCH_FAIL reason=%s\n", reason);
    std::exit(1);
}

std::uint32_t read_u32(const std::uint8_t* p) {
    return static_cast<std::uint32_t>(p[0]) | (static_cast<std::uint32_t>(p[1]) << 8)
         | (static_cast<std::uint32_t>(p[2]) << 16)
         | (static_cast<std::uint32_t>(p[3]) << 24);
}

bool accelerated_mode() {
    const char* mode = std::getenv("PIKAFISH_STAGEB_ACCEL");
    return !mode || std::strcmp(mode, "verify") == 0 || std::strcmp(mode, "1") == 0;
}

const char* mode_name() {
    const char* mode = std::getenv("PIKAFISH_STAGEB_ACCEL");
    return mode && *mode ? mode : "1";
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
    if (Stockfish::Eval::NNUE::StageBAccel::prepare(binding) != accelerated_mode())
        fail("stageb-prepare");
}

unsigned parse_unsigned(const char* name, unsigned fallback,
                        unsigned minimum, unsigned maximum) {
    const char* text = std::getenv(name);
    if (!text || !*text)
        return fallback;
    char* end = nullptr;
    const unsigned long value = std::strtoul(text, &end, 10);
    if (end == text || *end != '\0' || value < minimum || value > maximum)
        fail(name);
    return static_cast<unsigned>(value);
}

void wait_ready() {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::minutes(15);
    for (;;)
    {
        const int status = pikafish_embedded_status();
        if (status == PIKAFISH_EMBEDDED_READY)
            return;
        if (status == PIKAFISH_EMBEDDED_FAILED)
            fail("engine-load");
        if (std::chrono::steady_clock::now() >= deadline)
            fail("engine-timeout");
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
}

void print_result(const char* kind, unsigned first, unsigned second,
                  const pikafish_embedded_result_t& result) {
    std::printf("PIKAFISH_STAGEB_PHASE5_%s mode=%s first=%u second=%u "
                "bestmove=%s ponder=%s score=%d wdl=%u,%u,%u nodes=%u "
                "elapsed_ms=%u\n",
                kind, mode_name(), first, second, result.bestmove, result.ponder,
                result.score_cp, result.wins, result.draws, result.losses,
                result.nodes, result.elapsed_ms);
    std::fflush(stdout);
}

void require_checkpoint() {
    if (accelerated_mode()
        && !Stockfish::Eval::NNUE::StageBAccel::checkpoint())
        fail("checkpoint");
}

void trace_stage(const char* stage, unsigned round = 0) {
    std::printf("PIKAFISH_STAGEB_PHASE5_STAGE mode=%s stage=%s round=%u\n",
                mode_name(), stage, round);
    std::fflush(stdout);
}

void reset_new_game(unsigned resetBudgetMs, const char* kind, unsigned round = 0) {
    const auto started = std::chrono::steady_clock::now();
    pikafish_embedded_new_game();
    const auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
      std::chrono::steady_clock::now() - started);
    std::printf("PIKAFISH_STAGEB_PHASE5_RESET mode=%s kind=%s round=%u "
                "elapsed_us=%lld budget_ms=%u\n",
                mode_name(), kind, round, static_cast<long long>(elapsed.count()),
                resetBudgetMs);
    std::fflush(stdout);
    if (elapsed > std::chrono::milliseconds(resetBudgetMs))
        fail("new-game-budget");
}

}  // namespace

extern "C" int xiangqi_pikafish_gui_main(void) {
    const char* model = std::getenv("PIKAFISH_PHASE5_MODEL");
    if (!model || !*model)
        model = "pff1-view:0x10000000:68122688";
    const unsigned nodes = parse_unsigned("PIKAFISH_PHASE5_NODES", 128, 16, 1000000);
    const unsigned longNodes = parse_unsigned(
      "PIKAFISH_PHASE5_LONG_NODES", nodes * 8u, nodes, 1000000);
    const unsigned rounds = parse_unsigned("PIKAFISH_PHASE5_ROUNDS", 2, 1, 1000);
    const unsigned resetBudgetMs = parse_unsigned(
      "PIKAFISH_PHASE5_RESET_BUDGET_MS", 250, 1, 60000);

    prepare_stageb();
    require_checkpoint();
    if (!pikafish_embedded_start(model, 8))
        fail("engine-start");
    trace_stage("engine-wait-start");
    wait_ready();
    trace_stage("engine-ready");

    for (unsigned round = 0; round < rounds; ++round)
    {
        trace_stage("new-game-start", round);
        reset_new_game(resetBudgetMs, "corpus", round);
        trace_stage("new-game-ready", round);
        for (unsigned index = 0; index < Positions.size(); ++index)
        {
            pikafish_embedded_result_t result{};
            if (!pikafish_embedded_search_nodes(Positions[index], nodes, &result)
                || std::strcmp(result.bestmove, "(none)") == 0)
                fail("corpus-search");
            print_result("CASE", round, index, result);
        }
        trace_stage("checkpoint-start", round);
        require_checkpoint();
        trace_stage("checkpoint-ready", round);
    }

    trace_stage("long-new-game-start");
    reset_new_game(resetBudgetMs, "long");
    trace_stage("long-new-game-ready");
    pikafish_embedded_result_t longResult{};
    if (!pikafish_embedded_search_nodes(Positions[3], longNodes, &longResult)
        || std::strcmp(longResult.bestmove, "(none)") == 0)
        fail("long-search");
    print_result("LONG", longNodes, 0, longResult);
    trace_stage("long-checkpoint-start");
    require_checkpoint();
    trace_stage("long-checkpoint-ready");

    trace_stage("game-new-game-start");
    reset_new_game(resetBudgetMs, "terminal-game");
    trace_stage("game-new-game-ready");
    pikafish_embedded_result_t moveResult{};
    if (!pikafish_embedded_search_nodes_with_moves(
          CompleteGameFen, "", nodes, &moveResult)
        || std::strcmp(moveResult.bestmove, "(none)") == 0)
        fail("game-move");
    print_result("GAME", 0, 0, moveResult);
    pikafish_embedded_result_t terminalResult{};
    if (!pikafish_embedded_search_nodes_with_moves(
          CompleteGameFen, moveResult.bestmove, nodes, &terminalResult)
        || std::strcmp(terminalResult.bestmove, "(none)") != 0)
        fail("game-terminal");
    print_result("GAME", 1, 1, terminalResult);
    trace_stage("game-checkpoint-start");
    require_checkpoint();
    trace_stage("game-checkpoint-ready");

    const auto stats = Stockfish::Eval::NNUE::StageBAccel::statistics();
    if (accelerated_mode()
        && (stats.evaluations == 0
            || stats.jobs != stats.evaluations * PF_STAGEB_FC0_TILE_COUNT
            || stats.fallbacks != 0 || stats.verifyMismatches != 0
            // One initial checkpoint, one implicit new-game plus one explicit
            // post-search checkpoint for every corpus round, long search and
            // terminal-game path.
            || stats.checkpoints != rounds * 2u + 5u
            || stats.checkpointFailures != 0))
        fail("statistics");
    Stockfish::Eval::NNUE::StageBAccel::report_statistics();
    pikafish_embedded_stop();
    std::printf("PIKAFISH_STAGEB_PHASE5_SEARCH_PASS mode=%s cases=%zu rounds=%u "
                "nodes=%u long_nodes=%u game=terminal evaluations=%llu jobs=%llu\n",
                mode_name(), Positions.size(), rounds, nodes, longNodes,
                static_cast<unsigned long long>(stats.evaluations),
                static_cast<unsigned long long>(stats.jobs));
    return 0;
}
