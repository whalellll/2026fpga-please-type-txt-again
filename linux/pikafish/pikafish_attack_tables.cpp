#include "pikafish_attack_tables.h"

#include <array>
#include <cerrno>
#include <cstdint>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

#include "magics.h"

namespace Stockfish::Attacks {
namespace {

constexpr std::uint32_t FORMAT_VERSION = 1;
constexpr std::uint32_t HEADER_BYTES = 64;
constexpr std::uint32_t ENTRY_BYTES = 16;
constexpr std::uint32_t ROOK_OFFSET = HEADER_BYTES;
constexpr std::uint32_t CANNON_OFFSET = 0x01080040U;
constexpr std::uint32_t LAYOUT_LE_LOW64_HIGH64 = 1;

std::uint32_t read_u32(const std::uint8_t* data) {
    return std::uint32_t(data[0]) | (std::uint32_t(data[1]) << 8)
         | (std::uint32_t(data[2]) << 16) | (std::uint32_t(data[3]) << 24);
}

void put_u64(std::uint8_t* out, std::uint64_t value) {
    for (unsigned byte = 0; byte < 8; ++byte)
        out[byte] = static_cast<std::uint8_t>(value >> (byte * 8));
}

constexpr std::array<std::uint32_t, 256> make_crc32_table() {
    std::array<std::uint32_t, 256> table{};
    for (std::uint32_t index = 0; index < table.size(); ++index)
    {
        std::uint32_t value = index;
        for (unsigned bit = 0; bit < 8; ++bit)
            value = (value >> 1) ^ (0xedb88320U & (0U - (value & 1U)));
        table[index] = value;
    }
    return table;
}

constexpr auto CRC32_TABLE = make_crc32_table();

std::uint32_t crc32_update(std::uint32_t crc, const std::uint8_t* data,
                           std::size_t bytes) {
    while (bytes-- != 0)
        crc = (crc >> 8) ^ CRC32_TABLE[(crc ^ *data++) & 0xffU];
    return crc;
}

std::uint32_t crc32_bytes(const std::uint8_t* data, std::size_t bytes) {
    return crc32_update(0xffffffffU, data, bytes) ^ 0xffffffffU;
}

std::uint32_t expected_magics_crc() {
    std::uint32_t crc = 0xffffffffU;
    std::uint8_t encoded[ENTRY_BYTES];
    for (const Bitboard value : RookMagicsInit)
    {
        put_u64(encoded, static_cast<u64>(value));
        put_u64(encoded + 8, static_cast<u64>(value >> 64));
        crc = crc32_update(crc, encoded, sizeof(encoded));
    }
    return crc ^ 0xffffffffU;
}

bool reject(const char* message, const char*& error) {
    error = message;
    return false;
}

bool parse_precomputed_attack_tables_impl(const void* image, std::size_t bytes,
                                          PrecomputedAttackTableView& view,
                                          const char*& error,
                                          bool verifyPayloadCrc) {
    static_assert(sizeof(MagicMask) == ENTRY_BYTES);
    view = {};
    error = nullptr;
    if (!image || bytes != PIKAFISH_ATTACK_TABLE_BYTES)
        return reject("PFA1 physical image size mismatch", error);

    const auto* data = static_cast<const std::uint8_t*>(image);
    if (data[0] != 'P' || data[1] != 'F' || data[2] != 'A' || data[3] != '1')
        return reject("PFA1 magic mismatch", error);
    if (read_u32(data + 4) != FORMAT_VERSION || read_u32(data + 8) != HEADER_BYTES
        || read_u32(data + 12) != ENTRY_BYTES)
        return reject("PFA1 version or element size mismatch", error);

    const std::uint32_t rookOffset = read_u32(data + 16);
    const std::uint32_t rookCount = read_u32(data + 20);
    const std::uint32_t cannonOffset = read_u32(data + 24);
    const std::uint32_t cannonCount = read_u32(data + 28);
    if (rookOffset != ROOK_OFFSET || cannonOffset != CANNON_OFFSET
        || rookCount != PIKAFISH_ATTACK_TABLE_ENTRIES
        || cannonCount != PIKAFISH_ATTACK_TABLE_ENTRIES)
        return reject("PFA1 table layout mismatch", error);
    if (read_u32(data + 48) != bytes || read_u32(data + 52) != SQUARE_NB
        || read_u32(data + 56) != LAYOUT_LE_LOW64_HIGH64)
        return reject("PFA1 file size, square count, or layout mismatch", error);
    if (crc32_bytes(data, HEADER_BYTES - 4) != read_u32(data + 60))
        return reject("PFA1 header CRC mismatch", error);
    if (read_u32(data + 44) != expected_magics_crc())
        return reject("PFA1 magic seed fingerprint mismatch", error);

    const std::size_t tableBytes = PIKAFISH_ATTACK_TABLE_ENTRIES * ENTRY_BYTES;
    const auto* rookBytes = data + rookOffset;
    const auto* cannonBytes = data + cannonOffset;
    if (verifyPayloadCrc)
    {
        if (crc32_bytes(rookBytes, tableBytes) != read_u32(data + 32))
            return reject("PFA1 rook table CRC mismatch", error);
        if (crc32_bytes(cannonBytes, tableBytes) != read_u32(data + 36))
            return reject("PFA1 cannon table CRC mismatch", error);
        if (crc32_bytes(rookBytes, 2 * tableBytes) != read_u32(data + 40))
            return reject("PFA1 payload CRC mismatch", error);
    }

    if ((reinterpret_cast<std::uintptr_t>(rookBytes) % alignof(MagicMask)) != 0
        || (reinterpret_cast<std::uintptr_t>(cannonBytes) % alignof(MagicMask)) != 0)
        return reject("PFA1 table alignment mismatch", error);

    view.rook = reinterpret_cast<const MagicMask*>(rookBytes);
    view.cannon = reinterpret_cast<const MagicMask*>(cannonBytes);
    view.rookCount = rookCount;
    view.cannonCount = cannonCount;
    return true;
}

}  // namespace

bool parse_precomputed_attack_tables(const void* image, std::size_t bytes,
                                     PrecomputedAttackTableView& view,
                                     const char*& error) {
    return parse_precomputed_attack_tables_impl(image, bytes, view, error, true);
}

bool map_precomputed_attack_tables(PrecomputedAttackTableMapping& mapping,
                                   const char*& error) {
    mapping = {};
    error = nullptr;
    const int fd = open("/dev/mem", O_RDONLY | O_CLOEXEC);
    if (fd < 0)
        return reject("cannot open /dev/mem for PFA1", error);

    void* address = mmap(nullptr, PIKAFISH_ATTACK_TABLE_BYTES, PROT_READ, MAP_SHARED, fd,
                         static_cast<off_t>(PIKAFISH_ATTACK_TABLE_PHYS));
    const int savedErrno = errno;
    close(fd);
    if (address == MAP_FAILED)
    {
        errno = savedErrno;
        return reject("cannot mmap PFA1 physical image", error);
    }

    PrecomputedAttackTableView view;
    // The checked-in image is fully verified before SD preparation and every SD
    // block has a transport CRC16. Avoid rereading 66 MiB on the cacheless RV32;
    // retain header/layout/fingerprint checks before binding the mapped tables.
    if (!parse_precomputed_attack_tables_impl(
          address, PIKAFISH_ATTACK_TABLE_BYTES, view, error, false))
    {
        munmap(address, PIKAFISH_ATTACK_TABLE_BYTES);
        return false;
    }
    mapping.address = address;
    mapping.bytes = PIKAFISH_ATTACK_TABLE_BYTES;
    mapping.view = view;
    return true;
}

void unmap_precomputed_attack_tables(PrecomputedAttackTableMapping& mapping) {
    if (mapping.address && mapping.bytes)
        munmap(mapping.address, mapping.bytes);
    mapping = {};
}

}  // namespace Stockfish::Attacks
