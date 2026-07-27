#ifndef MACRO_SIM_DESKTOP_M11_PROTOCOL_HPP
#define MACRO_SIM_DESKTOP_M11_PROTOCOL_HPP

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>

#include "macro_sim/error.hpp"

namespace macro_sim::desktop {

inline constexpr std::uint32_t kM11DesktopProtocolVersion = 5U;
inline constexpr std::size_t kM11MaximumProtocolFrameBytes = std::size_t{1024} * 1024U;
inline constexpr std::size_t kM11MaximumProtocolResponseBytes =
    std::size_t{4} * 1024U * 1024U;
inline constexpr std::size_t kM11MaximumProtocolReceipts = 1024U;
inline constexpr std::size_t kM11MaximumSnapshotCacheEntries = 32U;

struct M11ProtocolOptions final {
    std::string capability_token;
    std::filesystem::path save_root;
    std::filesystem::path built_in_rl_artifact;
    std::size_t maximum_frame_bytes{kM11MaximumProtocolFrameBytes};
    std::size_t maximum_response_bytes{kM11MaximumProtocolResponseBytes};
};

class M11ProtocolWorker final {
  public:
    M11ProtocolWorker(const M11ProtocolWorker &) = delete;
    M11ProtocolWorker &operator=(const M11ProtocolWorker &) = delete;
    M11ProtocolWorker(M11ProtocolWorker &&) noexcept;
    M11ProtocolWorker &operator=(M11ProtocolWorker &&) noexcept;
    ~M11ProtocolWorker();

    [[nodiscard]] static Result<M11ProtocolWorker> create(M11ProtocolOptions options);

    [[nodiscard]] std::string handle_frame(std::string_view frame);

    [[nodiscard]] bool shutdown_requested() const noexcept;
    [[nodiscard]] bool has_session() const noexcept;
    [[nodiscard]] std::string_view session_id() const noexcept;

  private:
    struct Impl;
    explicit M11ProtocolWorker(Impl *implementation) noexcept;
    Impl *implementation_{nullptr};
};

[[nodiscard]] bool valid_m11_capability_token(std::string_view token) noexcept;

} // namespace macro_sim::desktop

#endif
