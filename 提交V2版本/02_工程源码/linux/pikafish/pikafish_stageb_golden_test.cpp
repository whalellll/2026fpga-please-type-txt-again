#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

#include "nnue/nnue_architecture.h"

extern "C" {
#include "pf_mlp_mac_pack.h"
#include "pf_mlp_golden_pack.h"
#include "pf_mlp_stage_b.h"
}

namespace {

using Stockfish::Eval::NNUE::L1;
using Stockfish::Eval::NNUE::L2;
using Stockfish::Eval::NNUE::LayerStacks;
using Stockfish::Eval::NNUE::NNZInfo;
using Stockfish::Eval::NNUE::NetworkArchitecture;
using Stockfish::Eval::NNUE::TransformedFeatureType;

constexpr std::size_t Pff1HeaderBytes       = 0x1000;
constexpr std::size_t Pff1FixedHeaderBytes  = 104;
constexpr std::size_t Pff1DescriptorBytes   = 32;
constexpr std::size_t Pff1SectionCount      = 6;
constexpr std::size_t Pff1StackBytes        = 35204;
constexpr std::size_t Pff1Fc0BiasOffset     = 0;
constexpr std::size_t Pff1Fc0WeightOffset   = Pff1Fc0BiasOffset + 32 * 4;
constexpr std::size_t Pff1Fc1BiasOffset     = Pff1Fc0WeightOffset + 32 * 1024;
constexpr std::size_t Pff1Fc1WeightOffset   = Pff1Fc1BiasOffset + 32 * 4;
constexpr std::size_t Pff1Fc2BiasOffset     = Pff1Fc1WeightOffset + 32 * 64;
constexpr std::size_t Pff1Fc2WeightOffset   = Pff1Fc2BiasOffset + 4;
constexpr std::size_t InputCaseCount        = 6;

static_assert(L1 == 1024);
static_assert(L2 == 32);
static_assert(LayerStacks == 16);
static_assert(Pff1Fc2WeightOffset + 128 == Pff1StackBytes);
static_assert(PF_STAGEB_STACK_COUNT == LayerStacks);
static_assert(PF_STAGEB_FC0_TILE_COUNT == 4);
static_assert(PF_STAGEB_PACK_USED_BYTES == 593920);
static_assert(PF_STAGEB_GOLDEN_STACK_COUNT == LayerStacks);
static_assert(PF_STAGEB_GOLDEN_CASE_COUNT == InputCaseCount);
static_assert(PF_STAGEB_GOLDEN_LANE_COUNT == L2);

struct Section {
    std::array<char, 4> name{};
    std::uint64_t       offset = 0;
    std::uint64_t       size   = 0;
    std::uint32_t       crc    = 0;
};

struct Pff1Image {
    std::ifstream file;
    Section       mlps;
};

struct NativeTileContext {
    const std::uint8_t* slot  = nullptr;
    unsigned            calls = 0;
};

[[noreturn]] void fail(const std::string& reason) {
    std::fprintf(stderr, "PIKAFISH_STAGEB_GOLDEN_ACCEPT_FAIL reason=%s\n", reason.c_str());
    std::exit(1);
}

std::uint32_t read_u32(const std::uint8_t* p) {
    return static_cast<std::uint32_t>(p[0]) | (static_cast<std::uint32_t>(p[1]) << 8)
         | (static_cast<std::uint32_t>(p[2]) << 16)
         | (static_cast<std::uint32_t>(p[3]) << 24);
}

std::uint64_t read_u64(const std::uint8_t* p) {
    return static_cast<std::uint64_t>(read_u32(p))
         | (static_cast<std::uint64_t>(read_u32(p + 4)) << 32);
}

std::int32_t read_i8(std::uint8_t value) {
    return value < 0x80u ? static_cast<std::int32_t>(value)
                         : static_cast<std::int32_t>(value) - 256;
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
    if (length <= 0 || static_cast<std::uint64_t>(length)
                         > std::numeric_limits<std::size_t>::max())
        fail(std::string("size-") + path);
    std::vector<std::uint8_t> data(static_cast<std::size_t>(length));
    input.seekg(0);
    input.read(reinterpret_cast<char*>(data.data()), length);
    if (!input)
        fail(std::string("read-") + path);
    return data;
}

Pff1Image open_pff1(const char* path) {
    Pff1Image image;
    image.file.open(path, std::ios::binary);
    if (!image.file)
        fail("pff1-open");

    std::array<std::uint8_t, Pff1HeaderBytes> header{};
    image.file.read(reinterpret_cast<char*>(header.data()), header.size());
    if (!image.file)
        fail("pff1-header-read");
    if (std::memcmp(header.data(), "PFF1", 4) != 0 || read_u32(header.data() + 4) != 0x00010000u
        || read_u32(header.data() + 8) != Pff1HeaderBytes
        || read_u32(header.data() + 52) != Pff1SectionCount
        || read_u32(header.data() + 64) != Pff1StackBytes)
        fail("pff1-header-contract");

    bool found = false;
    for (std::size_t index = 0; index < Pff1SectionCount; ++index)
    {
        const std::uint8_t* descriptor =
          header.data() + Pff1FixedHeaderBytes + index * Pff1DescriptorBytes;
        if (std::memcmp(descriptor, "MLPS", 4) != 0)
            continue;
        std::memcpy(image.mlps.name.data(), descriptor, 4);
        image.mlps.offset = read_u64(descriptor + 8);
        image.mlps.size   = read_u64(descriptor + 16);
        image.mlps.crc    = read_u32(descriptor + 24);
        found             = true;
    }
    if (!found || image.mlps.offset % 4096 != 0
        || image.mlps.size != Pff1StackBytes * LayerStacks)
        fail("pff1-mlps-contract");
    return image;
}

std::vector<std::uint8_t> read_mlps(Pff1Image& image) {
    std::vector<std::uint8_t> data(static_cast<std::size_t>(image.mlps.size));
    image.file.seekg(static_cast<std::streamoff>(image.mlps.offset));
    image.file.read(reinterpret_cast<char*>(data.data()),
                    static_cast<std::streamsize>(data.size()));
    if (!image.file)
        fail("pff1-mlps-read");
    if (crc32(data.data(), data.size()) != image.mlps.crc)
        fail("pff1-mlps-crc");
    return data;
}

std::array<std::uint8_t, 32> parse_hex_sha256(const char* text) {
    if (std::strlen(text) != 64)
        fail("model-sha256-length");
    std::array<std::uint8_t, 32> digest{};
    auto nibble = [](char c) -> int {
        if (c >= '0' && c <= '9')
            return c - '0';
        if (c >= 'a' && c <= 'f')
            return c - 'a' + 10;
        if (c >= 'A' && c <= 'F')
            return c - 'A' + 10;
        return -1;
    };
    for (std::size_t i = 0; i < digest.size(); ++i)
    {
        const int hi = nibble(text[i * 2]);
        const int lo = nibble(text[i * 2 + 1]);
        if (hi < 0 || lo < 0)
            fail("model-sha256-format");
        digest[i] = static_cast<std::uint8_t>((hi << 4) | lo);
    }
    return digest;
}

void validate_pfsb(const std::vector<std::uint8_t>& image,
                   const std::array<std::uint8_t, 32>& modelSha) {
    if (image.size() != PF_STAGEB_PACK_USED_BYTES || read_u32(image.data()) != PF_STAGEB_PACK_MAGIC
        || read_u32(image.data() + 4) != PF_STAGEB_PACK_VERSION
        || read_u32(image.data() + 8) != PF_STAGEB_HEADER_BYTES
        || read_u32(image.data() + 12) != PF_STAGEB_PACK_USED_BYTES
        || read_u32(image.data() + 16) != PF_STAGEB_STACK_COUNT
        || read_u32(image.data() + 20) != PF_STAGEB_STACK_SLOT_BYTES
        || read_u32(image.data() + 24) != PF_STAGEB_STACK_BASE
        || read_u32(image.data() + 28) != PF_STAGEB_FC0_PACKED_OFFSET
        || read_u32(image.data() + 32) != PF_STAGEB_FC0_TILE_BYTES
        || read_u32(image.data() + 36) != PF_STAGEB_FC0_TILE_COUNT
        || read_u32(image.data() + 40)
             != (PF_STAGEB_FLAG_MAC_NATIVE_FC0 | PF_STAGEB_FLAG_ROW_MAJOR_TAIL)
        || crc32(image.data(), PF_STAGEB_H_HEADER_CRC32)
             != read_u32(image.data() + PF_STAGEB_H_HEADER_CRC32))
        fail("pfsb-header-contract");
    if (std::memcmp(image.data() + 48, modelSha.data(), modelSha.size()) != 0)
        fail("pfsb-source-model-sha256");
    if (crc32(image.data() + PF_STAGEB_HEADER_BYTES,
              image.size() - PF_STAGEB_HEADER_BYTES)
        != read_u32(image.data() + 44))
        fail("pfsb-payload-crc");

    for (unsigned stack = 0; stack < PF_STAGEB_STACK_COUNT; ++stack)
    {
        const std::uint8_t* slot = image.data() + pf_stageb_stack_offset(stack);
        if (read_u32(slot) != PF_STAGEB_STACK_MAGIC || read_u32(slot + 4) != stack
            || read_u32(slot + 8) != PF_STAGEB_STACK_SLOT_BYTES
            || read_u32(slot + 12) != PF_STAGEB_FC0_PACKED_OFFSET
            || read_u32(slot + 16) != PF_STAGEB_FC0_PACKED_BYTES
            || read_u32(slot + 20) != PF_STAGEB_FC0_BIAS_OFFSET
            || read_u32(slot + 24) != PF_STAGEB_FC0_BIAS_BYTES
            || read_u32(slot + 28) != PF_STAGEB_FC1_WEIGHT_OFFSET
            || read_u32(slot + 32) != PF_STAGEB_FC1_WEIGHT_BYTES
            || read_u32(slot + 36) != PF_STAGEB_FC1_BIAS_OFFSET
            || read_u32(slot + 40) != PF_STAGEB_FC1_BIAS_BYTES
            || read_u32(slot + 44) != PF_STAGEB_FC2_WEIGHT_OFFSET
            || read_u32(slot + 48) != PF_STAGEB_FC2_WEIGHT_BYTES
            || read_u32(slot + 52) != PF_STAGEB_FC2_BIAS_OFFSET
            || read_u32(slot + 56) != PF_STAGEB_FC2_BIAS_BYTES)
            fail("pfsb-stack-contract-" + std::to_string(stack));
        if (crc32(slot + PF_STAGEB_STACK_HEADER_BYTES,
                  PF_STAGEB_STACK_DATA_END - PF_STAGEB_STACK_HEADER_BYTES)
              != read_u32(slot + PF_STAGEB_S_DATA_CRC32)
            || crc32(slot + PF_STAGEB_FC0_PACKED_OFFSET,
                     PF_STAGEB_FC0_PACKED_BYTES + PF_STAGEB_FC0_BIAS_BYTES)
                 != read_u32(slot + PF_STAGEB_S_FC0_CRC32))
            fail("pfsb-stack-crc-" + std::to_string(stack));
    }
}

std::size_t native_weight_offset(unsigned output, unsigned feature) {
    const unsigned tile     = feature / 256;
    const unsigned within   = feature % 256;
    const unsigned ciTile   = within / 4;
    const unsigned ci       = within % 4;
    const unsigned pair     = output / 2;
    const unsigned parity   = output % 2;
    return PF_STAGEB_FC0_PACKED_OFFSET + tile * PF_STAGEB_FC0_TILE_BYTES
         + ciTile * 128 + (pair * 4 + ci) * 2 + parity;
}

void compare_pack_to_pff1(unsigned stack,
                          const std::uint8_t* official,
                          const std::uint8_t* slot) {
    for (unsigned output = 0; output < L2; ++output)
        for (unsigned feature = 0; feature < L1; ++feature)
        {
            const std::uint8_t expected =
              official[Pff1Fc0WeightOffset + output * L1 + feature];
            const std::uint8_t actual = slot[native_weight_offset(output, feature)];
            if (actual != expected)
                fail("fc0-weight-layout-stack-" + std::to_string(stack) + "-out-"
                     + std::to_string(output) + "-feature-" + std::to_string(feature));
        }

    const struct {
        std::size_t pff1Offset;
        std::size_t pfsbOffset;
        std::size_t bytes;
        const char* name;
    } regions[] = {
      {Pff1Fc0BiasOffset, PF_STAGEB_FC0_BIAS_OFFSET, PF_STAGEB_FC0_BIAS_BYTES, "fc0-bias"},
      {Pff1Fc1WeightOffset, PF_STAGEB_FC1_WEIGHT_OFFSET, PF_STAGEB_FC1_WEIGHT_BYTES,
       "fc1-weight"},
      {Pff1Fc1BiasOffset, PF_STAGEB_FC1_BIAS_OFFSET, PF_STAGEB_FC1_BIAS_BYTES, "fc1-bias"},
      {Pff1Fc2WeightOffset, PF_STAGEB_FC2_WEIGHT_OFFSET, PF_STAGEB_FC2_WEIGHT_BYTES,
       "fc2-weight"},
      {Pff1Fc2BiasOffset, PF_STAGEB_FC2_BIAS_OFFSET, PF_STAGEB_FC2_BIAS_BYTES, "fc2-bias"},
    };
    for (const auto& region : regions)
        if (std::memcmp(official + region.pff1Offset, slot + region.pfsbOffset,
                        region.bytes)
            != 0)
            fail(std::string(region.name) + "-stack-" + std::to_string(stack));
}

void fill_input(std::array<std::uint8_t, L1>& input, unsigned pattern, unsigned stack) {
    std::uint32_t state = 0x9e3779b9u ^ (stack * 0x45d9f3bu) ^ pattern;
    for (unsigned i = 0; i < input.size(); ++i)
    {
        switch (pattern)
        {
        case 0:
            input[i] = 0;
            break;
        case 1:
            input[i] = 127;
            break;
        case 2:
            input[i] = static_cast<std::uint8_t>(i & 127u);
            break;
        case 3:
            input[i] = static_cast<std::uint8_t>((i * 37u + stack * 11u) & 127u);
            break;
        case 4:
            input[i] = i % 17u == 0 ? 127 : 0;
            break;
        default:
            state ^= state << 13;
            state ^= state >> 17;
            state ^= state << 5;
            input[i] = static_cast<std::uint8_t>(state & 127u);
            break;
        }
    }
}

int native_tile(void* context,
                const pf_mlp_model_t*,
                const std::uint8_t* input,
                const pf_mlp_fc0_tile_job_t* job,
                std::int32_t* partial) {
    auto* native = static_cast<NativeTileContext*>(context);
    if (!native || !native->slot || !input || !job || !partial || job->tile_id >= 4
        || job->cin != 256 || job->cout != 32)
        return 0;
    const unsigned featureBase = job->tile_id * 256;
    for (unsigned output = 0; output < 32; ++output)
    {
        std::int32_t sum = 0;
        for (unsigned feature = featureBase; feature < featureBase + 256; ++feature)
            sum += static_cast<std::int32_t>(input[feature])
                 * read_i8(native->slot[native_weight_offset(output, feature)]);
        partial[output] = sum;
    }
    ++native->calls;
    return 1;
}

void compare_lane(unsigned stack,
                  unsigned pattern,
                  unsigned lane,
                  const char* path,
                  std::int32_t expected,
                  std::int32_t actual) {
    if (expected == actual)
        return;
    std::ostringstream reason;
    reason << path << "-stack-" << stack << "-pattern-" << pattern << "-lane-" << lane
           << "-expected-" << expected << "-actual-" << actual;
    fail(reason.str());
}

void append_u32(std::vector<std::uint8_t>& output, std::uint32_t value) {
    output.push_back(static_cast<std::uint8_t>(value));
    output.push_back(static_cast<std::uint8_t>(value >> 8));
    output.push_back(static_cast<std::uint8_t>(value >> 16));
    output.push_back(static_cast<std::uint8_t>(value >> 24));
}

void run_stack(unsigned stack,
               const std::uint8_t* official,
               const std::uint8_t* slot,
               std::vector<std::uint8_t>& goldenPayload) {
    std::string parameterBytes(reinterpret_cast<const char*>(official), Pff1StackBytes);
    std::istringstream parameterStream(parameterBytes, std::ios::in | std::ios::binary);
    NetworkArchitecture architecture;
    if (!architecture.read_parameters(parameterStream)
        || parameterStream.tellg() != static_cast<std::streamoff>(Pff1StackBytes))
        fail("official-parameter-load-stack-" + std::to_string(stack));

    std::array<std::int8_t, PF_MLP_FC0_OUT * PF_MLP_L1> rowMajorFc0{};
    std::memcpy(rowMajorFc0.data(), official + Pff1Fc0WeightOffset, rowMajorFc0.size());
    pf_mlp_pack_header_t modelHeader{};
    modelHeader.magic             = PF_MLP_PACK_MAGIC;
    modelHeader.version           = PF_MLP_PACK_VERSION;
    modelHeader.l1                = PF_MLP_L1;
    modelHeader.l2                = PF_MLP_L2;
    modelHeader.l3                = PF_MLP_L3;
    modelHeader.weight_scale_bits = PF_MLP_WEIGHT_SCALE_BITS;
    modelHeader.flags             = 1;

    pf_mlp_model_t model{};
    if (!pf_mlp_model_bind(
          &model, &modelHeader, rowMajorFc0.data(),
          reinterpret_cast<const std::int32_t*>(slot + PF_STAGEB_FC0_BIAS_OFFSET),
          reinterpret_cast<const std::int8_t*>(slot + PF_STAGEB_FC1_WEIGHT_OFFSET),
          reinterpret_cast<const std::int32_t*>(slot + PF_STAGEB_FC1_BIAS_OFFSET),
          reinterpret_cast<const std::int8_t*>(slot + PF_STAGEB_FC2_WEIGHT_OFFSET),
          reinterpret_cast<const std::int32_t*>(slot + PF_STAGEB_FC2_BIAS_OFFSET)))
        fail("reference-model-bind-stack-" + std::to_string(stack));

    for (unsigned pattern = 0; pattern < InputCaseCount; ++pattern)
    {
        std::array<std::uint8_t, L1> input{};
        fill_input(input, pattern, stack);
        NNZInfo<L1> nnz{};
        typename decltype(architecture.fc_0)::OutputBuffer officialFc0{};
        architecture.fc_0.propagate(input.data(), officialFc0, nnz);

        std::array<std::int32_t, PF_MLP_FC0_OUT> referenceFc0{};
        if (!pf_mlp_ref_fc0(&model, input.data(), referenceFc0.data()))
            fail("reference-fc0-stack-" + std::to_string(stack));

        std::array<std::int32_t, PF_MLP_FC0_OUT> nativeFc0{};
        NativeTileContext native{slot, 0};
        if (!pf_mlp_tiled_fc0(&model, input.data(), native_tile, &native, nativeFc0.data())
            || native.calls != PF_MLP_FC0_CIN_TILES)
            fail("native-fc0-stack-" + std::to_string(stack));

        for (unsigned lane = 0; lane < L2; ++lane)
        {
            compare_lane(stack, pattern, lane, "reference-fc0", officialFc0[lane],
                         referenceFc0[lane]);
            compare_lane(stack, pattern, lane, "native-fc0", officialFc0[lane],
                         nativeFc0[lane]);
        }

        const std::int32_t officialScore = architecture.propagate(input.data(), nnz);
        std::int32_t       referenceScore = 0;
        std::int32_t       nativeScore    = 0;
        if (!pf_mlp_propagate(&model, input.data(), nullptr, nullptr, &referenceScore))
            fail("reference-propagate-stack-" + std::to_string(stack));
        native.calls = 0;
        if (!pf_mlp_propagate(&model, input.data(), native_tile, &native, &nativeScore)
            || native.calls != PF_MLP_FC0_CIN_TILES)
            fail("native-propagate-stack-" + std::to_string(stack));
        compare_lane(stack, pattern, 0, "reference-score", officialScore, referenceScore);
        compare_lane(stack, pattern, 0, "native-score", officialScore, nativeScore);
        for (const std::int32_t value : officialFc0)
            append_u32(goldenPayload, static_cast<std::uint32_t>(value));
        append_u32(goldenPayload, static_cast<std::uint32_t>(officialScore));
    }

    std::printf("PIKAFISH_STAGEB_GOLDEN_BUCKET_PASS bucket=%u cases=%zu\n", stack,
                InputCaseCount);
}

void write_golden_vectors(const char* path,
                          const std::vector<std::uint8_t>& payload,
                          const std::array<std::uint8_t, 32>& modelSha,
                          std::uint32_t mlpsCrc,
                          std::uint32_t pfsbCrc) {
    if (payload.size() != PF_STAGEB_GOLDEN_PAYLOAD_BYTES)
        fail("golden-payload-size");
    std::vector<std::uint8_t> image(PF_STAGEB_GOLDEN_HEADER_BYTES, 0);
    auto put_u32 = [&image](std::size_t offset, std::uint32_t value) {
        image[offset]     = static_cast<std::uint8_t>(value);
        image[offset + 1] = static_cast<std::uint8_t>(value >> 8);
        image[offset + 2] = static_cast<std::uint8_t>(value >> 16);
        image[offset + 3] = static_cast<std::uint8_t>(value >> 24);
    };
    put_u32(0, PF_STAGEB_GOLDEN_MAGIC);
    put_u32(4, PF_STAGEB_GOLDEN_VERSION);
    put_u32(8, PF_STAGEB_GOLDEN_HEADER_BYTES);
    put_u32(12, PF_STAGEB_GOLDEN_TOTAL_BYTES);
    put_u32(16, PF_STAGEB_GOLDEN_STACK_COUNT);
    put_u32(20, PF_STAGEB_GOLDEN_CASE_COUNT);
    put_u32(24, PF_STAGEB_GOLDEN_LANE_COUNT);
    put_u32(28, PF_STAGEB_GOLDEN_RECORD_BYTES);
    put_u32(32, pfsbCrc);
    put_u32(36, mlpsCrc);
    put_u32(40, crc32(payload.data(), payload.size()));
    put_u32(44, PF_STAGEB_GOLDEN_FLAG_FC0 | PF_STAGEB_GOLDEN_FLAG_SCORE);
    std::memcpy(image.data() + 48, modelSha.data(), modelSha.size());
    image.insert(image.end(), payload.begin(), payload.end());

    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output)
        fail("golden-output-open");
    output.write(reinterpret_cast<const char*>(image.data()),
                 static_cast<std::streamsize>(image.size()));
    if (!output)
        fail("golden-output-write");
    std::printf("PIKAFISH_STAGEB_GOLDEN_VECTOR_PASS bytes=%zu payload_crc32=%08x path=%s\n",
                image.size(), crc32(payload.data(), payload.size()), path);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 4 && argc != 5)
    {
        std::fprintf(stderr,
                     "usage: %s PFF1 PFSB SOURCE_NNUE_SHA256 [GOLDEN_OUTPUT]\n",
                     argv[0]);
        return 2;
    }

    Pff1Image pff1 = open_pff1(argv[1]);
    auto       mlps = read_mlps(pff1);
    auto       pfsb = read_file(argv[2]);
    const auto modelSha = parse_hex_sha256(argv[3]);
    validate_pfsb(pfsb, modelSha);
    std::vector<std::uint8_t> goldenPayload;
    goldenPayload.reserve(PF_STAGEB_GOLDEN_PAYLOAD_BYTES);

    for (unsigned stack = 0; stack < LayerStacks; ++stack)
    {
        const std::uint8_t* official = mlps.data() + stack * Pff1StackBytes;
        const std::uint8_t* slot     = pfsb.data() + pf_stageb_stack_offset(stack);
        compare_pack_to_pff1(stack, official, slot);
        run_stack(stack, official, slot, goldenPayload);
    }

    if (argc == 5)
        write_golden_vectors(argv[4], goldenPayload, modelSha, pff1.mlps.crc,
                             read_u32(pfsb.data() + 44));

    std::printf("PIKAFISH_STAGEB_GOLDEN_ACCEPT_PASS buckets=%u cases=%zu fc0_lanes=%zu "
                "mlps_crc32=%08x pfsb_crc32=%08x\n",
                static_cast<unsigned>(LayerStacks), LayerStacks * InputCaseCount,
                LayerStacks * InputCaseCount * L2, pff1.mlps.crc, read_u32(pfsb.data() + 44));
    return 0;
}
