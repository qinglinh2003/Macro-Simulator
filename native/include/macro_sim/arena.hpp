#ifndef MACRO_SIM_ARENA_HPP
#define MACRO_SIM_ARENA_HPP

#include <cstddef>
#include <cstdint>
#include <limits>
#include <utility>

#include "macro_sim/buffer.hpp"
#include "macro_sim/error.hpp"

namespace macro_sim {

class MonotonicArena final {
public:
    MonotonicArena(MonotonicArena&&) noexcept = default;
    MonotonicArena& operator=(MonotonicArena&&) noexcept = default;
    MonotonicArena(const MonotonicArena&) = delete;
    MonotonicArena& operator=(const MonotonicArena&) = delete;

    [[nodiscard]] static Result<MonotonicArena> create(std::size_t capacity) noexcept {
        auto result = OwnedBuffer::allocate(capacity);
        if (!result.ok()) {
            return result.status();
        }
        return MonotonicArena(std::move(result).take());
    }

    [[nodiscard]] Result<MutableBufferView> allocate(
        std::size_t size,
        std::size_t alignment = alignof(std::max_align_t)
    ) noexcept {
        if (alignment == 0 || (alignment & (alignment - 1)) != 0) {
            return Status(
                ErrorCode::invalid_argument,
                "arena alignment must be a nonzero power of two"
            );
        }
        const auto storage = buffer_.mutable_view();
        const auto base = reinterpret_cast<std::uintptr_t>(storage.data);
        if (used_ > storage.size || base > std::numeric_limits<std::uintptr_t>::max() - used_) {
            return Status(ErrorCode::out_of_range, "arena cursor overflow");
        }
        const auto current = base + used_;
        const auto mask = static_cast<std::uintptr_t>(alignment - 1);
        const auto padding = static_cast<std::size_t>((alignment - (current & mask)) & mask);
        if (padding > storage.size - used_) {
            return Status(ErrorCode::allocation_failure, "arena is exhausted");
        }
        const auto aligned_offset = used_ + padding;
        if (size > storage.size - aligned_offset) {
            return Status(ErrorCode::allocation_failure, "arena is exhausted");
        }
        used_ = aligned_offset + size;
        return MutableBufferView{storage.data + aligned_offset, size};
    }

    void reset() noexcept {
        used_ = 0;
    }

    [[nodiscard]] std::size_t used() const noexcept {
        return used_;
    }

    [[nodiscard]] std::size_t capacity() const noexcept {
        return buffer_.size();
    }

private:
    explicit MonotonicArena(OwnedBuffer buffer) : buffer_(std::move(buffer)) {}

    OwnedBuffer buffer_;
    std::size_t used_{};
};

}  // namespace macro_sim

#endif
