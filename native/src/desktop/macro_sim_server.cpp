#include <algorithm>
#include <array>
#include <cerrno>
#include <csignal>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <optional>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>

#include <nlohmann/json.hpp>

#if defined(_WIN32)
#include <winsock2.h>
#include <ws2tcpip.h>
#define NOMINMAX
#include <windows.h>
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

#include "macro_sim/desktop/m11_protocol.hpp"

namespace {

using Json = nlohmann::json;
using macro_sim::desktop::kM11DesktopProtocolVersion;
using macro_sim::desktop::kM11MaximumProtocolFrameBytes;
using macro_sim::desktop::M11ProtocolOptions;
using macro_sim::desktop::M11ProtocolWorker;

inline constexpr std::size_t kMaximumBootstrapBytes = std::size_t{64} * 1024U;
inline constexpr std::size_t kSocketChunkBytes = std::size_t{64} * 1024U;

volatile std::sig_atomic_t stop_requested = 0;

void handle_signal(int) { stop_requested = 1; }

struct Bootstrap final {
    std::string token;
    std::filesystem::path save_root;
    std::filesystem::path ready_file;
    std::filesystem::path rl_artifact;
};

[[nodiscard]] std::filesystem::path path_from_utf8(const std::string &value) {
    return std::filesystem::path(
        std::u8string(reinterpret_cast<const char8_t *>(value.data()), value.size()));
}

#if defined(_WIN32)
using SocketHandle = SOCKET;
using SocketLength = int;
inline constexpr SocketHandle kInvalidSocket = INVALID_SOCKET;
#else
using SocketHandle = int;
using SocketLength = socklen_t;
inline constexpr SocketHandle kInvalidSocket = -1;
#endif

class Socket final {
  public:
    explicit Socket(SocketHandle handle = kInvalidSocket) noexcept : handle_(handle) {}
    Socket(const Socket &) = delete;
    Socket &operator=(const Socket &) = delete;
    Socket(Socket &&other) noexcept
        : handle_(std::exchange(other.handle_, kInvalidSocket)) {}
    Socket &operator=(Socket &&other) noexcept {
        if (this != &other) {
            close();
            handle_ = std::exchange(other.handle_, kInvalidSocket);
        }
        return *this;
    }
    ~Socket() { close(); }

    [[nodiscard]] SocketHandle get() const noexcept { return handle_; }
    [[nodiscard]] bool valid() const noexcept { return handle_ != kInvalidSocket; }

  private:
    void close() noexcept {
        if (!valid()) {
            return;
        }
#if defined(_WIN32)
        closesocket(handle_);
#else
        ::close(handle_);
#endif
        handle_ = kInvalidSocket;
    }

    SocketHandle handle_{kInvalidSocket};
};

[[nodiscard]] std::optional<std::string>
read_small_file(const std::filesystem::path &path) {
    std::error_code error;
    const auto status = std::filesystem::symlink_status(path, error);
    if (error || std::filesystem::is_symlink(status) ||
        !std::filesystem::is_regular_file(status)) {
        return std::nullopt;
    }
#if !defined(_WIN32)
    struct stat native_status = {};
    if (::stat(path.c_str(), &native_status) != 0 ||
        (native_status.st_mode & static_cast<mode_t>(0077)) != 0) {
        return std::nullopt;
    }
#endif
    const auto size = std::filesystem::file_size(path, error);
    if (error || size == 0U || size > kMaximumBootstrapBytes) {
        return std::nullopt;
    }
    std::string bytes(static_cast<std::size_t>(size), '\0');
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
        return std::nullopt;
    }
    stream.read(bytes.data(), static_cast<std::streamsize>(bytes.size()));
    if (!stream) {
        return std::nullopt;
    }
    return bytes;
}

[[nodiscard]] std::optional<Bootstrap>
load_bootstrap(const std::filesystem::path &path) {
    if (!path.is_absolute()) {
        return std::nullopt;
    }
    const auto content = read_small_file(path);
    std::error_code cleanup_error;
    std::filesystem::remove(path, cleanup_error);
    if (!content.has_value()) {
        return std::nullopt;
    }
    try {
        const auto document = Json::parse(*content);
        if (!document.is_object() || document.size() < 3U || document.size() > 4U ||
            !document.contains("token") || !document.contains("save_root") ||
            !document.contains("ready_file") || !document.at("token").is_string() ||
            !document.at("save_root").is_string() ||
            !document.at("ready_file").is_string()) {
            return std::nullopt;
        }
        Bootstrap result;
        result.token = document.at("token").get<std::string>();
        result.save_root = path_from_utf8(document.at("save_root").get<std::string>());
        result.ready_file =
            path_from_utf8(document.at("ready_file").get<std::string>());
        if (document.contains("rl_artifact")) {
            if (!document.at("rl_artifact").is_string()) {
                return std::nullopt;
            }
            result.rl_artifact =
                path_from_utf8(document.at("rl_artifact").get<std::string>());
        }
        if (!macro_sim::desktop::valid_m11_capability_token(result.token) ||
            !result.save_root.is_absolute() || !result.ready_file.is_absolute() ||
            (!result.rl_artifact.empty() && !result.rl_artifact.is_absolute())) {
            return std::nullopt;
        }
        return result;
    } catch (...) {
        return std::nullopt;
    }
}

[[nodiscard]] bool write_ready_file(const std::filesystem::path &path,
                                    std::uint16_t port) {
    std::error_code error;
    std::filesystem::create_directories(path.parent_path(), error);
    if (error) {
        return false;
    }
    const auto temporary = path.parent_path() / (path.filename().string() + ".tmp");
    const auto payload =
        Json{
            {"status", "ready"},
            {"host", "127.0.0.1"},
            {"port", port},
            {"protocol_version", kM11DesktopProtocolVersion},
#if defined(_WIN32)
            {"pid", static_cast<std::uint64_t>(GetCurrentProcessId())},
#else
            {"pid", static_cast<std::uint64_t>(::getpid())},
#endif
        }
            .dump();
    {
        std::ofstream stream(temporary, std::ios::binary | std::ios::trunc);
        if (!stream) {
            return false;
        }
        stream.write(payload.data(), static_cast<std::streamsize>(payload.size()));
        stream.flush();
        if (!stream) {
            return false;
        }
    }
    std::filesystem::permissions(temporary,
                                 std::filesystem::perms::owner_read |
                                     std::filesystem::perms::owner_write,
                                 std::filesystem::perm_options::replace, error);
    if (error) {
        std::filesystem::remove(temporary, error);
        return false;
    }
    std::filesystem::rename(temporary, path, error);
    if (error) {
        std::filesystem::remove(temporary, error);
        return false;
    }
    return true;
}

[[nodiscard]] bool send_all(SocketHandle socket, std::string_view bytes) {
    std::size_t offset = 0U;
    while (offset < bytes.size()) {
        const auto remaining = bytes.size() - offset;
        // Windows headers define a max() macro; the parenthesized call keeps
        // this translation unit portable across MSVC and POSIX toolchains.
        const auto count = std::min<std::size_t>(
            remaining, static_cast<std::size_t>((std::numeric_limits<int>::max)()));
#if defined(_WIN32)
        const auto sent =
            ::send(socket, bytes.data() + offset, static_cast<int>(count), 0);
        if (sent == SOCKET_ERROR) {
            if (WSAGetLastError() == WSAEINTR) {
                continue;
            }
            return false;
        }
#else
#if defined(MSG_NOSIGNAL)
        constexpr int send_flags = MSG_NOSIGNAL;
#else
        constexpr int send_flags = 0;
#endif
        const auto sent = ::send(socket, bytes.data() + offset, count, send_flags);
        if (sent < 0) {
            if (errno == EINTR) {
                continue;
            }
            return false;
        }
#endif
        if (sent == 0) {
            return false;
        }
        offset += static_cast<std::size_t>(sent);
    }
    return true;
}

[[nodiscard]] bool serve_connection(SocketHandle socket, M11ProtocolWorker &worker) {
    std::string buffer;
    buffer.reserve(kSocketChunkBytes);
    std::array<char, kSocketChunkBytes> chunk{};
    while (!worker.shutdown_requested() && stop_requested == 0) {
#if defined(_WIN32)
        const auto received =
            ::recv(socket, chunk.data(), static_cast<int>(chunk.size()), 0);
        if (received == SOCKET_ERROR) {
            if (WSAGetLastError() == WSAEINTR) {
                continue;
            }
            return false;
        }
#else
        const auto received = ::recv(socket, chunk.data(), chunk.size(), 0);
        if (received < 0) {
            if (errno == EINTR) {
                continue;
            }
            return false;
        }
#endif
        if (received == 0) {
            return true;
        }
        buffer.append(chunk.data(), static_cast<std::size_t>(received));
        while (true) {
            const auto newline = buffer.find('\n');
            if (newline == std::string::npos) {
                break;
            }
            auto frame = buffer.substr(0U, newline);
            buffer.erase(0U, newline + 1U);
            if (!frame.empty() && frame.back() == '\r') {
                frame.pop_back();
            }
            const auto response = worker.handle_frame(frame);
            if (!send_all(socket, response) || !send_all(socket, "\n")) {
                return false;
            }
            if (worker.shutdown_requested()) {
                return true;
            }
        }
        if (buffer.size() > kM11MaximumProtocolFrameBytes) {
            const auto response = worker.handle_frame(buffer);
            static_cast<void>(send_all(socket, response));
            static_cast<void>(send_all(socket, "\n"));
            return false;
        }
    }
    return true;
}

[[nodiscard]] std::optional<std::pair<Socket, std::uint16_t>> listen_loopback() {
#if defined(_WIN32)
    WSADATA data{};
    if (WSAStartup(MAKEWORD(2, 2), &data) != 0) {
        return std::nullopt;
    }
#endif
    Socket listener(::socket(AF_INET, SOCK_STREAM, IPPROTO_TCP));
    if (!listener.valid()) {
        return std::nullopt;
    }
    int enabled = 1;
    static_cast<void>(setsockopt(listener.get(), SOL_SOCKET, SO_REUSEADDR,
                                 reinterpret_cast<const char *>(&enabled),
                                 static_cast<SocketLength>(sizeof(enabled))));
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = htons(0U);
    if (::bind(listener.get(), reinterpret_cast<const sockaddr *>(&address),
               sizeof(address)) != 0 ||
        ::listen(listener.get(), 4) != 0) {
        return std::nullopt;
    }
    SocketLength length = static_cast<SocketLength>(sizeof(address));
    if (::getsockname(listener.get(), reinterpret_cast<sockaddr *>(&address),
                      &length) != 0) {
        return std::nullopt;
    }
    return std::pair(std::move(listener), ntohs(address.sin_port));
}

[[nodiscard]] int run(const std::filesystem::path &bootstrap_path) {
    const auto bootstrap = load_bootstrap(bootstrap_path);
    if (!bootstrap.has_value()) {
        std::cerr << "Invalid bootstrap channel.\n";
        return 2;
    }
    M11ProtocolOptions options;
    options.capability_token = bootstrap->token;
    options.save_root = bootstrap->save_root;
    options.built_in_rl_artifact = bootstrap->rl_artifact;
    auto worker = M11ProtocolWorker::create(std::move(options));
    if (!worker.ok()) {
        std::cerr << "Could not initialize protocol worker.\n";
        return 3;
    }
    auto listener = listen_loopback();
    if (!listener.has_value()) {
        std::cerr << "Could not bind loopback socket.\n";
        return 4;
    }
    if (!write_ready_file(bootstrap->ready_file, listener->second)) {
        std::cerr << "Could not publish readiness.\n";
        return 5;
    }
    std::signal(SIGINT, handle_signal);
    std::signal(SIGTERM, handle_signal);
#if !defined(_WIN32)
    std::signal(SIGPIPE, SIG_IGN);
#endif
    while (!worker.get_if()->shutdown_requested() && stop_requested == 0) {
        sockaddr_in peer{};
        SocketLength peer_length = static_cast<SocketLength>(sizeof(peer));
        Socket connection(::accept(listener->first.get(),
                                   reinterpret_cast<sockaddr *>(&peer), &peer_length));
        if (!connection.valid()) {
#if defined(_WIN32)
            if (WSAGetLastError() == WSAEINTR) {
                continue;
            }
#else
            if (errno == EINTR) {
                continue;
            }
#endif
            break;
        }
        if (peer.sin_addr.s_addr != htonl(INADDR_LOOPBACK)) {
            continue;
        }
        static_cast<void>(serve_connection(connection.get(), *worker.get_if()));
    }
    std::error_code cleanup_error;
    std::filesystem::remove(bootstrap->ready_file, cleanup_error);
#if defined(_WIN32)
    WSACleanup();
#endif
    return 0;
}

} // namespace

#if defined(_WIN32)
int wmain(int argc, wchar_t **argv) {
    try {
        if (argc != 3 || std::wstring_view(argv[1]) != L"--bootstrap") {
            std::cerr << "Usage: macro_sim_server --bootstrap <absolute-path>\n";
            return 1;
        }
        return run(std::filesystem::path(argv[2]));
    } catch (...) {
        std::cerr << "The native worker failed unexpectedly.\n";
        return 1;
    }
}
#else
int main(int argc, char **argv) {
    try {
        if (argc != 3 || std::string_view(argv[1]) != "--bootstrap") {
            std::cerr << "Usage: macro_sim_server --bootstrap <absolute-path>\n";
            return 1;
        }
        return run(std::filesystem::path(argv[2]));
    } catch (...) {
        std::cerr << "The native worker failed unexpectedly.\n";
        return 1;
    }
}
#endif
