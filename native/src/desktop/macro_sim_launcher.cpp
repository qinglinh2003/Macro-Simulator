#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <string>
#include <string_view>
#include <system_error>
#include <thread>
#include <vector>

#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#if defined(__APPLE__)
#include <mach-o/dyld.h>
#endif

#include <nlohmann/json.hpp>

namespace {

using Json = nlohmann::json;

inline constexpr std::chrono::seconds kReadyTimeout{20};
inline constexpr std::chrono::seconds kShutdownTimeout{5};
inline constexpr std::chrono::milliseconds kProcessPollInterval{20};

volatile std::sig_atomic_t shutdown_signal = 0;

void record_shutdown_signal(int signal_number) noexcept {
    if (shutdown_signal == 0) {
        shutdown_signal = signal_number;
    }
}

class RuntimeDirectory final {
  public:
    RuntimeDirectory() = default;
    RuntimeDirectory(const RuntimeDirectory &) = delete;
    RuntimeDirectory &operator=(const RuntimeDirectory &) = delete;
    RuntimeDirectory(RuntimeDirectory &&) = delete;
    RuntimeDirectory &operator=(RuntimeDirectory &&) = delete;

    ~RuntimeDirectory() {
        if (!path_.empty()) {
            std::error_code error;
            std::filesystem::remove_all(path_, error);
        }
    }

    [[nodiscard]] bool create() {
        auto pattern =
            (std::filesystem::temp_directory_path() / "macro-simulator-launch.XXXXXX")
                .string();
        std::vector<char> bytes(pattern.begin(), pattern.end());
        bytes.push_back('\0');
        const auto *created = ::mkdtemp(bytes.data());
        if (created == nullptr) {
            return false;
        }
        path_ = created;
        return ::chmod(path_.c_str(), S_IRWXU) == 0;
    }

    [[nodiscard]] const std::filesystem::path &path() const noexcept { return path_; }

  private:
    std::filesystem::path path_;
};

class ProcessWatchdog final {
  public:
    ProcessWatchdog() = default;
    ProcessWatchdog(const ProcessWatchdog &) = delete;
    ProcessWatchdog &operator=(const ProcessWatchdog &) = delete;
    ~ProcessWatchdog() { finish(); }

    [[nodiscard]] bool create() {
        std::array<int, 2U> descriptors{};
        if (::pipe(descriptors.data()) != 0) {
            return false;
        }
        read_descriptor_ = descriptors[0];
        write_descriptor_ = descriptors[1];
        if (::fcntl(read_descriptor_, F_SETFD, FD_CLOEXEC) != 0 ||
            ::fcntl(write_descriptor_, F_SETFD, FD_CLOEXEC) != 0) {
            close_descriptors();
            return false;
        }
        return true;
    }

    [[nodiscard]] bool start(pid_t process_group,
                             const std::filesystem::path &runtime_path) {
        if (read_descriptor_ < 0 || write_descriptor_ < 0 || process_group <= 0) {
            return false;
        }
        const auto process = ::fork();
        if (process < 0) {
            return false;
        }
        if (process == 0) {
            (void)::close(write_descriptor_);
            std::array<char, 1U> buffer{};
            while (::read(read_descriptor_, buffer.data(), buffer.size()) < 0 &&
                   errno == EINTR) {
            }
            (void)::close(read_descriptor_);
            (void)::kill(-process_group, SIGTERM);
            const auto deadline = std::chrono::steady_clock::now() + kShutdownTimeout;
            while (std::chrono::steady_clock::now() < deadline &&
                   (::kill(-process_group, 0) == 0 || errno != ESRCH)) {
                std::this_thread::sleep_for(kProcessPollInterval);
            }
            (void)::kill(-process_group, SIGKILL);
            std::error_code error;
            std::filesystem::remove_all(runtime_path, error);
            _exit(0);
        }
        process_ = process;
        (void)::close(read_descriptor_);
        read_descriptor_ = -1;
        return true;
    }

    void finish() noexcept {
        if (write_descriptor_ >= 0) {
            (void)::close(write_descriptor_);
            write_descriptor_ = -1;
        }
        if (read_descriptor_ >= 0) {
            (void)::close(read_descriptor_);
            read_descriptor_ = -1;
        }
        if (process_ > 0) {
            int status = 0;
            while (::waitpid(process_, &status, 0) < 0 && errno == EINTR) {
            }
            process_ = -1;
        }
    }

  private:
    void close_descriptors() noexcept {
        if (read_descriptor_ >= 0) {
            (void)::close(read_descriptor_);
            read_descriptor_ = -1;
        }
        if (write_descriptor_ >= 0) {
            (void)::close(write_descriptor_);
            write_descriptor_ = -1;
        }
    }

    int read_descriptor_{-1};
    int write_descriptor_{-1};
    pid_t process_{-1};
};

struct PackageLayout final {
    std::filesystem::path game;
    std::filesystem::path server;
    std::filesystem::path artifact;
};

[[nodiscard]] PackageLayout package_layout(const std::filesystem::path &launcher) {
#if defined(__APPLE__)
    const auto contents = launcher.parent_path().parent_path();
    return PackageLayout{
        launcher.parent_path() / (launcher.filename().string() + ".game"),
        contents / "Resources/native/macro_sim_server",
        contents / "Resources/native/artifacts/"
                   "fiscal_stabilization_v1.msrl",
    };
#else
    const auto root = launcher.parent_path();
    return PackageLayout{
        root / (launcher.filename().string() + ".game"),
        root / "native/macro_sim_server",
        root / "native/artifacts/fiscal_stabilization_v1.msrl",
    };
#endif
}

[[nodiscard]] std::optional<std::filesystem::path> executable_path() {
#if defined(__APPLE__)
    std::uint32_t size = 0U;
    (void)_NSGetExecutablePath(nullptr, &size);
    if (size == 0U) {
        return std::nullopt;
    }
    std::vector<char> bytes(size, '\0');
    if (_NSGetExecutablePath(bytes.data(), &size) != 0) {
        return std::nullopt;
    }
    std::error_code error;
    auto path =
        std::filesystem::weakly_canonical(std::filesystem::path(bytes.data()), error);
    return error ? std::nullopt : std::optional<std::filesystem::path>(std::move(path));
#elif defined(__linux__)
    std::array<char, 4096U> bytes{};
    const auto count = ::readlink("/proc/self/exe", bytes.data(), bytes.size() - 1U);
    if (count <= 0) {
        return std::nullopt;
    }
    bytes[static_cast<std::size_t>(count)] = '\0';
    return std::filesystem::path(bytes.data());
#else
    return std::nullopt;
#endif
}

[[nodiscard]] std::optional<std::string> secure_token() {
    std::array<std::uint8_t, 32U> bytes{};
    const auto descriptor = ::open("/dev/urandom", O_RDONLY);
    if (descriptor < 0) {
        return std::nullopt;
    }
    std::size_t offset = 0U;
    while (offset < bytes.size()) {
        const auto count =
            ::read(descriptor, bytes.data() + offset, bytes.size() - offset);
        if (count <= 0) {
            (void)::close(descriptor);
            return std::nullopt;
        }
        offset += static_cast<std::size_t>(count);
    }
    (void)::close(descriptor);
    static constexpr std::array<char, 16U> digits{
        '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'd', 'e', 'f',
    };
    std::string result;
    result.reserve(bytes.size() * 2U);
    for (const auto byte : bytes) {
        result.push_back(digits[byte >> 4U]);
        result.push_back(digits[byte & 0x0fU]);
    }
    return result;
}

[[nodiscard]] bool write_private_file(const std::filesystem::path &path,
                                      std::string_view content) {
    const auto descriptor =
        ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL, S_IRUSR | S_IWUSR);
    if (descriptor < 0) {
        return false;
    }
    std::size_t offset = 0U;
    while (offset < content.size()) {
        const auto count =
            ::write(descriptor, content.data() + offset, content.size() - offset);
        if (count <= 0) {
            (void)::close(descriptor);
            return false;
        }
        offset += static_cast<std::size_t>(count);
    }
    return ::close(descriptor) == 0;
}

[[nodiscard]] std::optional<std::string>
read_private_file(const std::filesystem::path &path) {
    struct stat status{};
    if (::lstat(path.c_str(), &status) != 0 || !S_ISREG(status.st_mode) ||
        (status.st_mode & static_cast<mode_t>(0077)) != 0 || status.st_size <= 0 ||
        status.st_size > 65536) {
        return std::nullopt;
    }
    std::string content(static_cast<std::size_t>(status.st_size), '\0');
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
        return std::nullopt;
    }
    stream.read(content.data(), static_cast<std::streamsize>(content.size()));
    return stream ? std::optional<std::string>(std::move(content)) : std::nullopt;
}

[[nodiscard]] std::filesystem::path save_root() {
    const auto *home = std::getenv("HOME");
#if defined(__APPLE__)
    return home == nullptr
               ? std::filesystem::temp_directory_path() / "Macro Simulator/saves"
               : std::filesystem::path(home) / "Library/Application Support/"
                                               "Macro Simulator/saves";
#else
    const auto *data = std::getenv("XDG_DATA_HOME");
    if (data != nullptr && *data != '\0') {
        return std::filesystem::path(data) / "macro-simulator/saves";
    }
    return home == nullptr
               ? std::filesystem::temp_directory_path() / "macro-simulator/saves"
               : std::filesystem::path(home) / ".local/share/macro-simulator/saves";
#endif
}

[[nodiscard]] pid_t
launch_process(const std::filesystem::path &executable,
               const std::vector<std::string> &arguments,
               const std::optional<std::pair<std::string, std::string>> &environment =
                   std::nullopt,
               pid_t process_group = 0) {
    const auto process = ::fork();
    if (process != 0) {
        if (process > 0) {
            (void)::setpgid(process, process_group == 0 ? process : process_group);
        }
        return process;
    }
    if (::setpgid(0, process_group) != 0) {
        _exit(126);
    }
    if (environment.has_value() &&
        ::setenv(environment->first.c_str(), environment->second.c_str(), 1) != 0) {
        _exit(126);
    }
    std::vector<char *> native_arguments;
    native_arguments.reserve(arguments.size() + 2U);
    native_arguments.push_back(const_cast<char *>(executable.c_str()));
    for (const auto &argument : arguments) {
        native_arguments.push_back(const_cast<char *>(argument.c_str()));
    }
    native_arguments.push_back(nullptr);
    ::execv(executable.c_str(), native_arguments.data());
    _exit(errno == ENOENT ? 127 : 126);
}

[[nodiscard]] std::optional<std::uint16_t>
wait_for_ready(const std::filesystem::path &ready_file, pid_t worker,
               bool &worker_reaped) {
    const auto deadline = std::chrono::steady_clock::now() + kReadyTimeout;
    while (shutdown_signal == 0 && std::chrono::steady_clock::now() < deadline) {
        int status = 0;
        if (::waitpid(worker, &status, WNOHANG) == worker) {
            worker_reaped = true;
            return std::nullopt;
        }
        const auto content = read_private_file(ready_file);
        if (content.has_value()) {
            try {
                const auto document = Json::parse(*content);
                if (document.is_object() && document.at("status") == "ready" &&
                    document.at("host") == "127.0.0.1" &&
                    document.at("protocol_version") == 5U) {
                    const auto port = document.at("port").get<std::uint16_t>();
                    if (port > 0U) {
                        return port;
                    }
                }
            } catch (...) {
                return std::nullopt;
            }
        }
        std::this_thread::sleep_for(kProcessPollInterval);
    }
    return std::nullopt;
}

void terminate_process(pid_t process) {
    if (process <= 0) {
        return;
    }
    int status = 0;
    if (::waitpid(process, &status, WNOHANG) == process) {
        return;
    }
    (void)::kill(process, SIGTERM);
    const auto deadline = std::chrono::steady_clock::now() + kShutdownTimeout;
    while (std::chrono::steady_clock::now() < deadline) {
        if (::waitpid(process, &status, WNOHANG) == process) {
            return;
        }
        std::this_thread::sleep_for(kProcessPollInterval);
    }
    (void)::kill(process, SIGKILL);
    (void)::waitpid(process, &status, 0);
}

[[nodiscard]] int exit_code(int status) noexcept {
    if (WIFEXITED(status)) {
        return WEXITSTATUS(status);
    }
    if (WIFSIGNALED(status)) {
        return 128 + WTERMSIG(status);
    }
    return 1;
}

} // namespace

int main(int argument_count, char **arguments) {
    (void)::umask(static_cast<mode_t>(0077));
    (void)std::signal(SIGINT, record_shutdown_signal);
    (void)std::signal(SIGTERM, record_shutdown_signal);
    const auto launcher = executable_path();
    if (!launcher.has_value()) {
        std::cerr << "Unable to resolve the packaged launcher.\n";
        return 1;
    }
    const auto layout = package_layout(*launcher);
    if (!std::filesystem::is_regular_file(layout.game) ||
        !std::filesystem::is_regular_file(layout.server)) {
        std::cerr << "The packaged desktop runtime is incomplete.\n";
        return 1;
    }

    RuntimeDirectory runtime;
    const auto token = secure_token();
    if (!runtime.create() || !token.has_value()) {
        std::cerr << "Unable to create a secure launch channel.\n";
        return 1;
    }
    const auto bootstrap = runtime.path() / "worker-bootstrap.json";
    const auto ready = runtime.path() / "worker-ready.json";
    const auto client = runtime.path() / "godot-bootstrap.json";
    const auto saves = save_root();
    std::error_code error;
    std::filesystem::create_directories(saves, error);
    if (error) {
        std::cerr << "Unable to create the save directory.\n";
        return 1;
    }
    Json worker_bootstrap{
        {"ready_file", ready.string()},
        {"save_root", saves.string()},
        {"token", *token},
    };
    if (std::filesystem::is_regular_file(layout.artifact)) {
        worker_bootstrap["rl_artifact"] = layout.artifact.string();
    }
    if (!write_private_file(bootstrap, worker_bootstrap.dump())) {
        std::cerr << "Unable to initialize the native worker.\n";
        return 1;
    }

    ProcessWatchdog watchdog;
    if (!watchdog.create()) {
        std::cerr << "Unable to create the desktop process watchdog.\n";
        return 1;
    }
    const auto worker =
        launch_process(layout.server, {"--bootstrap", bootstrap.string()});
    if (worker <= 0) {
        std::cerr << "Unable to launch the native worker.\n";
        return 1;
    }
    if (!watchdog.start(worker, runtime.path())) {
        terminate_process(worker);
        std::cerr << "Unable to start the desktop process watchdog.\n";
        return 1;
    }
    bool worker_reaped = false;
    const auto port = wait_for_ready(ready, worker, worker_reaped);
    if (!port.has_value()) {
        if (!worker_reaped) {
            terminate_process(worker);
        }
        if (shutdown_signal != 0) {
            return 128 + shutdown_signal;
        }
        std::cerr << "The native worker did not become ready.\n";
        return 1;
    }
    const auto client_bootstrap =
        Json{
            {"host", "127.0.0.1"},
            {"port", *port},
            {"protocol_version", 5U},
            {"token", *token},
        }
            .dump();
    if (!write_private_file(client, client_bootstrap)) {
        terminate_process(worker);
        std::cerr << "Unable to configure the desktop client.\n";
        return 1;
    }

    std::vector<std::string> game_arguments;
    game_arguments.reserve(static_cast<std::size_t>(std::max(0, argument_count - 1)));
    for (int index = 1; index < argument_count; ++index) {
        game_arguments.emplace_back(arguments[index]);
    }
    const auto game_process = launch_process(
        layout.game, game_arguments,
        std::pair{std::string("MACRO_SIM_CLIENT_BOOTSTRAP"), client.string()}, worker);
    if (game_process <= 0) {
        terminate_process(worker);
        std::cerr << "Unable to launch the desktop client.\n";
        return 1;
    }
    int game_status = 1 << 8;
    bool game_reaped = false;
    bool worker_failed = false;
    while (shutdown_signal == 0) {
        const auto result = ::waitpid(game_process, &game_status, WNOHANG);
        if (result == game_process) {
            game_reaped = true;
            break;
        }
        if (result < 0 && errno != EINTR) {
            break;
        }
        int worker_status = 0;
        if (::waitpid(worker, &worker_status, WNOHANG) == worker) {
            worker_reaped = true;
            const auto grace_deadline =
                std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (std::chrono::steady_clock::now() < grace_deadline) {
                if (::waitpid(game_process, &game_status, WNOHANG) == game_process) {
                    game_reaped = true;
                    break;
                }
                std::this_thread::sleep_for(kProcessPollInterval);
            }
            worker_failed = !game_reaped;
            break;
        }
        std::this_thread::sleep_for(kProcessPollInterval);
    }
    if (!game_reaped) {
        terminate_process(game_process);
    }
    if (!worker_reaped) {
        terminate_process(worker);
    }
    watchdog.finish();
    if (shutdown_signal != 0) {
        return 128 + shutdown_signal;
    }
    if (worker_failed) {
        return 1;
    }
    return exit_code(game_status);
}
