#ifndef PIKAFISH_ATTACK_TABLES_H_INCLUDED
#define PIKAFISH_ATTACK_TABLES_H_INCLUDED

#include <cstddef>
#include <cstdint>

#include "attacks.h"

namespace Stockfish::Attacks {

constexpr std::uintptr_t PIKAFISH_ATTACK_TABLE_PHYS = 0x15000000U;
constexpr std::size_t PIKAFISH_ATTACK_TABLE_BYTES = 0x02100040U;
constexpr std::size_t PIKAFISH_ATTACK_TABLE_ENTRIES = 0x00108000U;

struct PrecomputedAttackTableView {
    const MagicMask* rook = nullptr;
    const MagicMask* cannon = nullptr;
    std::size_t rookCount = 0;
    std::size_t cannonCount = 0;
};

struct PrecomputedAttackTableMapping {
    void* address = nullptr;
    std::size_t bytes = 0;
    PrecomputedAttackTableView view;
};

bool parse_precomputed_attack_tables(const void* image, std::size_t bytes,
                                     PrecomputedAttackTableView& view,
                                     const char*& error);
bool map_precomputed_attack_tables(PrecomputedAttackTableMapping& mapping,
                                   const char*& error);
void unmap_precomputed_attack_tables(PrecomputedAttackTableMapping& mapping);

}  // namespace Stockfish::Attacks

#endif  // PIKAFISH_ATTACK_TABLES_H_INCLUDED
