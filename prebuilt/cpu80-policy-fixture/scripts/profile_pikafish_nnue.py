"""Build an isolated NNUE diagnostic, leaving production sources/objects intact.

Uses the already prepared, pinned Pikafish source and the original O3/LTO flags.
Run on Windows, then run the emitted build.sh in the project's WSL toolchain.
"""
import argparse
import json
from pathlib import Path
import shutil

STAGES = ["network", "accumulator", "feature_transform", "refresh_psq_indices",
          "refresh_threat_indices", "refresh_vectors", "refresh_psqt", "stagea_session",
          "stagea_descriptors", "stagea_copyin", "stagea_gather", "stagea_copyout",
          "fc0", "fc0_setup", "fc0_pack", "fc0_submit", "fc0_ioctl", "fc0_merge",
          "activation0", "fc1", "activation1", "fc2", "mlp_post"]


def prepare(root, output):
    source = root / "build/pikafish-rv32/source/src"
    stage = output / "src"
    if root / 'build' not in output.parents:
        raise ValueError('Diagnostic output must be a directory under this project build/')
    if stage == source or source in stage.parents or stage in source.parents:
        raise ValueError('Diagnostic output overlaps the original Pikafish source')
    shutil.copytree(source, stage, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.o", "*.d", "pikafish"))
    names = ",".join('"' + n + '"' for n in STAGES)
    header = r'''#pragma once
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
extern "C" std::uint64_t nnue_profile_counter();
extern "C" std::uint32_t nnue_profile_counter_hz();
namespace NNUEProfile {
inline bool enabled = false;
inline std::uint64_t totals[23]{}, counts[23]{};
inline const char* names[23] = {NAMES};
inline std::uint64_t now() {
    if (!enabled) return 0;
    return nnue_profile_counter();
}
inline std::uint64_t ns(std::uint64_t ticks) {
    const auto hz=nnue_profile_counter_hz();
    return (ticks/hz)*1000000000ull+(ticks%hz)*1000000000ull/hz;
}
inline void add(unsigned id, std::uint64_t started) {
    if (!enabled) return;
    totals[id] += now()-started; ++counts[id];
}
inline void reset() { std::memset(totals,0,sizeof(totals)); std::memset(counts,0,sizeof(counts)); }
inline void report(const char* phase, unsigned samples) {
    for (unsigned i=0;i<23;++i)
        std::printf("NNUE_PROFILE phase=%s stage=%s calls=%llu total_ns=%llu mean_us=%llu\n",
          phase,names[i],(unsigned long long)counts[i],(unsigned long long)ns(totals[i]),
          (unsigned long long)(ns(totals[i])/samples/1000));
}
struct Scope {
    unsigned id; std::uint64_t start;
    explicit Scope(unsigned i):id(i),start(now()){}
    ~Scope(){add(id,start);}
};
}
'''.replace("NAMES", names)
    (stage / "nnue_profile.h").write_text(header, encoding="utf-8")

    def edit(file, replacements):
        path = stage / file
        text = path.read_text(encoding="utf-8")
        include = '../nnue_profile.h' if file.startswith('nnue/') else 'nnue_profile.h'
        text = '#include "' + include + '"\n' + text
        for old, new in replacements:
            if text.count(old) != 1:
                raise ValueError(f"{file}: expected one match, got {text.count(old)}: {old[:100]}")
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")

    edit("nnue/network.cpp", [("NetworkOutput Network::evaluate(const Position&    pos,\n                                AccumulatorStack&  accumulatorStack,\n                                AccumulatorCaches& cache) const {",
         "NetworkOutput Network::evaluate(const Position&    pos,\n                                AccumulatorStack&  accumulatorStack,\n                                AccumulatorCaches& cache) const {\n    NNUEProfile::Scope profileNetwork(0);")])
    edit("nnue/nnue_feature_transformer.h", [
        ("        accumulatorStack.evaluate(pos, *this, cache);", "        auto profileMark=NNUEProfile::now();\n        accumulatorStack.evaluate(pos, *this, cache);\n        NNUEProfile::add(1,profileMark); profileMark=NNUEProfile::now();"),
        ("        return psqt;", "        NNUEProfile::add(2,profileMark);\n        return psqt;")])

    edit("nnue/nnue_accumulator.cpp", [
        ("    auto [bucket, mirror, attack_bucket] = PSQFeatureSet::make_feature_bucket(perspective, pos);",
         "    auto profileMark=NNUEProfile::now();\n    auto [bucket, mirror, attack_bucket] = PSQFeatureSet::make_feature_bucket(perspective, pos);"),
        ("    ThreatFeatureSet::IndexList active;\n    ThreatFeatureSet::append_active_indices(perspective, pos, active);",
         "    NNUEProfile::add(3,profileMark); profileMark=NNUEProfile::now();\n    ThreatFeatureSet::IndexList active;\n    ThreatFeatureSet::append_active_indices(perspective, pos, active);\n    NNUEProfile::add(4,profileMark); profileMark=NNUEProfile::now();"),
        ("    PsqtTile psqt;\n    for (IndexType j = 0; j < PSQTBuckets; increment_psqt_index(j))\n    {\n        psqt = load_psqt(j, entry.psqtAccumulation.data());",
         "    NNUEProfile::add(5,profileMark); profileMark=NNUEProfile::now();\n    PsqtTile psqt;\n    for (IndexType j = 0; j < PSQTBuckets; increment_psqt_index(j))\n    {\n        psqt = load_psqt(j, entry.psqtAccumulation.data());"),
        ("        store_psqt(j, accumulator.psqtAccumulation[perspective].data(), psqt);\n    }\n}\n\n}",
         "        store_psqt(j, accumulator.psqtAccumulation[perspective].data(), psqt);\n    }\n    NNUEProfile::add(6,profileMark);\n}\n\n}")])

    edit("nnue/nnue_architecture.h", [
        ("        Buffer buffer;", "        auto profileMark=NNUEProfile::now();\n        Buffer buffer;"),
        ("#if defined(USE_PAIR_ACTIVATIONS)\n        ac_sqr_0", "        NNUEProfile::add(12,profileMark); profileMark=NNUEProfile::now();\n#if defined(USE_PAIR_ACTIVATIONS)\n        ac_sqr_0"),
        ("        fc_1.propagate(buffer.concat_buffer, buffer.fc_1_out);", "        NNUEProfile::add(18,profileMark); profileMark=NNUEProfile::now();\n        fc_1.propagate(buffer.concat_buffer, buffer.fc_1_out);\n        NNUEProfile::add(19,profileMark); profileMark=NNUEProfile::now();"),
        ("        fc_2.propagate(buffer.concat_buffer, buffer.fc_2_out);", "        NNUEProfile::add(20,profileMark); profileMark=NNUEProfile::now();\n        fc_2.propagate(buffer.concat_buffer, buffer.fc_2_out);\n        NNUEProfile::add(21,profileMark); profileMark=NNUEProfile::now();"),
        ("        return outputValue;", "        NNUEProfile::add(22,profileMark);\n        return outputValue;")])

    # The Stage A source has another Session in model preparation: target apply only.
    edit("pikafish_stagea_accel.cpp", [
        ("    MacRuntime::Session session(MacRuntime::Client::StageA);\n    if (!session)\n        return false;",
         "    auto profileMark=NNUEProfile::now();\n    MacRuntime::Session session(MacRuntime::Client::StageA);\n    NNUEProfile::add(7,profileMark); profileMark=NNUEProfile::now();\n    if (!session)\n        return false;"),
        ("        std::memcpy(parent,base,MacRuntime::StageAGatherBaseBytes);",
         "        NNUEProfile::add(8,profileMark); profileMark=NNUEProfile::now();\n        std::memcpy(parent,base,MacRuntime::StageAGatherBaseBytes);\n        NNUEProfile::add(9,profileMark); profileMark=NNUEProfile::now();"),
        ("        std::memcpy(out,result,MacRuntime::StageAGatherOutputBytes);",
         "        NNUEProfile::add(10,profileMark); profileMark=NNUEProfile::now();\n        std::memcpy(out,result,MacRuntime::StageAGatherOutputBytes);\n        NNUEProfile::add(11,profileMark);")])
    edit("pikafish_stageb_accel.cpp", [
        ("    const auto evaluationStarted = Clock::now();", "    auto profileMark=NNUEProfile::now();\n    const auto evaluationStarted = Clock::now();"),
        ("    std::uint64_t evaluationCycles = 0;", "    NNUEProfile::add(13,profileMark);\n    std::uint64_t evaluationCycles = 0;"),
        ("        for (unsigned feature = 0; feature < 256; ++feature)", "        profileMark=NNUEProfile::now();\n        for (unsigned feature = 0; feature < 256; ++feature)"),
        ("        __sync_synchronize();\n        MacRuntime::Job job{};", "        NNUEProfile::add(14,profileMark); profileMark=NNUEProfile::now();\n        __sync_synchronize();\n        MacRuntime::Job job{};"),
        ("        evaluationCycles += tileCycles;", "        NNUEProfile::add(15,profileMark); profileMark=NNUEProfile::now();\n        evaluationCycles += tileCycles;"),
        ("            accumulated[lane] += read_u32(outputScratch + lane * sizeof(std::uint32_t));", "            accumulated[lane] += read_u32(outputScratch + lane * sizeof(std::uint32_t));\n        NNUEProfile::add(17,profileMark);")])
    edit("pikafish_mac_runtime.cpp", [
        ("        if (ioctl(state.deviceFd, command, &request) != 0)",
         "        const auto profileMark=NNUEProfile::now();\n        const int profileIoctlResult=ioctl(state.deviceFd, command, &request);\n        NNUEProfile::add(16,profileMark);\n        if (profileIoctlResult != 0)")])

    harness = (root / "linux/pikafish/pikafish_nnue_latency.cpp").read_text(encoding="utf-8")
    harness = '#include "nnue_profile.h"\n' + harness
    harness = '#include "pf_mlp_mac_pack.h"\n' + harness
    harness = harness.replace('    const char* model=setting(', '    std::setvbuf(stdout,nullptr,_IONBF,0);\n    const char* model=setting(')
    harness = harness.replace('    bool targetMet=true;', '''    NNUEProfile::enabled=std::strcmp(setting("NNUE_PROFILE","0"),"1")==0;
    if(NNUEProfile::enabled) {
        const auto begin=NNUEProfile::now();
        for(unsigned i=0;i<10000;++i){auto t=NNUEProfile::now();NNUEProfile::add(0,t);}
        const auto total=NNUEProfile::now()-begin;
        std::printf("NNUE_PROFILE_CALIBRATION pairs=10000 mean_pair_ns=%llu\\n",(unsigned long long)(NNUEProfile::ns(total)/10000));
        NNUEProfile::reset();
    }
    if(std::strcmp(setting("NNUE_PROFILE_MICRO","0"),"1")==0) {
        if(!requireHardware || !NNUEProfile::enabled) fail("micro-requires-strict-profile");
        constexpr unsigned count=50, warmup=5;
        for(unsigned terms:{2u,4u,16u,64u,256u}) {
            MacRuntime::Session session(MacRuntime::Client::StageA);
            auto* descriptors=reinterpret_cast<std::uint32_t*>(session.ddr(MacRuntime::StageAWeightOffset,terms*4));
            auto* base=session.ddr(MacRuntime::StageAInputOffset,2048);
            auto* output=session.ddr(MacRuntime::StageAOutputOffset,2048);
            if(!session || !descriptors || !base || !output) fail("micro-gather-context");
            std::memset(base,0,2048);
            for(unsigned i=0;i<terms;++i) descriptors[i]=(i%2)?0x80000000u:0u;
            std::uint64_t elapsed=0,cycles=0;
            for(unsigned i=0;i<count+warmup;++i) {
                std::memset(output,0x5a,2048);
                std::uint32_t jobCycles=0;
                const auto t=NNUEProfile::now();
                if(!session.gather(terms,&jobCycles)) fail("micro-gather-run");
                const auto end=NNUEProfile::now();
                for(unsigned j=0;j<2048;++j) if(output[j]!=0) fail("micro-gather-integer");
                if(i>=warmup){elapsed+=end-t;cycles+=jobCycles;}
            }
            std::printf("NNUE_MICRO engine=gather terms=%u cin=0 cout=1024 samples=%u host_mean_us=%llu hw_mean_us=%llu cycles=%llu copy_bytes=%u mismatches=0\\n",
                terms,count,(unsigned long long)(NNUEProfile::ns(elapsed)/count/1000),
                (unsigned long long)(cycles*1000000ull/count/49500000),
                (unsigned long long)cycles,4096+terms*4);
        }
        for(unsigned cin:{4u,16u,64u,256u}) for(unsigned cout:{1u,32u}) {
            MacRuntime::Session session(MacRuntime::Client::StageB);
            auto* input=session.ddr(MacRuntime::StageBInputOffset,512);
            auto* output=session.ddr(MacRuntime::StageBOutputOffset,128);
            if(!session || !input || !output) fail("micro-dense-context");
            std::memset(input,0,512);
            MacRuntime::Job job{};
            job.pixels=1;job.cin=cin;job.cout=cout;
            job.computeMode=MacRuntime::ComputeMode::U8S8;
            job.outputFormat=MacRuntime::OutputFormat::I32;job.zeroBias=true;
            job.inputOffset=MacRuntime::StageBInputOffset;
            job.weightOffset=pf_stageb_fc0_tile_offset(0,0);
            job.biasOffset=MacRuntime::StageBInputOffset;job.outputOffset=MacRuntime::StageBOutputOffset;
            std::uint64_t elapsed=0,cycles=0;
            for(unsigned i=0;i<count+warmup;++i) {
                std::memset(output,0x5a,128);
                std::uint32_t jobCycles=0;
                const auto t=NNUEProfile::now();
                if(!session.submit(job,&jobCycles)) fail("micro-dense-run");
                const auto end=NNUEProfile::now();
                for(unsigned j=0;j<cout*4;++j) if(output[j]!=0) fail("micro-dense-integer");
                if(i>=warmup){elapsed+=end-t;cycles+=jobCycles;}
            }
            std::printf("NNUE_MICRO engine=dense terms=0 cin=%u cout=%u samples=%u host_mean_us=%llu hw_mean_us=%llu cycles=%llu copy_bytes=%u mismatches=0\\n",
                cin,cout,count,(unsigned long long)(NNUEProfile::ns(elapsed)/count/1000),
                (unsigned long long)(cycles*1000000ull/count/49500000),
                (unsigned long long)cycles,cin*2+cout*4);
        }
        std::puts("NNUE_MICRO_CORRECTNESS_PASS");
        NNUEProfile::reset();
    }
    bool targetMet=true;''')
    harness = harness.replace('                before=MacRuntime::statistics();', '                NNUEProfile::reset();\n                before=MacRuntime::statistics();')
    harness = harness.replace('        const auto after=MacRuntime::statistics();', '        if(NNUEProfile::enabled) NNUEProfile::report(phase,samples);\n        const auto after=MacRuntime::statistics();')
    (output / "latency.cpp").write_text(harness, encoding="utf-8")
    clock = (root / 'linux/pikafish/nnue_clint_clock.c').read_text(encoding='utf-8') + '''
/* Diagnostic-only raw counter: convert outside the evaluation interval. */
uint64_t nnue_profile_counter(void) {
    pthread_once(&once, init_clock);
    if (clock_error) abort();
    if (use_linux) {
        struct timespec t;
        if (__real_clock_gettime(CLOCK_MONOTONIC,&t)) abort();
        return (uint64_t)t.tv_sec*1000000000ull+t.tv_nsec;
    }
    return ticks();
}
uint32_t nnue_profile_counter_hz(void) {
    pthread_once(&once, init_clock);
    if (clock_error) abort();
    return use_linux ? 1000000000u : CLINT_HZ;
}
'''
    (output / 'profile_clock.c').write_text(clock, encoding='utf-8')
    wsl_root = '/mnt/' + root.drive[0].lower() + root.as_posix()[2:]
    wsl_out = '/mnt/' + output.drive[0].lower() + output.as_posix()[2:]
    build = f'''#!/bin/sh
set -eu
root='{wsl_root}'
out='{wsl_out}'
cross=/opt/toolchain/bin/riscv32-linux-musl-g++
flags=$(cat "$root/build/vision/board_candidate_20261009_004155/original-link-flags.txt")
/opt/toolchain/bin/riscv32-linux-musl-gcc -std=gnu11 -Os -flto -march=rv32ima -mabi=ilp32 \\
 -Wall -Wextra -Werror -c "$out/profile_clock.c" -o "$out/profile_clock.o"
for unit in nnue/network nnue/nnue_accumulator pikafish_stagea_accel pikafish_stageb_accel pikafish_mac_runtime; do
  name=${{unit##*/}}
  "$cross" $flags -iquote "$out/src" -c "$out/src/$unit.cpp" -o "$out/$name.o"
done
"$cross" $flags -iquote "$out/src" -c "$out/latency.cpp" -o "$out/latency.o"
objects=
for object in "$root/build/pikafish-rv32/source/src/"*.o; do
  case ${{object##*/}} in
    network.o|nnue_accumulator.o|pikafish_stagea_accel.o|pikafish_stageb_accel.o|pikafish_mac_runtime.o) objects="$objects $out/${{object##*/}}";;
    *) objects="$objects $object";;
  esac
done
"$cross" $objects "$out/latency.o" "$out/profile_clock.o" \\
  $flags -Wl,--wrap=clock_gettime,--wrap=clock_getres -o "$out/nnue-profile"
/opt/toolchain/bin/riscv32-linux-musl-strip "$out/nnue-profile"
sha256sum "$out/nnue-profile"
NNUE_CLOCKSOURCE=linux NNUE_PROFILE=1 NNUE_MODEL="$root/linux/boot/pikafish.pff" \\
 NNUE_VECTORS="$root/build/nnue10ms/nnue10ms.vectors" NNUE_SAMPLES=20 NNUE_REQUIRE_HW=0 \\
 PIKAFISH_STAGEA_ACCEL=0 PIKAFISH_STAGEB_ACCEL=0 qemu-riscv32 "$out/nnue-profile" > "$out/qemu-profile.log" 2>&1
cat "$out/qemu-profile.log"
'''
    (output / "build.sh").write_text(build, encoding="utf-8", newline="\n")
    (output / "stages.json").write_text(json.dumps(STAGES, indent=2) + '\n', encoding="utf-8")
    print('PROFILE_STAGE_READY', output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.root.resolve(), args.output.resolve())
