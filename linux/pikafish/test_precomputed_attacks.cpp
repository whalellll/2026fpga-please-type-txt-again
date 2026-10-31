#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include "attacks.h"
#include "pikafish_attack_tables.h"

namespace {

template<Stockfish::PieceType Pt>
std::uint64_t validate_all_occupancies() {
    std::uint64_t count = 0;
    for (Stockfish::Square square = Stockfish::SQ_A0;
         square <= Stockfish::SQ_I9; ++square)
    {
        const auto& magic = Stockfish::Attacks::magic(square, Pt);
        Stockfish::Bitboard occupied = 0;
        do
        {
            const Stockfish::Bitboard expected =
              Stockfish::Attacks::sliding_attack<Pt>(square, occupied);
            if (magic.attack_bb(occupied) != expected)
                return 0;
            ++count;
            occupied = (occupied - magic.mask) & magic.mask;
        } while (occupied);
    }
    return count;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2)
    {
        std::fprintf(stderr, "usage: %s PIKAFISH.ATK\n", argv[0]);
        return EXIT_FAILURE;
    }
    const int fd = open(argv[1], O_RDONLY | O_CLOEXEC);
    if (fd < 0)
    {
        std::perror("open");
        return EXIT_FAILURE;
    }
    struct stat status {};
    if (fstat(fd, &status) != 0
        || static_cast<std::uint64_t>(status.st_size)
             != Stockfish::Attacks::PIKAFISH_ATTACK_TABLE_BYTES)
    {
        std::fprintf(stderr, "PRECOMPUTED_ATTACK_TEST_FAIL size\n");
        close(fd);
        return EXIT_FAILURE;
    }
    void* image = mmap(nullptr, status.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
    close(fd);
    if (image == MAP_FAILED)
    {
        std::perror("mmap");
        return EXIT_FAILURE;
    }

    Stockfish::Attacks::PrecomputedAttackTableView view;
    const char* error = nullptr;
    if (!Stockfish::Attacks::parse_precomputed_attack_tables(
          image, status.st_size, view, error)
        || !Stockfish::Attacks::init_precomputed(
          view.rook, view.rookCount, view.cannon, view.cannonCount))
    {
        std::fprintf(stderr, "PRECOMPUTED_ATTACK_TEST_FAIL parse=%s\n",
                     error ? error : "bind");
        munmap(image, status.st_size);
        return EXIT_FAILURE;
    }

    const std::uint64_t rook = validate_all_occupancies<Stockfish::ROOK>();
    const std::uint64_t cannon = validate_all_occupancies<Stockfish::CANNON>();
    if (rook != Stockfish::Attacks::PIKAFISH_ATTACK_TABLE_ENTRIES
        || cannon != Stockfish::Attacks::PIKAFISH_ATTACK_TABLE_ENTRIES
        || Stockfish::Attacks::init_precomputed(
             view.rook, view.rookCount - 1, view.cannon, view.cannonCount))
    {
        std::fprintf(stderr,
                     "PRECOMPUTED_ATTACK_TEST_FAIL rook=%llu cannon=%llu\n",
                     static_cast<unsigned long long>(rook),
                     static_cast<unsigned long long>(cannon));
        munmap(image, status.st_size);
        return EXIT_FAILURE;
    }

    std::printf("PIKAFISH_PRECOMPUTED_ATTACKS_PASS rook=%llu cannon=%llu\n",
                static_cast<unsigned long long>(rook),
                static_cast<unsigned long long>(cannon));
    munmap(image, status.st_size);
    return EXIT_SUCCESS;
}
