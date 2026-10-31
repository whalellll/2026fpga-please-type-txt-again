/* Dedicated engine service. Only fd3 is a machine-readable private protocol;
 * inherited stdout/stderr are discarded by engine_bridge to keep live FEN
 * out of UART logs. Links the same official prepared engine as T1. */
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
#include <thread>
#if XINYI_BATTLE_R17
#include <time.h>
#endif

namespace {
std::uint32_t u32(const std::uint8_t *p) {
    return p[0]|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);
}
bool prepare() {
    using namespace Stockfish::Eval::NNUE;
    if(setenv("PIKAFISH_MAC_BACKEND","driver",1) ||
       setenv("PIKAFISH_MAC_REQUIRE_DRIVER","1",1) ||
       setenv("PIKAFISH_MAC_REQUIRE_FEATURES","2531",1) ||
       setenv("PIKAFISH_NNUE_PIPELINE","1",1) ||
       setenv("PIKAFISH_NNUE_BATCH","1",1) ||
       setenv("PIKAFISH_STAGEA_ACCEL","1",1) ||
       setenv("PIKAFISH_STAGEB_ACCEL","1",1))return false;
    const char *pack=std::getenv("PIKAFISH_STAGEB_PACK");
    if(!pack || !*pack)return false; /* Bound by product kit, never guessed. */
    std::ifstream in(pack,std::ios::binary);
    std::array<std::uint8_t,PF_STAGEB_H_HEADER_CRC32+4u> h{};
    in.read(reinterpret_cast<char *>(h.data()),h.size());
    if(!in || u32(h.data()+PF_STAGEB_H_MAGIC)!=PF_STAGEB_PACK_MAGIC)return false;
    StageBAccel::ModelBinding binding{};
    std::memcpy(binding.decodedStreamSha256,h.data()+PF_STAGEB_H_DECODED_SHA256,
                sizeof(binding.decodedStreamSha256));
    binding.mlpsBytes=u32(h.data()+PF_STAGEB_H_MLPS_BYTES);
    binding.mlpsCrc32=u32(h.data()+PF_STAGEB_H_MLPS_CRC32);
    return StageBAccel::prepare(binding);
}
bool hardware_ok() {
    using namespace Stockfish::Eval::NNUE;
    const auto stage=StageBAccel::statistics();const auto mac=MacRuntime::statistics();
    return !stage.fallbacks && !stage.verifyMismatches && !mac.fused && !mac.pipelineFailures;
}
}

extern "C" int xiangqi_pikafish_gui_main(void) {
    FILE *protocol=fdopen(3,"w");if(!protocol)return 2;
    setvbuf(protocol,nullptr,_IOLBF,0);
    const char *model=std::getenv("PIKAFISH_EMBEDDED_MODEL");
    if(!model || !*model || !prepare() || !pikafish_embedded_start(model,8))return 3;
    const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(170);
    for(;;){
        int state=pikafish_embedded_status();
        if(state==PIKAFISH_EMBEDDED_READY)break;
        if(state==PIKAFISH_EMBEDDED_FAILED || std::chrono::steady_clock::now()>=deadline)return 4;
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    if(!hardware_ok() || std::fputs("XQ_ENGINE_READY_V1\n",protocol)<0)return 5;
    char line[256];
    while(std::fgets(line,sizeof(line),stdin)){
        unsigned token=0,revision=0,crc=0,nodes=0;int offset=0;
        if(!std::strchr(line,'\n') ||
           std::sscanf(line,"XQ_ENGINE_REQUEST_V1 %u %u %x %u %n",&token,&revision,&crc,&nodes,&offset)!=4 ||
           !offset || !token || !revision || nodes<16 || nodes>1000000)return 6;
        char *fen=line+offset;size_t length=std::strlen(fen);
        if(length<8 || length>=128 || fen[length-1]!='\n')return 6;
        fen[length-1]=0;
        pikafish_embedded_result_t result{};
        pikafish_embedded_new_game();
        bool okay=hardware_ok() && pikafish_embedded_search_nodes(fen,nodes,&result) && hardware_ok();
#if XINYI_BATTLE_R17
        // Stamp when the validated result becomes available in the producer,
        // before protocol transport or GUI scheduling can delay its consumer.
        timespec ready{};std::uint64_t readyUs=0;
        if(okay && !clock_gettime(CLOCK_MONOTONIC,&ready))
            readyUs=std::uint64_t(ready.tv_sec)*1000000u+std::uint64_t(ready.tv_nsec)/1000u;
#endif
        unsigned us=result.elapsed_ms>UINT32_MAX/1000u?UINT32_MAX:result.elapsed_ms*1000u;
#if XINYI_BATTLE_R17
        if(std::fprintf(protocol,"XQ_ENGINE_RESULT_V2 %u %u %08x %u %s %d %u %u %u %u %u %u %llu\n",
            token,revision,crc,okay?1u:0u,okay?result.bestmove:"0000",result.score_cp,result.nodes,
            result.wins,result.draws,result.losses,us,result.have_wdl?1u:0u,
            static_cast<unsigned long long>(readyUs))<0)return 7;
#else
        if(std::fprintf(protocol,"XQ_ENGINE_RESULT_V1 %u %u %08x %u %s %d %u %u %u %u %u %u\n",
            token,revision,crc,okay?1u:0u,okay?result.bestmove:"0000",result.score_cp,result.nodes,
            result.wins,result.draws,result.losses,us,result.have_wdl?1u:0u)<0)return 7;
#endif
        if(!okay)return 8; /* Caller receives failure, never a software move. */
    }
    pikafish_embedded_stop();return 0;
}
