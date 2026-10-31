#include <cstdio>
#include <cstring>
#include <type_traits>

#include "history.h"

namespace {

template<typename T>
bool expect_value(const char* name, const T& value, int expected) {
    const int actual = static_cast<int>(value);
    if (actual == expected)
        return true;

    std::fprintf(stderr, "%s: expected %d, got %d\n", name, expected, actual);
    return false;
}

}  // namespace

int main() {
    using namespace Stockfish;

    using TinyPawnBlock = OffsetAtomicStats<i16, 8192, -1247, 2, 3>;
    using TinyPawnHistory = DynStats<TinyPawnBlock, 2, -1247>;

    static_assert(std::is_trivially_copyable_v<ButterflyHistory>);
    static_assert(std::is_trivially_copyable_v<CapturePieceToHistory>);
    static_assert(std::is_trivially_copyable_v<PieceToHistory>);
    static_assert(std::is_trivially_copyable_v<CorrectionHistory<PieceTo>>);
    static_assert(std::is_trivially_copyable_v<ContinuationHistoryBlock>);

    ButterflyHistory mainHistory{};
    CapturePieceToHistory captureHistory{};
    PieceToHistory continuationHistory{};
    CorrectionHistory<PieceTo> localCorrection{};
    CorrectionBundle<i16, CORRECTION_HISTORY_LIMIT, -6> sharedCorrection{};
    OffsetAtomicStats<i16, 8192, -1247, PIECE_NB, SQUARE_NB> pawnHistory{};
    TinyPawnHistory dynamicPawnHistory(2);

    bool ok = true;
    ok &= expect_value("main-zero", mainHistory[0][0], -5);
    ok &= expect_value("capture-zero", captureHistory[0][0][0], -607);
    ok &= expect_value("continuation-zero", continuationHistory[0][0], -436);
    ok &= expect_value("local-correction-zero", localCorrection[0][0], 7);
    ok &= expect_value("shared-correction-zero", sharedCorrection.pawn, -6);
    ok &= expect_value("pawn-zero", pawnHistory[0][0], -1247);
    ok &= expect_value("dynamic-pawn-first-zero", dynamicPawnHistory[0][0][0], -1247);
    ok &= expect_value("dynamic-pawn-last-zero", dynamicPawnHistory[3][1][2], -1247);

    pawnHistory[0][0] << 100;
    ok &= expect_value("pawn-update", pawnHistory[0][0], -1132);
    pawnHistory[0][0] = 8192;
    ok &= expect_value("pawn-upper-bound", pawnHistory[0][0], 8192);
    pawnHistory[0][0] = -8192;
    ok &= expect_value("pawn-lower-bound", pawnHistory[0][0], -8192);

    // Exercise the same bulk-reset path used by ucinewgame.  Splitting the
    // range also checks that one worker cannot erase another worker's slice.
    dynamicPawnHistory[0][0][0] = 111;
    dynamicPawnHistory[3][1][2] = 222;
    dynamicPawnHistory.clear_range(-1247, 0, 2);
    ok &= expect_value("dynamic-pawn-first-reset", dynamicPawnHistory[0][0][0], -1247);
    ok &= expect_value("dynamic-pawn-second-preserved", dynamicPawnHistory[3][1][2], 222);
    dynamicPawnHistory.clear_range(-1247, 1, 2);
    ok &= expect_value("dynamic-pawn-last-reset", dynamicPawnHistory[3][1][2], -1247);

    dynamicPawnHistory.clear_range(-100, 0, 2);
    ok &= expect_value("dynamic-pawn-nondefault-fill", dynamicPawnHistory[0][1][2], -100);
    dynamicPawnHistory.clear_range(-1247, 0, 2);
    ok &= expect_value("dynamic-pawn-nondefault-reset", dynamicPawnHistory[0][1][2], -1247);

    mainHistory[0][0] = 321;
    captureHistory[0][0][0] = -222;
    continuationHistory[0][0] = 1234;
    localCorrection[0][0] = -77;
    sharedCorrection.pawn = 55;
    std::memset(&mainHistory, 0, sizeof(mainHistory));
    std::memset(&captureHistory, 0, sizeof(captureHistory));
    std::memset(&continuationHistory, 0, sizeof(continuationHistory));
    std::memset(&localCorrection, 0, sizeof(localCorrection));
    std::memset(&sharedCorrection, 0, sizeof(sharedCorrection));

    ok &= expect_value("main-reset", mainHistory[0][0], -5);
    ok &= expect_value("capture-reset", captureHistory[0][0][0], -607);
    ok &= expect_value("continuation-reset", continuationHistory[0][0], -436);
    ok &= expect_value("local-correction-reset", localCorrection[0][0], 7);
    ok &= expect_value("shared-correction-reset", sharedCorrection.pawn, -6);

    if (!ok)
        return 1;

    std::printf("PIKAFISH_HISTORY_LAYOUT main=%zu capture=%zu continuation_block=%zu "
                "local_correction=%zu\n",
                sizeof(mainHistory), sizeof(captureHistory),
                sizeof(ContinuationHistoryBlock), sizeof(localCorrection));
    std::puts("PIKAFISH_HISTORY_ZERO_STATE_TEST_PASS");
    return 0;
}
