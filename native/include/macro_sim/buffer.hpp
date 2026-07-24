#ifndef MACRO_SIM_BUFFER_HPP
#define MACRO_SIM_BUFFER_HPP

#include <cstddef>
#include <limits>
#include <new>
#include <stdexcept>
#include <utility>
#include <vector>

#include "macro_sim/error.hpp"

namespace macro_sim {

struct BufferView final {
    const std::byte* data{};
    std::size_t size{};
};

struct MutableBufferView final {
    std::byte* data{};
    std::size_t size{};

    [[nodiscard]] constexpr operator BufferView() const noexcept {
        return {data, size};
    }
};

class OwnedBuffer final {
public:
    OwnedBuffer() = default;
    OwnedBuffer(OwnedBuffer&&) noexcept = default;
    OwnedBuffer& operator=(OwnedBuffer&&) noexcept = default;
    OwnedBuffer(const OwnedBuffer&) = delete;
    OwnedBuffer& operator=(const OwnedBuffer&) = delete;

    [[nodiscard]] static Result<OwnedBuffer> allocate(std::size_t size) noexcept {
        if (size > std::vector<std::byte>{}.max_size()) {
            return Status(ErrorCode::out_of_range, "buffer size exceeds max_size");
        }
        try {
            return OwnedBuffer(size);
        } catch (const std::length_error&) {
            return Status(ErrorCode::out_of_range, "buffer size is invalid");
        } catch (const std::bad_alloc&) {
            return Status(ErrorCode::allocation_failure, "buffer allocation failed");
        } catch (...) {
            return Status(ErrorCode::internal_error, "unexpected buffer allocation error");
        }
    }

    [[nodiscard]] BufferView view() const noexcept {
        return {storage_.data(), storage_.size()};
    }

    [[nodiscard]] MutableBufferView mutable_view() noexcept {
        return {storage_.data(), storage_.size()};
    }

    [[nodiscard]] std::size_t size() const noexcept {
        return storage_.size();
    }

private:
    explicit OwnedBuffer(std::size_t size) : storage_(size) {}

    std::vector<std::byte> storage_;
};

}  // namespace macro_sim

#endif
