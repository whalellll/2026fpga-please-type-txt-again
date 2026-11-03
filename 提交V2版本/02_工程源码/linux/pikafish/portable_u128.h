#ifndef PIKAFISH_PORTABLE_U128_H_INCLUDED
#define PIKAFISH_PORTABLE_U128_H_INCLUDED

#include <cstdint>
#include <type_traits>

namespace Stockfish {

// GCC does not provide __int128 on RV32. Pikafish only needs unsigned,
// modulo-2^128 arithmetic for bitboards and magic indexing.
class PortableUInt128 {
   public:
    using u64 = std::uint64_t;
    using u32 = std::uint32_t;

    constexpr PortableUInt128() = default;

    template<typename T, typename = std::enable_if_t<std::is_integral_v<T>>>
    constexpr PortableUInt128(T value) : lo_(static_cast<u64>(value)), hi_(0) {}

    template<typename T,
             typename = std::enable_if_t<std::is_integral_v<T> && !std::is_same_v<T, bool>>>
    explicit constexpr operator T() const {
        return static_cast<T>(lo_);
    }

    explicit constexpr operator bool() const { return (lo_ | hi_) != 0; }

    constexpr u64 low() const { return lo_; }
    constexpr u64 high() const { return hi_; }

    constexpr PortableUInt128& operator&=(PortableUInt128 rhs) {
        lo_ &= rhs.lo_;
        hi_ &= rhs.hi_;
        return *this;
    }

    constexpr PortableUInt128& operator|=(PortableUInt128 rhs) {
        lo_ |= rhs.lo_;
        hi_ |= rhs.hi_;
        return *this;
    }

    constexpr PortableUInt128& operator^=(PortableUInt128 rhs) {
        lo_ ^= rhs.lo_;
        hi_ ^= rhs.hi_;
        return *this;
    }

    constexpr PortableUInt128& operator+=(PortableUInt128 rhs) {
        const u64 old = lo_;
        lo_ += rhs.lo_;
        hi_ += rhs.hi_ + (lo_ < old);
        return *this;
    }

    constexpr PortableUInt128& operator-=(PortableUInt128 rhs) {
        const u64 old = lo_;
        lo_ -= rhs.lo_;
        hi_ -= rhs.hi_ + (old < rhs.lo_);
        return *this;
    }

    constexpr PortableUInt128& operator*=(PortableUInt128 rhs) {
        *this = *this * rhs;
        return *this;
    }

    constexpr PortableUInt128& operator<<=(unsigned shift) {
        *this = *this << shift;
        return *this;
    }

    constexpr PortableUInt128& operator>>=(unsigned shift) {
        *this = *this >> shift;
        return *this;
    }

    friend constexpr bool operator==(PortableUInt128 lhs, PortableUInt128 rhs) {
        return lhs.lo_ == rhs.lo_ && lhs.hi_ == rhs.hi_;
    }

    friend constexpr bool operator!=(PortableUInt128 lhs, PortableUInt128 rhs) {
        return !(lhs == rhs);
    }

    friend constexpr bool operator<(PortableUInt128 lhs, PortableUInt128 rhs) {
        return lhs.hi_ < rhs.hi_ || (lhs.hi_ == rhs.hi_ && lhs.lo_ < rhs.lo_);
    }

    friend constexpr bool operator>(PortableUInt128 lhs, PortableUInt128 rhs) {
        return rhs < lhs;
    }

    friend constexpr bool operator<=(PortableUInt128 lhs, PortableUInt128 rhs) {
        return !(rhs < lhs);
    }

    friend constexpr bool operator>=(PortableUInt128 lhs, PortableUInt128 rhs) {
        return !(lhs < rhs);
    }

    friend constexpr PortableUInt128 operator&(PortableUInt128 lhs, PortableUInt128 rhs) {
        return from_parts(lhs.lo_ & rhs.lo_, lhs.hi_ & rhs.hi_);
    }

    friend constexpr PortableUInt128 operator|(PortableUInt128 lhs, PortableUInt128 rhs) {
        return from_parts(lhs.lo_ | rhs.lo_, lhs.hi_ | rhs.hi_);
    }

    friend constexpr PortableUInt128 operator^(PortableUInt128 lhs, PortableUInt128 rhs) {
        return from_parts(lhs.lo_ ^ rhs.lo_, lhs.hi_ ^ rhs.hi_);
    }

    friend constexpr PortableUInt128 operator~(PortableUInt128 value) {
        return from_parts(~value.lo_, ~value.hi_);
    }

    friend constexpr PortableUInt128 operator+(PortableUInt128 lhs, PortableUInt128 rhs) {
        lhs += rhs;
        return lhs;
    }

    friend constexpr PortableUInt128 operator-(PortableUInt128 lhs, PortableUInt128 rhs) {
        lhs -= rhs;
        return lhs;
    }

    friend constexpr PortableUInt128 operator-(PortableUInt128 value) {
        return ~value + PortableUInt128(1);
    }

    friend constexpr PortableUInt128 operator*(PortableUInt128 lhs, PortableUInt128 rhs) {
        return from_parts(lhs.lo_ * rhs.lo_,
                          mul_hi64(lhs.lo_, rhs.lo_) + lhs.lo_ * rhs.hi_
                            + lhs.hi_ * rhs.lo_);
    }

    friend constexpr PortableUInt128 operator<<(PortableUInt128 value, unsigned shift) {
        if (shift >= 128)
            return PortableUInt128(0);
        if (shift == 0)
            return value;
        if (shift >= 64)
            return from_parts(0, value.lo_ << (shift - 64));
        return from_parts(value.lo_ << shift,
                          (value.hi_ << shift) | (value.lo_ >> (64 - shift)));
    }

    friend constexpr PortableUInt128 operator>>(PortableUInt128 value, unsigned shift) {
        if (shift >= 128)
            return PortableUInt128(0);
        if (shift == 0)
            return value;
        if (shift >= 64)
            return from_parts(value.hi_ >> (shift - 64), 0);
        return from_parts((value.lo_ >> shift) | (value.hi_ << (64 - shift)),
                          value.hi_ >> shift);
    }

   private:
    u64 lo_ = 0;
    u64 hi_ = 0;

    constexpr PortableUInt128(u64 low, u64 high) : lo_(low), hi_(high) {}

    static constexpr PortableUInt128 from_parts(u64 low, u64 high) {
        return PortableUInt128(low, high);
    }

    static constexpr u64 mul_hi64(u64 lhs, u64 rhs) {
        const u64 lhsLow  = static_cast<u32>(lhs);
        const u64 lhsHigh = lhs >> 32;
        const u64 rhsLow  = static_cast<u32>(rhs);
        const u64 rhsHigh = rhs >> 32;

        const u64 lowProduct = lhsLow * rhsLow;
        const u64 middle     = lhsHigh * rhsLow + (lowProduct >> 32);
        const u64 middleLow  = static_cast<u32>(middle) + lhsLow * rhsHigh;
        return lhsHigh * rhsHigh + (middle >> 32) + (middleLow >> 32);
    }
};

static_assert(sizeof(PortableUInt128) == 16);
static_assert((PortableUInt128(1) << 89) >> 89 == PortableUInt128(1));
static_assert(PortableUInt128(0xffffffffffffffffULL) + PortableUInt128(1)
              == (PortableUInt128(1) << 64));

}  // namespace Stockfish

#endif  // PIKAFISH_PORTABLE_U128_H_INCLUDED
