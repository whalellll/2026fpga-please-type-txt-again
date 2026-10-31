#ifndef PIKAFISH_PFF1_VIEW_H_INCLUDED
#define PIKAFISH_PFF1_VIEW_H_INCLUDED

#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace Stockfish::Eval::NNUE {

// A trivially-copyable, process-lifetime view used only by the embedded PFF1
// build. The mapped model is immutable; mutable access exists solely so the
// upstream NNUE templates continue to compile and must never be used after
// bind().
template<typename T, std::size_t N>
class Pff1ArrayView {
   public:
    using value_type     = T;
    using size_type      = std::size_t;
    using iterator       = T*;
    using const_iterator = const T*;

    static constexpr size_type extent    = N;
    static constexpr size_type byte_size = N * sizeof(T);

    constexpr size_type size() const noexcept { return N; }
    constexpr bool      empty() const noexcept { return N == 0; }

    T*       data() noexcept { return elements; }
    const T* data() const noexcept { return elements; }

    T&       operator[](size_type index) noexcept { return elements[index]; }
    const T& operator[](size_type index) const noexcept { return elements[index]; }

    iterator       begin() noexcept { return elements; }
    const_iterator begin() const noexcept { return elements; }
    const_iterator cbegin() const noexcept { return elements; }
    iterator       end() noexcept { return elements + N; }
    const_iterator end() const noexcept { return elements + N; }
    const_iterator cend() const noexcept { return elements + N; }

    bool bind(const void* address, size_type bytes) noexcept {
        const auto numeric = reinterpret_cast<std::uintptr_t>(address);
        if (address == nullptr || bytes != byte_size || numeric % alignof(T) != 0)
            return false;
        elements = const_cast<T*>(static_cast<const T*>(address));
        return true;
    }

   private:
    T* elements = nullptr;
};

static_assert(std::is_trivially_copyable_v<Pff1ArrayView<std::uint8_t, 1>>);
static_assert(std::is_trivially_destructible_v<Pff1ArrayView<std::uint8_t, 1>>);

}  // namespace Stockfish::Eval::NNUE

#endif  // PIKAFISH_PFF1_VIEW_H_INCLUDED
