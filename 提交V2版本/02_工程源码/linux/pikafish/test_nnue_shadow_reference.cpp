// A full-pipeline verification reference must not submit a generic FC0 job.
#include <cassert>
#ifndef STAGEB_IMPL
#define STAGEB_IMPL "pikafish_stageb_accel.cpp"
#endif
#include STAGEB_IMPL
int main() {
    using namespace Stockfish::Eval::NNUE::StageBAccel;
    std::uint8_t input[1024]{};
    std::int32_t output[32];
    for (auto& lane: output) lane=0x12345678;
    auto& s=runtime();s.ready=true;s.mode=Mode::Verify;
    pipelineResult={input,11,2392,true,true};
    const auto before=statistics();
    assert(!fc0(11,input,output));
    for (auto lane: output) assert(lane==0x12345678);
    const auto after=statistics();
    assert(after.fallbacks==before.fallbacks);
    assert(after.jobs==before.jobs);
    assert(pipelineResult.valid);
    verify_pipeline(11,input,2392);
    assert(!pipelineResult.valid && statistics().verifyMismatches==0);
    std::puts("NNUE_SHADOW_CPU_REFERENCE_PASS");
}
