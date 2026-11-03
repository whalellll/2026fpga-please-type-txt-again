#include "pikafish_embedded.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include "attacks.h"
#include "engine.h"
#include "misc.h"
#include "pikafish_attack_tables.h"
#if defined(PIKAFISH_STAGEB_ACCEL)
#include "pikafish_stageb_accel.h"
#endif
#include "position.h"
#include "score.h"
#include "search.h"

namespace {

std::atomic<int>                         engineStatus{PIKAFISH_EMBEDDED_IDLE};
std::unique_ptr<Stockfish::Engine>       engine;
std::unique_ptr<std::thread>             loaderThread;
std::mutex                               engineMutex;
std::string                              modelPath;
unsigned int                             hashMiB;
pikafish_embedded_result_t               searchResult{};
std::chrono::steady_clock::time_point     initStarted;
std::chrono::steady_clock::time_point     initLastStage;
#if !defined(PIKAFISH_MAC_RUNTIME_EMULATED)
Stockfish::Attacks::PrecomputedAttackTableMapping attackTableMapping;
#endif

void report_init_stage(const char* stage) {
    const auto now = std::chrono::steady_clock::now();
    const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
      now - initStarted);
    const auto delta = std::chrono::duration_cast<std::chrono::milliseconds>(
      now - initLastStage);
    std::fprintf(stdout,
                 "XQ LINUX ENGINE INIT stage=%s elapsed_ms=%lld delta_ms=%lld\n",
                 stage, static_cast<long long>(elapsed.count()),
                 static_cast<long long>(delta.count()));
    std::fflush(stdout);
    initLastStage = now;
}

void set_option(Stockfish::Engine& target, const std::string& name,
                const std::string& value) {
    std::istringstream command("name " + name + " value " + value);
    target.get_options().setoption(command);
}

void copy_move(char (&target)[8], std::string_view source) {
    const auto count = std::min(source.size(), sizeof(target) - 1u);
    std::memcpy(target, source.data(), count);
    target[count] = '\0';
}

void update_score(const Stockfish::Engine::InfoFull& info) {
    if (info.multiPV != 1)
        return;
    searchResult.nodes = static_cast<uint32_t>(
      std::min<Stockfish::usize>(info.nodes, UINT32_MAX));
    searchResult.elapsed_ms = static_cast<uint32_t>(
      std::min<Stockfish::usize>(info.timeMs, UINT32_MAX));
    if (info.score.is<Stockfish::Score::InternalUnits>())
    {
        searchResult.score_cp = info.score.get<Stockfish::Score::InternalUnits>().value;
        searchResult.have_score = 1;
    }
    else if (info.score.is<Stockfish::Score::Mate>())
    {
        const int plies = info.score.get<Stockfish::Score::Mate>().plies;
        searchResult.score_cp = plies >= 0 ? 32000 : -32000;
        searchResult.have_score = 1;
    }
    if (!info.wdl.empty())
    {
        std::istringstream values{std::string(info.wdl)};
        if (values >> searchResult.wins >> searchResult.draws >> searchResult.losses)
            searchResult.have_wdl = 1;
    }
}

void initialize_engine() {
    bool verifyFailed = false;
#if !defined(PIKAFISH_MAC_RUNTIME_EMULATED)
    const char* attackError = nullptr;
#endif
    initStarted = initLastStage = std::chrono::steady_clock::now();
    engineStatus.store(PIKAFISH_EMBEDDED_LOADING, std::memory_order_release);
    report_init_stage("attacks-map-start");
#if defined(PIKAFISH_MAC_RUNTIME_EMULATED)
    Stockfish::Attacks::init();
    report_init_stage("attacks-map-ready");
#else
    if (!Stockfish::Attacks::map_precomputed_attack_tables(attackTableMapping,
                                                           attackError)) {
        std::fprintf(stderr, "XQ LINUX ENGINE FAILED stage=attacks-map error=%s\n",
                     attackError ? attackError : "unknown");
        engineStatus.store(PIKAFISH_EMBEDDED_FAILED, std::memory_order_release);
        return;
    }
    report_init_stage("attacks-map-ready");
    if (!Stockfish::Attacks::init_precomputed(
          attackTableMapping.view.rook, attackTableMapping.view.rookCount,
          attackTableMapping.view.cannon, attackTableMapping.view.cannonCount)) {
        std::fprintf(stderr, "XQ LINUX ENGINE FAILED stage=attacks-bind\n");
        Stockfish::Attacks::unmap_precomputed_attack_tables(attackTableMapping);
        engineStatus.store(PIKAFISH_EMBEDDED_FAILED, std::memory_order_release);
        return;
    }
#endif
    report_init_stage("attacks-ready");
    Stockfish::Position::init();
    report_init_stage("position-ready");
    report_init_stage("constructor-start");
    auto next = std::make_unique<Stockfish::Engine>(
      std::nullopt, hashMiB,
      std::make_optional(std::filesystem::path(modelPath)));
    report_init_stage("constructor-ready");
    set_option(*next, "UCI_ShowWDL", "true");
    report_init_stage("options-ready");
    next->set_on_update_no_moves([](const auto&) {});
    next->set_on_iter([](const auto&) {});
    next->set_on_start([]() {});
    next->set_on_update_full([](const auto& info) { update_score(info); });
    next->set_on_bestmove([](std::string_view bestmove, std::string_view ponder) {
        copy_move(searchResult.bestmove, bestmove);
        copy_move(searchResult.ponder, ponder);
    });
    next->set_on_verify_network([&verifyFailed](std::string_view message) {
        if (message.find("ERROR:") != std::string_view::npos)
            verifyFailed = true;
        std::fprintf(stdout, "info string %.*s\n", static_cast<int>(message.size()),
                     message.data());
        std::fflush(stdout);
    });
    report_init_stage("verify-start");
    next->verify_network();
    report_init_stage("verify-ready");
    if (verifyFailed) {
        std::fprintf(stderr, "info string PIKAFISH_EMBEDDED_FAILED model=%s\n",
                     modelPath.c_str());
        engineStatus.store(PIKAFISH_EMBEDDED_FAILED, std::memory_order_release);
        return;
    }
    // Verification also runs before every search. Do not retain the startup
    // thread's stack-local failure flag in the long-lived Engine callback.
    next->set_on_verify_network([](std::string_view message) {
        std::fprintf(stdout, "info string %.*s\n", static_cast<int>(message.size()),
                     message.data());
        std::fflush(stdout);
    });
    {
        std::lock_guard<std::mutex> lock(engineMutex);
        engine = std::move(next);
    }
    engineStatus.store(PIKAFISH_EMBEDDED_READY, std::memory_order_release);
    std::puts("XQ LINUX ENGINE DIRECT CORE READY");
    std::fflush(stdout);
}

}  // namespace

extern "C" int pikafish_embedded_start(const char* path, unsigned int requestedHashMiB) {
    int expected = PIKAFISH_EMBEDDED_IDLE;
    if (!path || !*path || requestedHashMiB == 0
        || !engineStatus.compare_exchange_strong(expected, PIKAFISH_EMBEDDED_LOADING))
        return 0;
    modelPath = path;
    hashMiB   = requestedHashMiB;
    loaderThread = std::make_unique<std::thread>(initialize_engine);
    return 1;
}

extern "C" int pikafish_embedded_status(void) {
    // The GUI calls this from its input loop. Even after READY is published,
    // joining the loader thread here can block that loop during thread exit.
    // The Engine is fully published before READY; stop() owns the final join.
    return engineStatus.load(std::memory_order_acquire);
}

namespace {

bool parse_move_history(const char* text, std::vector<std::string>& moves) {
    if (!text || !*text)
        return true;
    if (std::strlen(text) > 4096u)
        return false;
    std::istringstream input(text);
    std::string move;
    while (input >> move)
    {
        if (move.size() != 4u || moves.size() >= 512u)
            return false;
        moves.push_back(move);
    }
    return input.eof();
}

int search_with_limits(const char* fen, const char* movesText, unsigned int movetimeMs,
                       std::uint64_t nodes, pikafish_embedded_result_t* result) {
    if (!fen || !result || ((movetimeMs == 0) == (nodes == 0))
        || engineStatus.load(std::memory_order_acquire) != PIKAFISH_EMBEDDED_READY)
        return 0;
    std::vector<std::string> moves;
    if (!parse_move_history(movesText, moves))
    {
        std::fprintf(stderr, "XQ LINUX SEARCH FAILED stage=parse-moves\n");
        std::fflush(stderr);
        return 0;
    }
    std::lock_guard<std::mutex> lock(engineMutex);
    if (!engine)
        return 0;
    std::memset(&searchResult, 0, sizeof(searchResult));
    if (auto error = engine->set_position(fen, moves))
    {
        std::fprintf(stderr,
                     "XQ LINUX SEARCH FAILED stage=set-position error=%s fen=%s\n",
                     error->what(), fen);
        std::fflush(stderr);
        return 0;
    }
    if (nodes != 0)
        std::fprintf(stdout, "XQ LINUX SEARCH START nodes=%llu moves=%zu fen=%s\n",
                     static_cast<unsigned long long>(nodes), moves.size(), fen);
    else
        std::fprintf(stdout, "XQ LINUX SEARCH START movetime_ms=%u moves=%zu fen=%s\n",
                     movetimeMs, moves.size(), fen);
    std::fflush(stdout);
    Stockfish::Search::LimitsType limits;
    limits.startTime = Stockfish::now();
    limits.movetime  = static_cast<Stockfish::TimePoint>(movetimeMs);
    limits.nodes     = nodes;
    engine->go(limits);
    engine->wait_for_search_finished();
    *result = searchResult;
    if (searchResult.bestmove[0] == '\0')
    {
        std::fprintf(stderr,
                     "XQ LINUX SEARCH FAILED stage=no-bestmove nodes=%u elapsed_ms=%u\n",
                     searchResult.nodes, searchResult.elapsed_ms);
        std::fflush(stderr);
        return 0;
    }
    return 1;
}

}  // namespace

extern "C" int pikafish_embedded_search(const char* fen, unsigned int movetimeMs,
                                         pikafish_embedded_result_t* result) {
    return search_with_limits(fen, "", movetimeMs, 0, result);
}

extern "C" int pikafish_embedded_search_nodes(const char* fen, std::uint64_t nodes,
                                               pikafish_embedded_result_t* result) {
    return search_with_limits(fen, "", 0, nodes, result);
}

extern "C" int pikafish_embedded_search_nodes_with_moves(
  const char* fen, const char* moves, std::uint64_t nodes,
  pikafish_embedded_result_t* result) {
    return search_with_limits(fen, moves, 0, nodes, result);
}

extern "C" void pikafish_embedded_new_game(void) {
    if (engineStatus.load(std::memory_order_acquire) != PIKAFISH_EMBEDDED_READY)
        return;
    const auto started = std::chrono::steady_clock::now();
    std::lock_guard<std::mutex> lock(engineMutex);
    if (!engine)
        return;
    bool checkpointReady = true;
#if defined(PIKAFISH_STAGEB_ACCEL)
    // A GUI search always supplies a complete FEN plus its move history, so
    // no mutable game position is retained in Engine between requests.  Audit
    // the resident accelerator image at this lifecycle boundary, but retain
    // the key-addressed TT and move-ordering histories.  Their entries cannot
    // alter chess legality or evaluation correctness and are useful warm
    // caches; Engine::search_clear() would synchronously rewrite tens of MiB
    // on the 27 MHz target and freeze the GUI after every restart.
    checkpointReady = Stockfish::Eval::NNUE::StageBAccel::checkpoint();
#endif
    const auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
      std::chrono::steady_clock::now() - started);
    std::fprintf(stdout,
                 "XQ LINUX ENGINE NEW GAME READY reset=position-snapshot "
                 "tt=retained histories=retained checkpoint=%s elapsed_us=%lld\n",
                 checkpointReady ? "pass" : "cpu-fallback",
                 static_cast<long long>(elapsed.count()));
    std::fflush(stdout);
}

extern "C" void pikafish_embedded_stop(void) {
    if (loaderThread && loaderThread->joinable())
        loaderThread->join();
    loaderThread.reset();
    std::lock_guard<std::mutex> lock(engineMutex);
    if (engine)
        engine->stop();
#if defined(PIKAFISH_STAGEB_ACCEL)
    Stockfish::Eval::NNUE::StageBAccel::report_statistics();
#endif
    engine.reset();
#if !defined(PIKAFISH_MAC_RUNTIME_EMULATED)
    Stockfish::Attacks::unmap_precomputed_attack_tables(attackTableMapping);
#endif
    engineStatus.store(PIKAFISH_EMBEDDED_IDLE, std::memory_order_release);
}
