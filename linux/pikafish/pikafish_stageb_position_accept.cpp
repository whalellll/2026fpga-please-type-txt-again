#if defined(PIKAFISH_STAGEB_POSITION_ACCEPTANCE)

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include "attacks.h"
#include "evaluate.h"
#include "nnue/network.h"
#include "nnue/nnue_accumulator.h"
#include "nnue/nnue_misc.h"
#include "pikafish_attack_tables.h"
#include "position.h"

extern "C" {
#include "mac_accel_kernel.h"
#include "pf_mlp_mac_pack.h"
#include "pf_mlp_stage_b.h"
#include "pf_stageb_position_golden.h"
}

extern "C" int pikafish_stageb_position_acceptance_main(int argc, char** argv);

namespace {

using Stockfish::BLACK;
using Stockfish::Color;
using Stockfish::Eval::NNUE::AccumulatorCaches;
using Stockfish::Eval::NNUE::AccumulatorStack;
using Stockfish::Eval::NNUE::EvalFile;
using Stockfish::Eval::NNUE::L1;
using Stockfish::Eval::NNUE::L2;
using Stockfish::Eval::NNUE::Network;
using Stockfish::Eval::NNUE::StageBPositionTrace;
using Stockfish::Position;
using Stockfish::StateInfo;
using Stockfish::Value;
using Stockfish::WHITE;
using Stockfish::i64;

constexpr std::uint32_t MacRegisterPhysical = 0x1fe10000u;
constexpr std::uint32_t Pff1Physical        = 0x10000000u;
constexpr std::size_t   Pff1HeaderBytes     = 4096u;
constexpr std::size_t   Pff1MlpsDescriptor  = 104u + 5u * 32u;
constexpr std::uint32_t MacPollLimit        = 5000000u;
constexpr std::uint8_t  ScratchCanary       = 0xa5u;
constexpr std::uint8_t  OutputPoison        = 0x5au;

static_assert(L1 == PF_STAGEB_POSITION_FEATURE_COUNT);
static_assert(L2 == PF_STAGEB_POSITION_FC0_LANES);
static_assert(PF_STAGEB_POSITION_RECORD_BYTES == 1188u);
static_assert(PF_STAGEB_POSITION_TOTAL_BYTES == 38176u);

struct ModelBinding {
    std::array<std::uint8_t, 32> sourceSha{};
    std::array<std::uint8_t, 32> decodedSha{};
    std::uint32_t                mlpsCrc = 0;
    std::uint32_t                pfsbCrc = 0;
};

struct Counts {
    unsigned usRooks;
    unsigned themRooks;
    unsigned usKnightCannon;
    unsigned themKnightCannon;
};

struct HardwareContext {
    int                    memFd       = -1;
    void*                  registerMap = MAP_FAILED;
    void*                  ddrMap      = MAP_FAILED;
    volatile std::uint32_t* registers  = nullptr;
    std::uint8_t*          ddr        = nullptr;
    std::uint32_t          bucket     = 0;
    std::uint32_t          jobs       = 0;
    std::uint32_t          failedJobs = 0;
    std::uint64_t          cycles     = 0;
};

[[noreturn]] void fail(const std::string& reason) {
    std::fprintf(stderr, "PIKAFISH_STAGEB_PHASE2_FAIL reason=%s\n", reason.c_str());
    std::exit(1);
}

std::uint32_t read_u32(const std::uint8_t* p) {
    return std::uint32_t(p[0]) | (std::uint32_t(p[1]) << 8) | (std::uint32_t(p[2]) << 16)
         | (std::uint32_t(p[3]) << 24);
}

std::uint64_t read_u64(const std::uint8_t* p) {
    return std::uint64_t(read_u32(p)) | (std::uint64_t(read_u32(p + 4)) << 32);
}

std::int32_t read_i32(const std::uint8_t* p) {
    return static_cast<std::int32_t>(read_u32(p));
}

void write_u32(std::uint8_t* p, std::uint32_t value) {
    p[0] = static_cast<std::uint8_t>(value);
    p[1] = static_cast<std::uint8_t>(value >> 8);
    p[2] = static_cast<std::uint8_t>(value >> 16);
    p[3] = static_cast<std::uint8_t>(value >> 24);
}

std::uint32_t crc32(const std::uint8_t* data, std::size_t bytes) {
    std::uint32_t crc = 0xffffffffu;
    for (std::size_t i = 0; i < bytes; ++i)
    {
        crc ^= data[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return crc ^ 0xffffffffu;
}

std::vector<std::uint8_t> read_file(const char* path) {
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    if (!input)
        fail(std::string("open-") + path);
    const std::streamoff length = input.tellg();
    if (length <= 0)
        fail(std::string("size-") + path);
    std::vector<std::uint8_t> data(static_cast<std::size_t>(length));
    input.seekg(0);
    input.read(reinterpret_cast<char*>(data.data()), length);
    if (!input)
        fail(std::string("read-") + path);
    return data;
}

void validate_pff1_header(const std::uint8_t* header, ModelBinding& binding) {
    if (std::memcmp(header, "PFF1", 4) != 0 || read_u32(header + 4) != 0x00010000u
        || read_u32(header + 8) != Pff1HeaderBytes || read_u32(header + 52) != 6u
        || read_u32(header + 64) != 35204u
        || std::memcmp(header + Pff1MlpsDescriptor, "MLPS", 4) != 0
        || read_u64(header + Pff1MlpsDescriptor + 16) != 16u * 35204u)
        fail("pff1-header-contract");
    std::memcpy(binding.decodedSha.data(), header + 72, binding.decodedSha.size());
    binding.mlpsCrc = read_u32(header + Pff1MlpsDescriptor + 24);
}

void read_pff1_binding(const char* path, bool physical, ModelBinding& binding) {
    if (!physical)
    {
        auto file = read_file(path);
        if (file.size() < Pff1HeaderBytes || read_u64(file.data() + 56) != file.size())
            fail("pff1-file-size");
        validate_pff1_header(file.data(), binding);
        return;
    }

    const int fd = open("/dev/mem", O_RDONLY | O_SYNC | O_CLOEXEC);
    if (fd < 0)
        fail("pff1-open-devmem");
    void* mapping = mmap(nullptr, Pff1HeaderBytes, PROT_READ, MAP_SHARED, fd,
                         static_cast<off_t>(Pff1Physical));
    if (mapping == MAP_FAILED)
    {
        close(fd);
        fail("pff1-map-header");
    }
    validate_pff1_header(static_cast<const std::uint8_t*>(mapping), binding);
    munmap(mapping, Pff1HeaderBytes);
    close(fd);
}

void validate_pfsb(const std::vector<std::uint8_t>& image, ModelBinding& binding) {
    const auto require = [](bool condition, const char* field) {
        if (!condition)
            fail(std::string("pfsb-contract-") + field);
    };
    require(image.size() == PF_STAGEB_PACK_USED_BYTES, "size");
    require(read_u32(image.data()) == PF_STAGEB_PACK_MAGIC, "magic");
    require(read_u32(image.data() + 4) == PF_STAGEB_PACK_VERSION, "version");
    require(read_u32(image.data() + 8) == PF_STAGEB_HEADER_BYTES, "header-size");
    require(read_u32(image.data() + 12) == PF_STAGEB_PACK_USED_BYTES, "used-size");
    require(read_u32(image.data() + 16) == PF_STAGEB_STACK_COUNT, "stack-count");
    require(read_u32(image.data() + 20) == PF_STAGEB_STACK_SLOT_BYTES, "slot-size");
    require(read_u32(image.data() + 24) == PF_STAGEB_STACK_BASE, "stack-base");
    require(read_u32(image.data() + 28) == PF_STAGEB_FC0_PACKED_OFFSET, "fc0-offset");
    require(read_u32(image.data() + 32) == PF_STAGEB_FC0_TILE_BYTES, "tile-size");
    require(read_u32(image.data() + 36) == PF_STAGEB_FC0_TILE_COUNT, "tile-count");
    require(read_u32(image.data() + PF_STAGEB_H_MLPS_BYTES) == 16u * 35204u,
            "mlps-size");
    require(read_u32(image.data() + PF_STAGEB_H_MLPS_CRC32) == binding.mlpsCrc,
            "mlps-crc");
    require(std::memcmp(image.data() + PF_STAGEB_H_DECODED_SHA256,
                        binding.decodedSha.data(), binding.decodedSha.size()) == 0,
            "decoded-sha");
    require(crc32(image.data(), PF_STAGEB_H_HEADER_CRC32)
                == read_u32(image.data() + PF_STAGEB_H_HEADER_CRC32),
            "header-crc");
    require(crc32(image.data() + PF_STAGEB_HEADER_BYTES,
                  image.size() - PF_STAGEB_HEADER_BYTES)
                == read_u32(image.data() + PF_STAGEB_H_PAYLOAD_CRC32),
            "payload-crc");
    binding.pfsbCrc = read_u32(image.data() + 44);
    std::memcpy(binding.sourceSha.data(), image.data() + 48, binding.sourceSha.size());
    for (unsigned bucket = 0; bucket < PF_STAGEB_STACK_COUNT; ++bucket)
    {
        const std::uint8_t* slot = image.data() + pf_stageb_stack_offset(bucket);
        if (read_u32(slot) != PF_STAGEB_STACK_MAGIC || read_u32(slot + 4) != bucket
            || read_u32(slot + 8) != PF_STAGEB_STACK_SLOT_BYTES
            || crc32(slot + PF_STAGEB_STACK_HEADER_BYTES,
                     PF_STAGEB_STACK_DATA_END - PF_STAGEB_STACK_HEADER_BYTES)
                 != read_u32(slot + PF_STAGEB_S_DATA_CRC32)
            || crc32(slot + PF_STAGEB_FC0_PACKED_OFFSET,
                     PF_STAGEB_FC0_PACKED_BYTES + PF_STAGEB_FC0_BIAS_BYTES)
                 != read_u32(slot + PF_STAGEB_S_FC0_CRC32))
            fail("pfsb-stack-contract-" + std::to_string(bucket));
    }
}

Counts counts_for_bucket(unsigned bucket) {
    if (bucket < 12)
    {
        const unsigned rooks = bucket / 4;
        switch (bucket % 4)
        {
        case 0:
            return {rooks, rooks, 1, 0};
        case 1:
            return {rooks, rooks, 1, 1};
        case 2:
            return {rooks, rooks, 3, 1};
        default:
            return {rooks, rooks, 2, 2};
        }
    }
    if (bucket == 12)
        return {2, 1, 1, 1};
    if (bucket == 13)
        return {1, 2, 1, 1};
    if (bucket == 14)
        return {1, 0, 2, 1};
    return {0, 1, 1, 2};
}

void add_rooks(std::array<std::array<char, 9>, 10>& board, Color color, unsigned count) {
    const unsigned rank = color == WHITE ? 1u : 8u;
    const char     piece = color == WHITE ? 'R' : 'r';
    if (count > 0)
        board[rank][0] = piece;
    if (count > 1)
        board[rank][8] = piece;
}

void add_knights_cannons(std::array<std::array<char, 9>, 10>& board,
                         Color color,
                         unsigned count) {
    const unsigned knightRank = color == WHITE ? 1u : 8u;
    const unsigned cannonRank = color == WHITE ? 3u : 6u;
    const char     knight     = color == WHITE ? 'N' : 'n';
    const char     cannon     = color == WHITE ? 'C' : 'c';
    if (count > 0)
        board[knightRank][1] = knight;
    if (count > 1)
        board[knightRank][7] = knight;
    if (count > 2)
        board[cannonRank][1] = cannon;
    if (count > 3)
        board[cannonRank][7] = cannon;
}

std::string make_fen(unsigned bucket, Color side) {
    auto counts = counts_for_bucket(bucket);
    const unsigned whiteRooks = side == WHITE ? counts.usRooks : counts.themRooks;
    const unsigned blackRooks = side == BLACK ? counts.usRooks : counts.themRooks;
    const unsigned whiteNc = side == WHITE ? counts.usKnightCannon : counts.themKnightCannon;
    const unsigned blackNc = side == BLACK ? counts.usKnightCannon : counts.themKnightCannon;
    std::array<std::array<char, 9>, 10> board{};
    for (auto& rank : board)
        rank.fill(' ');
    board[9][4] = 'k';
    board[0][4] = 'K';
    board[4][4] = 'P';  // Prevent flying kings without changing a Stage B bucket.
    add_rooks(board, WHITE, whiteRooks);
    add_rooks(board, BLACK, blackRooks);
    add_knights_cannons(board, WHITE, whiteNc);
    add_knights_cannons(board, BLACK, blackNc);

    std::string fen;
    for (int rank = 9; rank >= 0; --rank)
    {
        unsigned empty = 0;
        for (unsigned file = 0; file < 9; ++file)
        {
            const char piece = board[rank][file];
            if (piece == ' ')
                ++empty;
            else
            {
                if (empty)
                {
                    fen += static_cast<char>('0' + empty);
                    empty = 0;
                }
                fen += piece;
            }
        }
        if (empty)
            fen += static_cast<char>('0' + empty);
        if (rank != 0)
            fen += '/';
    }
    fen += side == WHITE ? " w - - 0 1" : " b - - 0 1";
    return fen;
}

std::vector<std::string> make_corpus() {
    std::vector<std::string> corpus;
    corpus.reserve(PF_STAGEB_POSITION_CASE_COUNT);
    for (unsigned bucket = 0; bucket < PF_STAGEB_POSITION_BUCKET_COUNT; ++bucket)
    {
        corpus.push_back(make_fen(bucket, WHITE));
        corpus.push_back(make_fen(bucket, BLACK));
    }
    return corpus;
}

std::uint32_t corpus_crc(const std::vector<std::string>& corpus) {
    std::vector<std::uint8_t> bytes;
    for (const auto& fen : corpus)
    {
        bytes.insert(bytes.end(), fen.begin(), fen.end());
        bytes.push_back('\n');
    }
    return crc32(bytes.data(), bytes.size());
}

Value scaled_eval(const Position& pos, Value psqt, Value positional) {
    Value nnue = psqt + positional;
    const int complexity = std::abs(int(psqt) - int(positional));
    nnue -= nnue * i64(complexity) / 11743;
    const int material = pos.major_material();
    int       value    = nnue + (nnue * i64(material)) / 36139;
    value -= (value * pos.rule60_count()) / 253;
    value = std::clamp(value, int(Stockfish::VALUE_MATED_IN_MAX_PLY) + 1,
                       int(Stockfish::VALUE_MATE_IN_MAX_PLY) - 1);
    return static_cast<Value>(value);
}

void validate_golden_header(const std::vector<std::uint8_t>& golden,
                            const ModelBinding& binding,
                            std::uint32_t expectedCorpusCrc) {
    if (golden.size() != PF_STAGEB_POSITION_TOTAL_BYTES
        || read_u32(golden.data() + PF_STAGEB_POSITION_H_MAGIC) != PF_STAGEB_POSITION_MAGIC
        || read_u32(golden.data() + PF_STAGEB_POSITION_H_VERSION)
             != PF_STAGEB_POSITION_VERSION
        || read_u32(golden.data() + PF_STAGEB_POSITION_H_HEADER_BYTES)
             != PF_STAGEB_POSITION_HEADER_BYTES
        || read_u32(golden.data() + PF_STAGEB_POSITION_H_TOTAL_BYTES)
             != PF_STAGEB_POSITION_TOTAL_BYTES
        || read_u32(golden.data() + PF_STAGEB_POSITION_H_CASE_COUNT)
             != PF_STAGEB_POSITION_CASE_COUNT
        || read_u32(golden.data() + PF_STAGEB_POSITION_H_BUCKET_COUNT)
             != PF_STAGEB_POSITION_BUCKET_COUNT
        || read_u32(golden.data() + PF_STAGEB_POSITION_H_FEATURE_COUNT)
             != PF_STAGEB_POSITION_FEATURE_COUNT
        || read_u32(golden.data() + PF_STAGEB_POSITION_H_FC0_LANES)
             != PF_STAGEB_POSITION_FC0_LANES
        || read_u32(golden.data() + PF_STAGEB_POSITION_H_RECORD_BYTES)
             != PF_STAGEB_POSITION_RECORD_BYTES
        || read_u32(golden.data() + PF_STAGEB_POSITION_H_FLAGS) != PF_STAGEB_POSITION_FLAGS
        || read_u32(golden.data() + PF_STAGEB_POSITION_H_CORPUS_CRC32) != expectedCorpusCrc
        || read_u32(golden.data() + PF_STAGEB_POSITION_H_MLPS_CRC32) != binding.mlpsCrc
        || read_u32(golden.data() + PF_STAGEB_POSITION_H_PFSB_CRC32) != binding.pfsbCrc
        || std::memcmp(golden.data() + PF_STAGEB_POSITION_H_SOURCE_SHA256,
                       binding.sourceSha.data(), binding.sourceSha.size()) != 0
        || std::memcmp(golden.data() + PF_STAGEB_POSITION_H_DECODED_SHA256,
                       binding.decodedSha.data(), binding.decodedSha.size()) != 0
        || crc32(golden.data() + PF_STAGEB_POSITION_HEADER_BYTES,
                 PF_STAGEB_POSITION_PAYLOAD_BYTES)
             != read_u32(golden.data() + PF_STAGEB_POSITION_H_PAYLOAD_CRC32))
        fail("golden-contract");
}

void write_record(std::uint8_t* record,
                  unsigned index,
                  const std::string& fen,
                  const StageBPositionTrace& trace,
                  Value finalEval) {
    const unsigned expectedBucket = index / PF_STAGEB_POSITION_CASES_PER_BUCKET;
    const unsigned expectedSide   = index % PF_STAGEB_POSITION_CASES_PER_BUCKET;
    if (trace.bucket != static_cast<int>(expectedBucket))
        fail("corpus-bucket-" + std::to_string(index));
    write_u32(record + PF_STAGEB_POSITION_R_BUCKET, expectedBucket);
    write_u32(record + PF_STAGEB_POSITION_R_SIDE_TO_MOVE, expectedSide);
    write_u32(record + PF_STAGEB_POSITION_R_FEN_CRC32,
              crc32(reinterpret_cast<const std::uint8_t*>(fen.data()), fen.size()));
    write_u32(record + PF_STAGEB_POSITION_R_PSQT_RAW,
              static_cast<std::uint32_t>(trace.psqtRaw));
    write_u32(record + PF_STAGEB_POSITION_R_POSITIONAL_RAW,
              static_cast<std::uint32_t>(trace.positionalRaw));
    write_u32(record + PF_STAGEB_POSITION_R_PSQT, static_cast<std::uint32_t>(trace.psqt));
    write_u32(record + PF_STAGEB_POSITION_R_POSITIONAL,
              static_cast<std::uint32_t>(trace.positional));
    write_u32(record + PF_STAGEB_POSITION_R_NNUE,
              static_cast<std::uint32_t>(trace.psqt + trace.positional));
    write_u32(record + PF_STAGEB_POSITION_R_FINAL_EVAL,
              static_cast<std::uint32_t>(finalEval));
    std::memcpy(record + PF_STAGEB_POSITION_FEATURE_OFFSET, trace.transformedFeatures.data(),
                trace.transformedFeatures.size());
    for (unsigned lane = 0; lane < trace.fc0.size(); ++lane)
        write_u32(record + PF_STAGEB_POSITION_FC0_OFFSET + lane * 4u,
                  static_cast<std::uint32_t>(trace.fc0[lane]));
}

void compare_record(const std::uint8_t* record,
                    unsigned index,
                    const std::string& fen,
                    const StageBPositionTrace& trace,
                    Value finalEval) {
    std::array<std::uint8_t, PF_STAGEB_POSITION_RECORD_BYTES> actual{};
    write_record(actual.data(), index, fen, trace, finalEval);
    if (std::memcmp(record, actual.data(), actual.size()) == 0)
        return;
    for (std::size_t offset = 0; offset < actual.size(); ++offset)
        if (record[offset] != actual[offset])
            fail("golden-mismatch-case-" + std::to_string(index) + "-offset-"
                 + std::to_string(offset));
    fail("golden-mismatch");
}

int hardware_tile(void* opaque,
                  const pf_mlp_model_t*,
                  const std::uint8_t* input,
                  const pf_mlp_fc0_tile_job_t* tile,
                  std::int32_t* partial) {
    auto* context = static_cast<HardwareContext*>(opaque);
    if (!context || !input || !tile || !partial || tile->tile_id >= 4 || tile->cin != 256
        || tile->cout != 32)
        return 0;
    mac_kernel_job_t job{};
    job.pixels         = 1;
    job.cin            = tile->cin;
    job.cout           = tile->cout;
    job.compute_mode   = MAC_KERNEL_MODE_U8_S8;
    job.activation     = MAC_KERNEL_ACT_NONE;
    job.output_format  = MAC_KERNEL_OUT_I32;
    job.zero_bias      = 1;
    job.input_addr     = PF_STAGEB_DDR_BUS_BASE + PF_STAGEB_INPUT_OFFSET;
    job.weight_addr    = PF_STAGEB_DDR_BUS_BASE
                    + pf_stageb_fc0_tile_offset(context->bucket, tile->tile_id);
    job.bias_addr      = job.input_addr;
    job.output_addr    = PF_STAGEB_DDR_BUS_BASE + PF_STAGEB_OUTPUT_OFFSET;
    if (mac_kernel_validate_job(&job) != MAC_KERNEL_OK)
        return 0;
    const auto sizes = mac_kernel_buffer_sizes(&job);
    auto* inputScratch  = context->ddr + PF_STAGEB_INPUT_OFFSET;
    auto* outputScratch = context->ddr + PF_STAGEB_OUTPUT_OFFSET;
    std::memset(inputScratch, 0, sizes.input_bytes);
    std::memset(outputScratch, OutputPoison, sizes.output_bytes);
    for (unsigned feature = 0; feature < tile->cin; ++feature)
    {
        const std::size_t offset = std::size_t(feature / 4u) * 8u
                                 + std::size_t(feature % 4u) * 2u;
        inputScratch[offset] = input[tile->tile_id * 256u + feature];
    }
    __sync_synchronize();
    int result = mac_kernel_submit(reinterpret_cast<std::uintptr_t>(context->registers), &job);
    if (result == MAC_KERNEL_OK)
        result = mac_kernel_wait(reinterpret_cast<std::uintptr_t>(context->registers),
                                 MacPollLimit);
    __sync_synchronize();
    if (result != MAC_KERNEL_OK)
    {
        ++context->failedJobs;
        return 0;
    }
    for (unsigned lane = 0; lane < tile->cout; ++lane)
        partial[lane] = read_i32(outputScratch + lane * 4u);
    ++context->jobs;
    context->cycles +=
      mac_kernel_cycles(reinterpret_cast<std::uintptr_t>(context->registers));
    return 1;
}

std::int32_t score_from_fc0(const std::uint8_t* slot, const std::int32_t* fc0) {
    std::int32_t fc1[PF_MLP_FC1_OUT]{};
    std::int32_t fc2[PF_MLP_FC2_OUT]{};
    std::int32_t fc1Bias[PF_MLP_FC1_OUT]{};
    std::int32_t fc2Bias[PF_MLP_FC2_OUT]{};
    std::uint8_t act0Sqr[PF_MLP_FC0_OUT]{};
    std::uint8_t act0Clip[PF_MLP_FC0_OUT]{};
    std::uint8_t concat0[PF_MLP_FC1_IN]{};
    std::uint8_t act1Sqr[PF_MLP_FC1_OUT]{};
    std::uint8_t act1Clip[PF_MLP_FC1_OUT]{};
    std::uint8_t concat1[PF_MLP_FC2_IN]{};
    for (unsigned i = 0; i < PF_MLP_FC1_OUT; ++i)
        fc1Bias[i] = read_i32(slot + PF_STAGEB_FC1_BIAS_OFFSET + i * 4u);
    fc2Bias[0] = read_i32(slot + PF_STAGEB_FC2_BIAS_OFFSET);
    pf_mlp_sqr_clipped_relu_i32(fc0, act0Sqr, PF_MLP_FC0_OUT, PF_MLP_ACT0_SHIFT);
    pf_mlp_clipped_relu_i32(fc0, act0Clip, PF_MLP_FC0_OUT, PF_MLP_ACT0_SHIFT);
    std::memcpy(concat0, act0Sqr, PF_MLP_FC0_OUT);
    std::memcpy(concat0 + PF_MLP_FC0_OUT, act0Clip, PF_MLP_FC0_OUT);
    pf_mlp_affine_u8_i8(concat0, PF_MLP_FC1_IN,
                        reinterpret_cast<const std::int8_t*>(
                          slot + PF_STAGEB_FC1_WEIGHT_OFFSET),
                        fc1Bias, PF_MLP_FC1_OUT, fc1);
    pf_mlp_sqr_clipped_relu_i32(fc1, act1Sqr, PF_MLP_FC1_OUT, PF_MLP_ACT1_SHIFT);
    pf_mlp_clipped_relu_i32(fc1, act1Clip, PF_MLP_FC1_OUT, PF_MLP_ACT1_SHIFT);
    std::memcpy(concat1, act0Sqr, PF_MLP_FC0_OUT);
    std::memcpy(concat1 + PF_MLP_FC0_OUT, act0Clip, PF_MLP_FC0_OUT);
    std::memcpy(concat1 + PF_MLP_FC0_OUT * 2u, act1Sqr, PF_MLP_FC1_OUT);
    std::memcpy(concat1 + PF_MLP_FC0_OUT * 2u + PF_MLP_FC1_OUT, act1Clip,
                PF_MLP_FC1_OUT);
    pf_mlp_affine_u8_i8(concat1, PF_MLP_FC2_IN,
                        reinterpret_cast<const std::int8_t*>(
                          slot + PF_STAGEB_FC2_WEIGHT_OFFSET),
                        fc2Bias, PF_MLP_FC2_OUT, fc2);
    return pf_mlp_scale_output(fc2[0] + fc0[PF_MLP_FC0_OUT - 2u]
                              - fc0[PF_MLP_FC0_OUT - 1u]);
}

void open_hardware(HardwareContext& context, const std::vector<std::uint8_t>& pfsb) {
    context.memFd = open("/dev/mem", O_RDWR | O_SYNC | O_CLOEXEC);
    if (context.memFd < 0)
        fail("mac-open-devmem");
    context.registerMap = mmap(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_SHARED,
                               context.memFd, static_cast<off_t>(MacRegisterPhysical));
    context.ddrMap = mmap(nullptr, PF_STAGEB_DDR_BYTES, PROT_READ | PROT_WRITE, MAP_SHARED,
                          context.memFd, static_cast<off_t>(PF_STAGEB_DDR_CPU_ALIAS));
    if (context.registerMap == MAP_FAILED || context.ddrMap == MAP_FAILED)
        fail("mac-map-devmem");
    context.registers = static_cast<volatile std::uint32_t*>(context.registerMap);
    context.ddr       = static_cast<std::uint8_t*>(context.ddrMap);
    const auto base = reinterpret_cast<std::uintptr_t>(context.registers);
    if (mac_kernel_read(base, MAC_KERNEL_REG_ID) != MAC_KERNEL_ID
        || mac_kernel_read(base, MAC_KERNEL_REG_VERSION) != MAC_KERNEL_VERSION)
        fail("mac-id-version");
    std::memcpy(context.ddr, pfsb.data(), pfsb.size());
    __sync_synchronize();
    if (std::memcmp(context.ddr, pfsb.data(), pfsb.size()) != 0)
        fail("pfsb-ddr-readback");
    std::memset(context.ddr + PF_STAGEB_INPUT_OFFSET, ScratchCanary, PF_STAGEB_INPUT_BYTES);
    std::memset(context.ddr + PF_STAGEB_OUTPUT_OFFSET, ScratchCanary, PF_STAGEB_OUTPUT_BYTES);
}

void close_hardware(HardwareContext& context) {
    if (context.ddrMap != MAP_FAILED)
        munmap(context.ddrMap, PF_STAGEB_DDR_BYTES);
    if (context.registerMap != MAP_FAILED)
        munmap(context.registerMap, 4096);
    if (context.memFd >= 0)
        close(context.memFd);
}

bool scratch_canaries_ok(const HardwareContext& context) {
    for (std::size_t i = 512; i < PF_STAGEB_INPUT_BYTES; ++i)
        if (context.ddr[PF_STAGEB_INPUT_OFFSET + i] != ScratchCanary)
            return false;
    for (std::size_t i = PF_MLP_FC0_OUT * 4u; i < PF_STAGEB_OUTPUT_BYTES; ++i)
        if (context.ddr[PF_STAGEB_OUTPUT_OFFSET + i] != ScratchCanary)
            return false;
    return true;
}

void verify_hardware_case(HardwareContext& context,
                          const std::vector<std::uint8_t>& pfsb,
                          const StageBPositionTrace& trace,
                          const Position& pos,
                          Value officialFinal) {
    const auto* slot = pfsb.data() + pf_stageb_stack_offset(trace.bucket);
    std::array<std::int32_t, PF_MLP_FC0_OUT> bias{};
    for (unsigned lane = 0; lane < bias.size(); ++lane)
        bias[lane] = read_i32(slot + PF_STAGEB_FC0_BIAS_OFFSET + lane * 4u);
    pf_mlp_pack_header_t header{};
    header.magic             = PF_MLP_PACK_MAGIC;
    header.version           = PF_MLP_PACK_VERSION;
    header.l1                = PF_MLP_L1;
    header.l2                = PF_MLP_L2;
    header.l3                = PF_MLP_L3;
    header.weight_scale_bits = PF_MLP_WEIGHT_SCALE_BITS;
    header.flags             = 1;
    pf_mlp_model_t model{};
    if (!pf_mlp_model_bind(
          &model, &header,
          reinterpret_cast<const std::int8_t*>(slot + PF_STAGEB_FC0_PACKED_OFFSET),
          bias.data(), reinterpret_cast<const std::int8_t*>(slot + PF_STAGEB_FC1_WEIGHT_OFFSET),
          reinterpret_cast<const std::int32_t*>(slot + PF_STAGEB_FC1_BIAS_OFFSET),
          reinterpret_cast<const std::int8_t*>(slot + PF_STAGEB_FC2_WEIGHT_OFFSET),
          reinterpret_cast<const std::int32_t*>(slot + PF_STAGEB_FC2_BIAS_OFFSET)))
        fail("hardware-model-bind");
    context.bucket = static_cast<std::uint32_t>(trace.bucket);
    std::array<std::int32_t, PF_MLP_FC0_OUT> actual{};
    if (!pf_mlp_tiled_fc0(&model, trace.transformedFeatures.data(), hardware_tile, &context,
                          actual.data()))
        fail("hardware-fc0-bucket-" + std::to_string(trace.bucket));
    for (unsigned lane = 0; lane < actual.size(); ++lane)
        if (actual[lane] != trace.fc0[lane])
            fail("hardware-fc0-mismatch-bucket-" + std::to_string(trace.bucket) + "-lane-"
                 + std::to_string(lane));
    const std::int32_t positionalRaw = score_from_fc0(slot, actual.data());
    if (positionalRaw != trace.positionalRaw)
        fail("hardware-positional-mismatch-bucket-" + std::to_string(trace.bucket));
    const Value positional = static_cast<Value>(positionalRaw / Stockfish::Eval::NNUE::OutputScale);
    if (scaled_eval(pos, trace.psqt, positional) != officialFinal)
        fail("hardware-final-eval-mismatch-bucket-" + std::to_string(trace.bucket));
    if (!scratch_canaries_ok(context))
        fail("hardware-scratch-canary");
}

}  // namespace

extern "C" int pikafish_stageb_position_acceptance_main(int argc, char** argv) {
    if (argc != 6
        || (std::strcmp(argv[1], "--generate") != 0 && std::strcmp(argv[1], "--verify") != 0
            && std::strcmp(argv[1], "--board") != 0))
    {
        std::fprintf(stderr,
                     "usage: %s {--generate|--verify|--board} MODEL PFF1_OR_- PFSB GOLDEN\n",
                     argv[0]);
        return 2;
    }
    const bool generate  = std::strcmp(argv[1], "--generate") == 0;
    const bool boardMode = std::strcmp(argv[1], "--board") == 0;
    const char* modelPath  = argv[2];
    const char* pff1Path   = argv[3];
    const char* pfsbPath   = argv[4];
    const char* goldenPath = argv[5];

    ModelBinding binding{};
    read_pff1_binding(pff1Path, boardMode && std::strcmp(pff1Path, "-") == 0, binding);
    auto pfsb = read_file(pfsbPath);
    validate_pfsb(pfsb, binding);
    auto corpus = make_corpus();
    const std::uint32_t corpusCrc = corpus_crc(corpus);

    Stockfish::Attacks::PrecomputedAttackTableMapping attackMapping{};
    if (boardMode)
    {
        const char* error = nullptr;
        if (!Stockfish::Attacks::map_precomputed_attack_tables(attackMapping, error)
            || !Stockfish::Attacks::init_precomputed(
              attackMapping.view.rook, attackMapping.view.rookCount,
              attackMapping.view.cannon, attackMapping.view.cannonCount))
            fail(std::string("attack-table-") + (error ? error : "bind"));
    }
    else
        Stockfish::Attacks::init();
    Position::init();

    auto network = std::make_unique<Network>();
    EvalFile evalFile{};
    network->load({}, std::filesystem::path(modelPath), evalFile);
    if (!evalFile.current.has_value())
        fail("network-load");
    auto accumulators = std::make_unique<AccumulatorStack>();
    auto caches       = std::make_unique<AccumulatorCaches>(*network);

    std::vector<std::uint8_t> golden;
    if (generate)
    {
        golden.assign(PF_STAGEB_POSITION_TOTAL_BYTES, 0);
        write_u32(golden.data() + PF_STAGEB_POSITION_H_MAGIC, PF_STAGEB_POSITION_MAGIC);
        write_u32(golden.data() + PF_STAGEB_POSITION_H_VERSION, PF_STAGEB_POSITION_VERSION);
        write_u32(golden.data() + PF_STAGEB_POSITION_H_HEADER_BYTES,
                  PF_STAGEB_POSITION_HEADER_BYTES);
        write_u32(golden.data() + PF_STAGEB_POSITION_H_TOTAL_BYTES,
                  PF_STAGEB_POSITION_TOTAL_BYTES);
        write_u32(golden.data() + PF_STAGEB_POSITION_H_CASE_COUNT,
                  PF_STAGEB_POSITION_CASE_COUNT);
        write_u32(golden.data() + PF_STAGEB_POSITION_H_BUCKET_COUNT,
                  PF_STAGEB_POSITION_BUCKET_COUNT);
        write_u32(golden.data() + PF_STAGEB_POSITION_H_FEATURE_COUNT,
                  PF_STAGEB_POSITION_FEATURE_COUNT);
        write_u32(golden.data() + PF_STAGEB_POSITION_H_FC0_LANES,
                  PF_STAGEB_POSITION_FC0_LANES);
        write_u32(golden.data() + PF_STAGEB_POSITION_H_RECORD_BYTES,
                  PF_STAGEB_POSITION_RECORD_BYTES);
        write_u32(golden.data() + PF_STAGEB_POSITION_H_CORPUS_CRC32, corpusCrc);
        write_u32(golden.data() + PF_STAGEB_POSITION_H_MLPS_CRC32, binding.mlpsCrc);
        write_u32(golden.data() + PF_STAGEB_POSITION_H_PFSB_CRC32, binding.pfsbCrc);
        write_u32(golden.data() + PF_STAGEB_POSITION_H_FLAGS, PF_STAGEB_POSITION_FLAGS);
        std::memcpy(golden.data() + PF_STAGEB_POSITION_H_SOURCE_SHA256,
                    binding.sourceSha.data(), binding.sourceSha.size());
        std::memcpy(golden.data() + PF_STAGEB_POSITION_H_DECODED_SHA256,
                    binding.decodedSha.data(), binding.decodedSha.size());
    }
    else
    {
        golden = read_file(goldenPath);
        validate_golden_header(golden, binding, corpusCrc);
    }

    HardwareContext hardware{};
    if (boardMode)
        open_hardware(hardware, pfsb);

    for (unsigned index = 0; index < corpus.size(); ++index)
    {
        StateInfo state{};
        Position  position;
        if (auto error = position.set(corpus[index], &state))
            fail("fen-" + std::to_string(index) + "-" + error->what());
        if (position.checkers())
            fail("corpus-position-in-check-" + std::to_string(index));
        accumulators->reset();
        const StageBPositionTrace trace =
          network->stageb_position_trace(position, *accumulators, *caches);
        const Value finalEval = Stockfish::Eval::evaluate(
          *network, position, *accumulators, *caches, Stockfish::VALUE_ZERO);
        if (scaled_eval(position, trace.psqt, trace.positional) != finalEval)
            fail("final-eval-formula-" + std::to_string(index));
        auto* record = golden.data() + pf_stageb_position_record_offset(index);
        if (generate)
            write_record(record, index, corpus[index], trace, finalEval);
        else
            compare_record(record, index, corpus[index], trace, finalEval);
        if (boardMode)
            verify_hardware_case(hardware, pfsb, trace, position, finalEval);
        if (index % PF_STAGEB_POSITION_CASES_PER_BUCKET
            == PF_STAGEB_POSITION_CASES_PER_BUCKET - 1)
            std::printf("PIKAFISH_STAGEB_PHASE2_BUCKET_PASS bucket=%u cases=%u%s\n",
                        index / PF_STAGEB_POSITION_CASES_PER_BUCKET,
                        PF_STAGEB_POSITION_CASES_PER_BUCKET,
                        boardMode ? " hardware=1" : "");
    }

    if (generate)
    {
        write_u32(golden.data() + PF_STAGEB_POSITION_H_PAYLOAD_CRC32,
                  crc32(golden.data() + PF_STAGEB_POSITION_HEADER_BYTES,
                        PF_STAGEB_POSITION_PAYLOAD_BYTES));
        std::ofstream output(goldenPath, std::ios::binary | std::ios::trunc);
        if (!output)
            fail("golden-output-open");
        output.write(reinterpret_cast<const char*>(golden.data()), golden.size());
        if (!output)
            fail("golden-output-write");
        std::printf("PIKAFISH_STAGEB_PHASE2_GOLDEN_PASS buckets=%u cases=%u bytes=%u "
                    "payload_crc32=%08x corpus_crc32=%08x\n",
                    PF_STAGEB_POSITION_BUCKET_COUNT, PF_STAGEB_POSITION_CASE_COUNT,
                    PF_STAGEB_POSITION_TOTAL_BYTES,
                    read_u32(golden.data() + PF_STAGEB_POSITION_H_PAYLOAD_CRC32), corpusCrc);
    }
    else if (boardMode)
    {
        __sync_synchronize();
        if (crc32(hardware.ddr + PF_STAGEB_HEADER_BYTES,
                  PF_STAGEB_PACK_USED_BYTES - PF_STAGEB_HEADER_BYTES)
              != binding.pfsbCrc
            || hardware.failedJobs != 0
            || hardware.jobs
                 != PF_STAGEB_POSITION_CASE_COUNT * PF_STAGEB_FC0_TILE_COUNT)
            fail("hardware-final-contract");
        std::printf("PIKAFISH_STAGEB_PHASE2_BOARD_PASS buckets=%u cases=%u jobs=%u "
                    "fc0_lanes=%u pfsb_crc32=%08x cycles=%llu\n",
                    PF_STAGEB_POSITION_BUCKET_COUNT, PF_STAGEB_POSITION_CASE_COUNT,
                    hardware.jobs,
                    PF_STAGEB_POSITION_CASE_COUNT * PF_STAGEB_POSITION_FC0_LANES,
                    binding.pfsbCrc, static_cast<unsigned long long>(hardware.cycles));
    }
    else
        std::printf("PIKAFISH_STAGEB_PHASE2_HOST_PASS buckets=%u cases=%u "
                    "features=%u fc0_lanes=%u corpus_crc32=%08x\n",
                    PF_STAGEB_POSITION_BUCKET_COUNT, PF_STAGEB_POSITION_CASE_COUNT,
                    PF_STAGEB_POSITION_CASE_COUNT * PF_STAGEB_POSITION_FEATURE_COUNT,
                    PF_STAGEB_POSITION_CASE_COUNT * PF_STAGEB_POSITION_FC0_LANES, corpusCrc);

    if (boardMode)
    {
        close_hardware(hardware);
        Stockfish::Attacks::unmap_precomputed_attack_tables(attackMapping);
    }
    return 0;
}

#endif
