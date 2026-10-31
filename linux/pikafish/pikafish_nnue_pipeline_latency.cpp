// Full Network::evaluate latency; model/attack loading and FEN setup excluded.
// CPU-generated integer vectors are compared outside each timed interval.
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <memory>
#include <string>
#include <vector>
#include "attacks.h"
#include "position.h"
#include "nnue/network.h"
#include "nnue/nnue_accumulator.h"
#include "pikafish_attack_tables.h"
#include "pikafish_mac_runtime.h"
#include "pikafish_stageb_accel.h"
namespace {
constexpr std::array<const char*, 10> Positions = {
  "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
  "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C2C4/9/RNBAKABNR b - - 1 1",
  "2bakab2/9/c3c1n2/p3p1p1p/1npr5/2P2NP2/P3P3P/2CCB4/4A4/1NBAKR3 b - - 1 1",
  "2bak4/4a4/1c2b1n2/pC1cp1N1p/1n5r1/P1P2RP2/4P3P/N2CB4/4A4/2BAK4 b - - 10 10",
  "3ak4/1c2a4/4b1C2/p1c1p3p/9/PCP2RP1P/4P4/N1n1B4/4r4/2B2K3 b - - 1 21",
  "4k4/1c2a4/4b1C2/p1c1p3p/2P6/PC3RP1P/4P4/N1n1B4/3r5/2B2K3 b - - 4 26",
  "4k4/4a4/4b1C2/p3p3p/2c2P3/P7P/4P4/Nc6r/5K3/1R7 b - - 7 38",
  "4k4/4a4/4b1C2/p3p3p/2c2r3/P3P3P/9/Nc2K4/9/1R7 b - - 1 43",
  "4k4/9/5a1C1/p7p/6b2/PN2r3P/7C1/1c1K5/c8/R8 b - - 9 53",
  "5k3/9/3a5/p7p/6b2/Pr6P/3C5/1c1K5/c3R4/9 b - - 7 57",
};
[[noreturn]] void fail(const char* why) { std::fprintf(stderr,"NNUE_LATENCY_FAIL reason=%s\n",why);std::exit(1); }
const char* setting(const char* key,const char* fallback) {const char* value=std::getenv(key);return value&&*value?value:fallback;}
unsigned parse_samples() {
    char* end=nullptr;const char* text=setting("NNUE_SAMPLES","200");
    const unsigned long n=std::strtoul(text,&end,10);
    if(*end || n<20 || n>100000)fail("samples");
    return static_cast<unsigned>(n);
}
std::uint32_t read_u32(const unsigned char* p) { return p[0]|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24); }
void put32(unsigned char* p,std::int32_t n) { const auto v=static_cast<std::uint32_t>(n);for(unsigned i=0;i<4;++i)p[i]=static_cast<unsigned char>(v>>(8*i)); }
std::int64_t report(const char* phase,std::vector<std::int64_t>& us,unsigned samples) {
    std::int64_t sum=0;for(auto value:us)sum+=value;
    std::sort(us.begin(),us.end());
    std::printf("NNUE_LATENCY phase=%s samples=%u mean_us=%lld min_us=%lld p50_us=%lld p95_us=%lld max_us=%lld\n",
        phase,samples,static_cast<long long>(sum/samples),static_cast<long long>(us.front()),
        static_cast<long long>(us[(samples-1)/2]),static_cast<long long>(us[(samples-1)*95/100]),static_cast<long long>(us.back()));
    return sum/samples;
}
}
extern "C" int xiangqi_pikafish_gui_main(void) {
    using namespace Stockfish;
    using namespace Stockfish::Eval::NNUE;
    const char* model=setting("NNUE_MODEL","pff1-view:0x10000000:68122688");
    const char* vectors=setting("NNUE_VECTORS","/opt/pikafish/nnue10ms.vectors");
    const bool generate=std::strcmp(setting("NNUE_GENERATE","0"),"1")==0;
    const bool requireHardware=std::strcmp(setting("NNUE_REQUIRE_HW","0"),"1")==0;
    const unsigned samples=parse_samples();
    const bool chain=std::strcmp(setting("PIKAFISH_NNUE_PIPELINE","0"),"1")==0;
    timespec clockResolution{};
    if(clock_getres(CLOCK_MONOTONIC,&clockResolution))fail("clock-resolution");
    std::printf("NNUE_CLOCK clock=monotonic resolution_ns=%lld\n",
        static_cast<long long>(clockResolution.tv_sec)*1000000000+clockResolution.tv_nsec);
    Attacks::PrecomputedAttackTableMapping attacks{};
    if(std::strncmp(model,"pff1-view:",10)==0) {
        const char* error=nullptr;
        if(!Attacks::map_precomputed_attack_tables(attacks,error) ||
           !Attacks::init_precomputed(attacks.view.rook,attacks.view.rookCount,attacks.view.cannon,attacks.view.cannonCount)) fail("attack-tables");
    } else Attacks::init();
    Position::init();
    auto network=std::make_unique<Network>();EvalFile loaded{};
    network->load({},std::filesystem::path(model),loaded);
    if(!loaded.current.has_value())fail("model-load");
    auto accumulators=std::make_unique<AccumulatorStack>();
    auto caches=std::make_unique<AccumulatorCaches>(*network);
    caches->clear(*network);
    std::array<unsigned char,16+Positions.size()*8> golden{};
    if(generate) {
        if(requireHardware || std::strcmp(setting("PIKAFISH_STAGEA_ACCEL","1"),"0") ||
           std::strcmp(setting("PIKAFISH_STAGEB_ACCEL","1"),"0")) fail("generation-requires-cpu");
        std::memcpy(golden.data(),"NU10",4);put32(golden.data()+4,Positions.size());
        for(unsigned i=0;i<Positions.size();++i) {
            StateInfo state{};Position position;
            if(position.set(Positions[i],&state))fail("fen");
            accumulators->reset();const auto result=network->evaluate(position,*accumulators,*caches);
            put32(golden.data()+16+i*8,std::get<0>(result));put32(golden.data()+20+i*8,std::get<1>(result));
        }
        std::ofstream output(vectors,std::ios::binary);output.write(reinterpret_cast<const char*>(golden.data()),golden.size());
        if(!output)fail("write-vectors");
        std::printf("NNUE_VECTOR_GENERATE_PASS cases=%zu\n",Positions.size());return 0;
    }
    std::ifstream input(vectors,std::ios::binary);input.read(reinterpret_cast<char*>(golden.data()),golden.size());
    if(!input || input.peek()!=EOF || std::memcmp(golden.data(),"NU10",4) || read_u32(golden.data()+4)!=Positions.size())fail("vectors");
    if(requireHardware) {
        {
            MacRuntime::Session session(MacRuntime::Client::StageA);
            if(!session.gather_available())fail("gather-unavailable");
            if(chain && !session.pipeline_available())fail("pipeline-unavailable");
        }
        if(!MacRuntime::statistics().residentRegistered)fail("resident-unavailable");
        const auto b=StageBAccel::statistics();if(!b.prepareCalls || b.fallbacks)fail("stageb-unavailable");
    }
    bool targetMet=true;
    for(const char* phase:{"cold","warm"}) {
        caches->clear(*network);
        std::vector<std::int64_t> timings;timings.reserve(samples);
        MacRuntime::Statistics before{};
        StageBAccel::Statistics beforeB{};
        for(unsigned sample=0;sample<samples+Positions.size();++sample) {
            const unsigned i=sample%Positions.size();StateInfo state{};Position position;
            if(position.set(Positions[i],&state))fail("fen");
            if(std::strcmp(phase,"cold")==0)caches->clear(*network);
            accumulators->reset();
            if(sample==Positions.size()) {
                before=MacRuntime::statistics();beforeB=StageBAccel::statistics();
            }
            const auto start=std::chrono::steady_clock::now();
            const auto result=network->evaluate(position,*accumulators,*caches);
            const auto elapsed=std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now()-start).count();
            if(static_cast<std::uint32_t>(std::get<0>(result))!=read_u32(golden.data()+16+i*8) ||
               static_cast<std::uint32_t>(std::get<1>(result))!=read_u32(golden.data()+20+i*8))fail("integer-mismatch");
            if(sample>=Positions.size())timings.push_back(elapsed);
        }
        const auto after=MacRuntime::statistics();
        const auto afterB=StageBAccel::statistics();
        if(requireHardware && (after.fused || after.gatherCompleted<=before.gatherCompleted ||
           (chain ? after.pipelineCompleted-before.pipelineCompleted!=samples : after.completed[1]<=before.completed[1]) ||
           after.pipelineFailures!=before.pipelineFailures || afterB.fallbacks!=beforeB.fallbacks ||
           afterB.verifyMismatches!=beforeB.verifyMismatches))fail("hardware-fallback");
        if(requireHardware && after.dedicated && (!before.cacheStatsValid || !after.cacheStatsValid ||
           after.cacheRuns-before.cacheRuns!=samples || after.cacheErrors!=before.cacheErrors))fail("dedicated-cache-statistics");
        if(report(phase,timings,samples)>10000)targetMet=false;
        std::printf("NNUE_PIPELINE_BREAKDOWN phase=%s evaluations=%llu dense_jobs=%llu cycles=%llu uploads=%llu retries=%llu failures=%llu\n",phase,
            static_cast<unsigned long long>(after.pipelineCompleted-before.pipelineCompleted),
            static_cast<unsigned long long>((after.pipelineCompleted-before.pipelineCompleted)*6),
            static_cast<unsigned long long>(after.pipelineCycles-before.pipelineCycles),
            static_cast<unsigned long long>(after.pipelineUploads-before.pipelineUploads),
            static_cast<unsigned long long>(after.pipelineRetries-before.pipelineRetries),
            static_cast<unsigned long long>(after.pipelineFailures-before.pipelineFailures));
        std::printf("NNUE_LATENCY_BACKEND phase=%s stagea_jobs=%llu stageb_jobs=%llu fused=%u\n",phase,
            static_cast<unsigned long long>(after.completed[0]-before.completed[0]),
            static_cast<unsigned long long>(after.completed[1]-before.completed[1]),after.fused?1u:0u);
        if(after.dedicated)std::printf("NNUE_DEDICATED_CACHE phase=%s runs=%llu hits=%llu model_read_words=%llu restores=%llu errors=%llu\n",phase,
            static_cast<unsigned long long>(after.cacheRuns-before.cacheRuns),static_cast<unsigned long long>(after.cacheHits-before.cacheHits),
            static_cast<unsigned long long>(after.cacheReadWords-before.cacheReadWords),static_cast<unsigned long long>(after.cacheModelRestores-before.cacheModelRestores),
            static_cast<unsigned long long>(after.cacheErrors-before.cacheErrors));
        if(after.batchEnabled)std::printf("NNUE_BATCH_BREAKDOWN phase=%s calls=%llu updates=%llu cycles=%llu host_mean_us=%llu external_read_words=%llu local_read_words=%llu export_words=%llu scope=stagea_mlp_exports\n",phase,
            static_cast<unsigned long long>(after.batchCalls-before.batchCalls),static_cast<unsigned long long>(after.batchUpdates-before.batchUpdates),
            static_cast<unsigned long long>(after.batchCycles-before.batchCycles),static_cast<unsigned long long>((after.batchHostNanoseconds-before.batchHostNanoseconds)/samples/1000),
            static_cast<unsigned long long>(after.batchExternalReadWords-before.batchExternalReadWords),static_cast<unsigned long long>(after.batchLocalReadWords-before.batchLocalReadWords),
            static_cast<unsigned long long>(after.batchExportWords-before.batchExportWords));
        if(after.batchEnabled)std::printf("NNUE_ACCUM_RESIDENT phase=%s enabled=%u requested=%llu hits=%llu input_publish_saved_bytes=%llu base_read_saved_bytes=%llu\n",phase,
            after.batchResidentEnabled?1u:0u,
            static_cast<unsigned long long>(after.batchResidentRequested-before.batchResidentRequested),
            static_cast<unsigned long long>(after.batchResidentHits-before.batchResidentHits),
            static_cast<unsigned long long>((after.batchResidentHits-before.batchResidentHits)*2048),
            static_cast<unsigned long long>((after.batchResidentHits-before.batchResidentHits)*2048));
        std::printf("NNUE_LATENCY_BREAKDOWN phase=%s gather_jobs=%llu gather_terms=%llu gather_cycles=%llu gather_ioctl_mean_us=%llu fc0_cycles=%llu fc0_host_mean_us=%llu resident=%u\n",phase,
            static_cast<unsigned long long>(after.gatherCompleted-before.gatherCompleted),
            static_cast<unsigned long long>(after.gatherTerms-before.gatherTerms),
            static_cast<unsigned long long>(after.gatherCycles-before.gatherCycles),
            static_cast<unsigned long long>((after.gatherHostNanoseconds-before.gatherHostNanoseconds)/samples/1000),
            static_cast<unsigned long long>(afterB.macCycles-beforeB.macCycles),
            static_cast<unsigned long long>((afterB.hostNanoseconds-beforeB.hostNanoseconds)/samples/1000),
            after.residentRegistered?1u:0u);
    }
    StageBAccel::report_statistics();std::puts("NNUE_LATENCY_CORRECTNESS_PASS");
    if(requireHardware && std::strcmp(setting("PIKAFISH_STAGEB_ACCEL","1"),"1")==0) {
        std::puts(targetMet?"NNUE_10MS_TARGET_PASS":"NNUE_10MS_TARGET_MISS");
        return targetMet?0:2;
    }
    std::puts("NNUE_10MS_TARGET_UNMEASURED hardware_required=1 mode_required=1");
    return 0;
}
