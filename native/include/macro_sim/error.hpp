#ifndef MACRO_SIM_ERROR_HPP
#define MACRO_SIM_ERROR_HPP

#include <cstdint>
#include <optional>
#include <string_view>
#include <utility>

namespace macro_sim {

enum class ErrorCode : std::uint32_t {
    ok = 0,
    invalid_argument = 1,
    out_of_range = 2,
    allocation_failure = 3,
    invalid_handle = 4,
    incompatible_abi = 5,
    contract_violation = 6,
    corrupt_input = 7,
    unsupported = 8,
    internal_error = 9,
};

[[nodiscard]] constexpr std::string_view error_code_name(ErrorCode code) noexcept {
    switch (code) {
        case ErrorCode::ok:
            return "ok";
        case ErrorCode::invalid_argument:
            return "invalid_argument";
        case ErrorCode::out_of_range:
            return "out_of_range";
        case ErrorCode::allocation_failure:
            return "allocation_failure";
        case ErrorCode::invalid_handle:
            return "invalid_handle";
        case ErrorCode::incompatible_abi:
            return "incompatible_abi";
        case ErrorCode::contract_violation:
            return "contract_violation";
        case ErrorCode::corrupt_input:
            return "corrupt_input";
        case ErrorCode::unsupported:
            return "unsupported";
        case ErrorCode::internal_error:
            return "internal_error";
    }
    return "unknown";
}

class Status final {
public:
    constexpr Status() noexcept = default;
    constexpr Status(ErrorCode code, std::string_view message) noexcept
        : code_(code), message_(message) {}

    [[nodiscard]] static constexpr Status success() noexcept {
        return {};
    }

    [[nodiscard]] constexpr bool ok() const noexcept {
        return code_ == ErrorCode::ok;
    }

    [[nodiscard]] constexpr ErrorCode code() const noexcept {
        return code_;
    }

    [[nodiscard]] constexpr std::string_view message() const noexcept {
        return message_;
    }

private:
    ErrorCode code_{ErrorCode::ok};
    std::string_view message_{};
};

template <typename T>
class Result final {
public:
    Result(T value) : value_(std::move(value)), status_(Status::success()) {}
    Result(Status status) : value_(std::nullopt), status_(status) {}

    [[nodiscard]] bool ok() const noexcept {
        return status_.ok();
    }

    [[nodiscard]] const Status& status() const noexcept {
        return status_;
    }

    [[nodiscard]] T* get_if() noexcept {
        return value_ ? &*value_ : nullptr;
    }

    [[nodiscard]] const T* get_if() const noexcept {
        return value_ ? &*value_ : nullptr;
    }

    [[nodiscard]] T&& take() && {
        return std::move(*value_);
    }

private:
    std::optional<T> value_;
    Status status_;
};

}  // namespace macro_sim

#endif
