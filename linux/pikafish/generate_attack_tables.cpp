#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

// Include the implementation in this translation unit so the generator uses
// the exact pinned Pikafish table construction code and can serialize its
// internal tables after init().
#include "attacks.cpp"

namespace Stockfish::Attacks {

const std::array<MagicMask, 0x108000>& generated_rook_table() {
    return RookTable;
}

const std::array<MagicMask, 0x108000>& generated_cannon_table() {
    return CannonTable;
}

}  // namespace Stockfish::Attacks

namespace {

using Stockfish::Bitboard;
using Stockfish::CANNON;
using Stockfish::PieceType;
using Stockfish::ROOK;
using Stockfish::RookMagicsInit;
using Stockfish::SQUARE_NB;
using Stockfish::Square;
using Stockfish::u64;
using Stockfish::Attacks::MagicMask;

constexpr std::uint32_t FORMAT_VERSION = 1;
constexpr std::uint32_t HEADER_BYTES = 64;
constexpr std::uint32_t ENTRY_BYTES = 16;
constexpr std::uint32_t LAYOUT_LE_LOW64_HIGH64 = 1;

class Crc32 {
   public:
    void update(const std::uint8_t* data, std::size_t size) {
        while (size-- != 0)
        {
            value_ ^= *data++;
            for (unsigned bit = 0; bit < 8; ++bit)
                value_ = (value_ >> 1) ^
                         (0xedb88320U & (0U - (value_ & 1U)));
        }
    }

    std::uint32_t value() const { return value_ ^ 0xffffffffU; }

   private:
    std::uint32_t value_ = 0xffffffffU;
};

[[noreturn]] void fail(const char* message) {
    std::fprintf(stderr, "PIKAFISH_ATTACK_TABLE_FAIL %s\n", message);
    std::exit(EXIT_FAILURE);
}

void put_u32(std::uint8_t* out, std::uint32_t value) {
    out[0] = static_cast<std::uint8_t>(value);
    out[1] = static_cast<std::uint8_t>(value >> 8);
    out[2] = static_cast<std::uint8_t>(value >> 16);
    out[3] = static_cast<std::uint8_t>(value >> 24);
}

void put_u64(std::uint8_t* out, std::uint64_t value) {
    for (unsigned byte = 0; byte < 8; ++byte)
        out[byte] = static_cast<std::uint8_t>(value >> (byte * 8));
}

void encode_bitboard(std::uint8_t out[ENTRY_BYTES], Bitboard value) {
    put_u64(out, static_cast<u64>(value));
    put_u64(out + 8, static_cast<u64>(value >> 64));
}

template<PieceType Pt>
std::uint64_t validate_attacks() {
    std::uint64_t count = 0;
    for (Square square = Stockfish::SQ_A0; square <= Stockfish::SQ_I9; ++square)
    {
        const auto& magic = Stockfish::Attacks::magic(square, Pt);
        Bitboard occupied = 0;
        do
        {
            const Bitboard expected =
              Stockfish::Attacks::sliding_attack<Pt>(square, occupied);
            if (magic.attack_bb(occupied) != expected)
                fail(Pt == ROOK ? "rook lookup mismatch" :
                                  "cannon lookup mismatch");
            ++count;
            occupied = (occupied - magic.mask) & magic.mask;
        } while (occupied);
    }
    return count;
}

template<std::size_t Count>
std::uint32_t write_table(
  std::FILE* file,
  const std::array<MagicMask, Count>& table,
  Crc32& payloadCrc) {
    Crc32 tableCrc;
    std::uint8_t encoded[ENTRY_BYTES];
    for (const MagicMask value : table)
    {
        encode_bitboard(encoded, value);
        if (std::fwrite(encoded, 1, sizeof(encoded), file) != sizeof(encoded))
            fail("payload write failed");
        tableCrc.update(encoded, sizeof(encoded));
        payloadCrc.update(encoded, sizeof(encoded));
    }
    return tableCrc.value();
}

std::uint32_t magic_seed_crc() {
    Crc32 crc;
    std::uint8_t encoded[ENTRY_BYTES];
    for (const Bitboard value : RookMagicsInit)
    {
        encode_bitboard(encoded, value);
        crc.update(encoded, sizeof(encoded));
    }
    return crc.value();
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2)
    {
        std::fprintf(stderr, "usage: %s OUTPUT\n", argv[0]);
        return EXIT_FAILURE;
    }

    static_assert(sizeof(MagicMask) == ENTRY_BYTES);
    static_assert(SQUARE_NB == 90);

    Stockfish::Attacks::init();
    const auto& rook = Stockfish::Attacks::generated_rook_table();
    const auto& cannon = Stockfish::Attacks::generated_cannon_table();
    const std::uint64_t rookSubsets = validate_attacks<ROOK>();
    const std::uint64_t cannonSubsets = validate_attacks<CANNON>();
    if (rookSubsets != rook.size() || cannonSubsets != cannon.size())
        fail("unexpected occupancy subset count");

    std::FILE* file = std::fopen(argv[1], "wb+");
    if (!file)
        fail("cannot open output");

    std::uint8_t header[HEADER_BYTES] = {};
    if (std::fwrite(header, 1, sizeof(header), file) != sizeof(header))
        fail("header reservation failed");

    Crc32 payloadCrc;
    const std::uint32_t rookCrc = write_table(file, rook, payloadCrc);
    const std::uint32_t cannonCrc = write_table(file, cannon, payloadCrc);
    const std::uint32_t rookOffset = HEADER_BYTES;
    const std::uint32_t cannonOffset =
      rookOffset + static_cast<std::uint32_t>(rook.size() * ENTRY_BYTES);
    const std::uint32_t fileBytes =
      cannonOffset + static_cast<std::uint32_t>(cannon.size() * ENTRY_BYTES);

    header[0] = 'P';
    header[1] = 'F';
    header[2] = 'A';
    header[3] = '1';
    put_u32(header + 4, FORMAT_VERSION);
    put_u32(header + 8, HEADER_BYTES);
    put_u32(header + 12, ENTRY_BYTES);
    put_u32(header + 16, rookOffset);
    put_u32(header + 20, static_cast<std::uint32_t>(rook.size()));
    put_u32(header + 24, cannonOffset);
    put_u32(header + 28, static_cast<std::uint32_t>(cannon.size()));
    put_u32(header + 32, rookCrc);
    put_u32(header + 36, cannonCrc);
    put_u32(header + 40, payloadCrc.value());
    put_u32(header + 44, magic_seed_crc());
    put_u32(header + 48, fileBytes);
    put_u32(header + 52, SQUARE_NB);
    put_u32(header + 56, LAYOUT_LE_LOW64_HIGH64);
    Crc32 headerCrc;
    headerCrc.update(header, HEADER_BYTES - 4);
    put_u32(header + 60, headerCrc.value());

    if (std::fseek(file, 0, SEEK_SET) != 0 ||
        std::fwrite(header, 1, sizeof(header), file) != sizeof(header) ||
        std::fclose(file) != 0)
        fail("header finalization failed");

    std::printf(
      "PIKAFISH_ATTACK_TABLE_GENERATE_PASS file=%s bytes=%u "
      "rook_entries=%zu cannon_entries=%zu rook_crc=%08x "
      "cannon_crc=%08x payload_crc=%08x magics_crc=%08x\n",
      argv[1], fileBytes, rook.size(), cannon.size(), rookCrc, cannonCrc,
      payloadCrc.value(), magic_seed_crc());
    return EXIT_SUCCESS;
}
