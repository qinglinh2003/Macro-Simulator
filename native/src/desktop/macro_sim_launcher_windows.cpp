#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <optional>
#include <string>
#include <string_view>
#include <system_error>
#include <thread>
#include <utility>
#include <vector>

#define NOMINMAX
#include <aclapi.h>
#include <bcrypt.h>
#include <shellapi.h>
#include <windows.h>

#include <nlohmann/json.hpp>

namespace {

using Json = nlohmann::json;

inline constexpr std::chrono::seconds kReadyTimeout{20};
inline constexpr std::chrono::seconds kShutdownTimeout{5};
inline constexpr std::chrono::milliseconds kProcessPollInterval{20};

class Handle final {
  public:
    explicit Handle(HANDLE value = nullptr) noexcept : value_(value) {}
    Handle(const Handle &) = delete;
    Handle &operator=(const Handle &) = delete;
    Handle(Handle &&other) noexcept : value_(std::exchange(other.value_, nullptr)) {}
    Handle &operator=(Handle &&other) noexcept {
        if (this != &other) {
            close();
            value_ = std::exchange(other.value_, nullptr);
        }
        return *this;
    }
    ~Handle() { close(); }

    [[nodiscard]] HANDLE get() const noexcept { return value_; }
    [[nodiscard]] bool valid() const noexcept {
        return value_ != nullptr && value_ != INVALID_HANDLE_VALUE;
    }

  private:
    void close() noexcept {
        if (valid()) {
            CloseHandle(value_);
        }
        value_ = nullptr;
    }

    HANDLE value_{nullptr};
};

class PrivateSecurity final {
  public:
    PrivateSecurity() = default;
    PrivateSecurity(const PrivateSecurity &) = delete;
    PrivateSecurity &operator=(const PrivateSecurity &) = delete;
    ~PrivateSecurity() {
        if (access_control_list_ != nullptr) {
            LocalFree(access_control_list_);
        }
    }

    [[nodiscard]] bool initialize() {
        HANDLE raw_token = nullptr;
        if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &raw_token)) {
            return false;
        }
        Handle token(raw_token);
        DWORD size = 0U;
        GetTokenInformation(token.get(), TokenUser, nullptr, 0U, &size);
        if (size == 0U) {
            return false;
        }
        token_user_.resize(size);
        if (!GetTokenInformation(token.get(), TokenUser, token_user_.data(), size,
                                 &size)) {
            return false;
        }
        auto *user = reinterpret_cast<TOKEN_USER *>(token_user_.data());
        EXPLICIT_ACCESSW access{};
        access.grfAccessPermissions = GENERIC_ALL;
        access.grfAccessMode = SET_ACCESS;
        access.grfInheritance = SUB_CONTAINERS_AND_OBJECTS_INHERIT;
        access.Trustee.TrusteeForm = TRUSTEE_IS_SID;
        access.Trustee.TrusteeType = TRUSTEE_IS_USER;
        access.Trustee.ptstrName = reinterpret_cast<LPWSTR>(user->User.Sid);
        if (SetEntriesInAclW(1U, &access, nullptr, &access_control_list_) !=
            ERROR_SUCCESS) {
            return false;
        }
        if (!InitializeSecurityDescriptor(&security_descriptor_,
                                          SECURITY_DESCRIPTOR_REVISION) ||
            !SetSecurityDescriptorDacl(&security_descriptor_, TRUE,
                                       access_control_list_, FALSE) ||
            !SetSecurityDescriptorControl(&security_descriptor_, SE_DACL_PROTECTED,
                                          SE_DACL_PROTECTED)) {
            return false;
        }
        attributes_.nLength = sizeof(attributes_);
        attributes_.lpSecurityDescriptor = &security_descriptor_;
        attributes_.bInheritHandle = FALSE;
        return true;
    }

    [[nodiscard]] SECURITY_ATTRIBUTES *attributes() noexcept { return &attributes_; }

  private:
    std::vector<std::byte> token_user_;
    PACL access_control_list_{nullptr};
    SECURITY_DESCRIPTOR security_descriptor_{};
    SECURITY_ATTRIBUTES attributes_{};
};

[[nodiscard]] std::optional<std::wstring> environment_value(std::wstring_view name) {
    const auto required =
        GetEnvironmentVariableW(std::wstring(name).c_str(), nullptr, 0U);
    if (required == 0U) {
        return std::nullopt;
    }
    std::wstring result(required, L'\0');
    const auto written =
        GetEnvironmentVariableW(std::wstring(name).c_str(), result.data(), required);
    if (written == 0U || written >= required) {
        return std::nullopt;
    }
    result.resize(written);
    return result;
}

[[nodiscard]] std::optional<std::string> wide_to_utf8(std::wstring_view value) {
    if (value.empty()) {
        return std::string{};
    }
    const auto required = WideCharToMultiByte(
        CP_UTF8, WC_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()),
        nullptr, 0, nullptr, nullptr);
    if (required <= 0) {
        return std::nullopt;
    }
    std::string result(static_cast<std::size_t>(required), '\0');
    if (WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(),
                            static_cast<int>(value.size()), result.data(), required,
                            nullptr, nullptr) != required) {
        return std::nullopt;
    }
    return result;
}

[[nodiscard]] std::optional<std::string>
path_to_utf8(const std::filesystem::path &path) {
    return wide_to_utf8(path.native());
}

[[nodiscard]] std::optional<std::string> secure_token() {
    std::array<std::uint8_t, 32U> bytes{};
    if (BCryptGenRandom(nullptr, bytes.data(), static_cast<ULONG>(bytes.size()),
                        BCRYPT_USE_SYSTEM_PREFERRED_RNG) != 0) {
        return std::nullopt;
    }
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

[[nodiscard]] std::optional<std::filesystem::path> temporary_root() {
    DWORD capacity = MAX_PATH + 1U;
    std::vector<wchar_t> buffer(capacity, L'\0');
    while (true) {
        const auto count = GetTempPathW(capacity, buffer.data());
        if (count == 0U) {
            return std::nullopt;
        }
        if (count < capacity) {
            return std::filesystem::path(
                std::wstring(buffer.data(), static_cast<std::size_t>(count)));
        }
        capacity = count + 1U;
        buffer.assign(capacity, L'\0');
    }
}

class RuntimeDirectory final {
  public:
    RuntimeDirectory() = default;
    RuntimeDirectory(const RuntimeDirectory &) = delete;
    RuntimeDirectory &operator=(const RuntimeDirectory &) = delete;
    ~RuntimeDirectory() {
        if (!path_.empty()) {
            std::error_code error;
            std::filesystem::remove_all(path_, error);
        }
    }

    [[nodiscard]] bool create() {
        const auto root = temporary_root();
        if (!root.has_value() || !security_.initialize()) {
            return false;
        }
        for (std::uint32_t attempt = 0U; attempt < 16U; ++attempt) {
            const auto suffix = secure_token();
            if (!suffix.has_value()) {
                return false;
            }
            std::wstring name = L"macro-simulator-launch.";
            name.append(suffix->begin(), suffix->begin() + 32);
            const auto candidate = *root / name;
            if (CreateDirectoryW(candidate.c_str(), security_.attributes())) {
                path_ = candidate;
                return true;
            }
            if (GetLastError() != ERROR_ALREADY_EXISTS) {
                return false;
            }
        }
        return false;
    }

    [[nodiscard]] const std::filesystem::path &path() const noexcept { return path_; }
    [[nodiscard]] SECURITY_ATTRIBUTES *attributes() noexcept {
        return security_.attributes();
    }

  private:
    PrivateSecurity security_;
    std::filesystem::path path_;
};

[[nodiscard]] bool write_private_file(const std::filesystem::path &path,
                                      std::string_view content,
                                      SECURITY_ATTRIBUTES *attributes) {
    Handle file(CreateFileW(path.c_str(), GENERIC_WRITE, 0U, attributes, CREATE_NEW,
                            FILE_ATTRIBUTE_TEMPORARY, nullptr));
    if (!file.valid()) {
        return false;
    }
    std::size_t offset = 0U;
    while (offset < content.size()) {
        const auto remaining = std::min<std::size_t>(
            content.size() - offset, static_cast<std::size_t>(MAXDWORD));
        DWORD written = 0U;
        if (!WriteFile(file.get(), content.data() + offset,
                       static_cast<DWORD>(remaining), &written, nullptr) ||
            written == 0U) {
            return false;
        }
        offset += written;
    }
    return FlushFileBuffers(file.get()) != FALSE;
}

[[nodiscard]] std::optional<std::string>
read_private_file(const std::filesystem::path &path) {
    const auto attributes = GetFileAttributesW(path.c_str());
    if (attributes == INVALID_FILE_ATTRIBUTES ||
        (attributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT)) !=
            0U) {
        return std::nullopt;
    }
    Handle file(CreateFileW(path.c_str(), GENERIC_READ, 0U, nullptr, OPEN_EXISTING,
                            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT,
                            nullptr));
    if (!file.valid()) {
        return std::nullopt;
    }
    LARGE_INTEGER size{};
    if (!GetFileSizeEx(file.get(), &size) || size.QuadPart <= 0 ||
        size.QuadPart > 65536) {
        return std::nullopt;
    }
    std::string content(static_cast<std::size_t>(size.QuadPart), '\0');
    DWORD read = 0U;
    if (!ReadFile(file.get(), content.data(), static_cast<DWORD>(content.size()), &read,
                  nullptr) ||
        static_cast<std::size_t>(read) != content.size()) {
        return std::nullopt;
    }
    return content;
}

[[nodiscard]] std::optional<std::filesystem::path> executable_path() {
    DWORD capacity = MAX_PATH;
    std::vector<wchar_t> buffer(capacity, L'\0');
    while (true) {
        const auto count = GetModuleFileNameW(nullptr, buffer.data(), capacity);
        if (count == 0U) {
            return std::nullopt;
        }
        if (count < capacity - 1U) {
            return std::filesystem::path(
                std::wstring(buffer.data(), static_cast<std::size_t>(count)));
        }
        capacity *= 2U;
        buffer.assign(capacity, L'\0');
    }
}

struct PackageLayout final {
    std::filesystem::path game;
    std::filesystem::path server;
    std::filesystem::path artifact;
};

[[nodiscard]] PackageLayout package_layout(const std::filesystem::path &launcher) {
    auto game_name = launcher.stem().wstring();
    game_name += L".game.exe";
    const auto root = launcher.parent_path();
    return PackageLayout{
        root / game_name,
        root / "native/macro_sim_server.exe",
        root / "native/artifacts/fiscal_stabilization_v1.msrl",
    };
}

[[nodiscard]] std::filesystem::path save_root() {
    const auto local = environment_value(L"LOCALAPPDATA");
    if (local.has_value() && !local->empty()) {
        return std::filesystem::path(*local) / "Macro Simulator/saves";
    }
    const auto root = temporary_root();
    return root.value_or(std::filesystem::current_path()) / "Macro Simulator/saves";
}

[[nodiscard]] std::wstring quote_argument(std::wstring_view argument) {
    if (argument.find_first_of(L" \t\n\v\"") == std::wstring_view::npos) {
        return std::wstring(argument);
    }
    std::wstring result(1U, L'"');
    std::size_t backslashes = 0U;
    for (const auto character : argument) {
        if (character == L'\\') {
            ++backslashes;
            continue;
        }
        if (character == L'"') {
            result.append(backslashes * 2U + 1U, L'\\');
            result.push_back(L'"');
            backslashes = 0U;
            continue;
        }
        result.append(backslashes, L'\\');
        backslashes = 0U;
        result.push_back(character);
    }
    result.append(backslashes * 2U, L'\\');
    result.push_back(L'"');
    return result;
}

[[nodiscard]] Handle
launch_process(const std::filesystem::path &executable,
               const std::vector<std::wstring> &arguments, DWORD creation_flags,
               const std::optional<std::pair<std::wstring, std::wstring>> &environment =
                   std::nullopt) {
    std::wstring command = quote_argument(executable.native());
    for (const auto &argument : arguments) {
        command.push_back(L' ');
        command += quote_argument(argument);
    }
    const auto old_value = environment.has_value()
                               ? environment_value(environment->first)
                               : std::optional<std::wstring>{};
    if (environment.has_value() &&
        !SetEnvironmentVariableW(environment->first.c_str(),
                                 environment->second.c_str())) {
        return Handle{};
    }
    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    const auto created =
        CreateProcessW(executable.c_str(), command.data(), nullptr, nullptr, FALSE,
                       creation_flags, nullptr, nullptr, &startup, &process);
    if (environment.has_value()) {
        SetEnvironmentVariableW(environment->first.c_str(),
                                old_value.has_value() ? old_value->c_str() : nullptr);
    }
    if (!created) {
        return Handle{};
    }
    CloseHandle(process.hThread);
    return Handle(process.hProcess);
}

[[nodiscard]] bool valid_watchdog_path(const std::filesystem::path &runtime_path) {
    const auto root = temporary_root();
    if (!root.has_value() || !runtime_path.is_absolute() ||
        !runtime_path.filename().native().starts_with(L"macro-simulator-launch.")) {
        return false;
    }
    const auto attributes = GetFileAttributesW(runtime_path.c_str());
    if (attributes == INVALID_FILE_ATTRIBUTES ||
        (attributes & FILE_ATTRIBUTE_DIRECTORY) == 0U ||
        (attributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0U) {
        return false;
    }
    std::error_code error;
    const auto expected = std::filesystem::weakly_canonical(*root, error);
    if (error) {
        return false;
    }
    const auto actual =
        std::filesystem::weakly_canonical(runtime_path.parent_path(), error);
    return !error && actual == expected;
}

[[nodiscard]] int
cleanup_runtime_after_parent(DWORD parent_process_id,
                             const std::filesystem::path &runtime_path) {
    if (parent_process_id == 0U || !valid_watchdog_path(runtime_path)) {
        return 1;
    }
    Handle parent(OpenProcess(SYNCHRONIZE, FALSE, parent_process_id));
    if (!parent.valid()) {
        return 1;
    }
    if (WaitForSingleObject(parent.get(), INFINITE) != WAIT_OBJECT_0) {
        return 1;
    }
    std::error_code error;
    std::filesystem::remove_all(runtime_path, error);
    return error ? 1 : 0;
}

class ProcessJob final {
  public:
    [[nodiscard]] bool create() {
        job_ = Handle(CreateJobObjectW(nullptr, nullptr));
        if (!job_.valid()) {
            return false;
        }
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        return SetInformationJobObject(job_.get(), JobObjectExtendedLimitInformation,
                                       &limits, sizeof(limits)) != FALSE;
    }

    [[nodiscard]] bool add(const Handle &process) const {
        return AssignProcessToJobObject(job_.get(), process.get()) != FALSE;
    }

  private:
    Handle job_;
};

[[nodiscard]] std::optional<std::uint16_t>
wait_for_ready(const std::filesystem::path &ready_file, const Handle &worker) {
    const auto deadline = std::chrono::steady_clock::now() + kReadyTimeout;
    while (std::chrono::steady_clock::now() < deadline) {
        if (WaitForSingleObject(worker.get(), 0U) == WAIT_OBJECT_0) {
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

void terminate_process(const Handle &process) {
    if (!process.valid() || WaitForSingleObject(process.get(), 0U) == WAIT_OBJECT_0) {
        return;
    }
    if (WaitForSingleObject(process.get(), static_cast<DWORD>(kShutdownTimeout.count() *
                                                              1000)) == WAIT_OBJECT_0) {
        return;
    }
    TerminateProcess(process.get(), 1U);
    WaitForSingleObject(process.get(), INFINITE);
}

[[nodiscard]] int process_exit_code(const Handle &process) {
    DWORD code = 1U;
    return GetExitCodeProcess(process.get(), &code) ? static_cast<int>(code) : 1;
}

[[nodiscard]] int run_launcher(int argument_count, wchar_t **arguments) {
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
    auto cleanup_watchdog = launch_process(*launcher,
                                           {L"--macro-sim-cleanup-watchdog",
                                            std::to_wstring(GetCurrentProcessId()),
                                            runtime.path().native()},
                                           CREATE_NO_WINDOW);
    if (!cleanup_watchdog.valid()) {
        std::cerr << "Unable to start the launch cleanup watchdog.\n";
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
    const auto ready_utf8 = path_to_utf8(ready);
    const auto saves_utf8 = path_to_utf8(saves);
    const auto bootstrap_utf8 = path_to_utf8(bootstrap);
    const auto client_utf8 = path_to_utf8(client);
    if (!ready_utf8.has_value() || !saves_utf8.has_value() ||
        !bootstrap_utf8.has_value() || !client_utf8.has_value()) {
        std::cerr << "Unable to encode the launch channel paths.\n";
        return 1;
    }
    Json worker_bootstrap{
        {"ready_file", *ready_utf8},
        {"save_root", *saves_utf8},
        {"token", *token},
    };
    if (std::filesystem::is_regular_file(layout.artifact)) {
        const auto artifact_utf8 = path_to_utf8(layout.artifact);
        if (!artifact_utf8.has_value()) {
            return 1;
        }
        worker_bootstrap["rl_artifact"] = *artifact_utf8;
    }
    if (!write_private_file(bootstrap, worker_bootstrap.dump(), runtime.attributes())) {
        std::cerr << "Unable to initialize the native worker.\n";
        return 1;
    }

    ProcessJob job;
    if (!job.create()) {
        std::cerr << "Unable to create the desktop process group.\n";
        return 1;
    }
    auto worker = launch_process(layout.server, {L"--bootstrap", bootstrap.native()},
                                 CREATE_NO_WINDOW);
    if (!worker.valid() || !job.add(worker)) {
        std::cerr << "Unable to launch the native worker.\n";
        return 1;
    }
    const auto port = wait_for_ready(ready, worker);
    if (!port.has_value()) {
        terminate_process(worker);
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
    if (!write_private_file(client, client_bootstrap, runtime.attributes())) {
        terminate_process(worker);
        std::cerr << "Unable to configure the desktop client.\n";
        return 1;
    }

    std::vector<std::wstring> game_arguments;
    game_arguments.reserve(static_cast<std::size_t>(std::max(0, argument_count - 1)));
    for (int index = 1; index < argument_count; ++index) {
        game_arguments.emplace_back(arguments[index]);
    }
    auto game = launch_process(
        layout.game, game_arguments, 0U,
        std::pair{std::wstring(L"MACRO_SIM_CLIENT_BOOTSTRAP"), client.native()});
    if (!game.valid() || !job.add(game)) {
        terminate_process(worker);
        std::cerr << "Unable to launch the desktop client.\n";
        return 1;
    }

    const std::array<HANDLE, 2U> processes{game.get(), worker.get()};
    const auto result = WaitForMultipleObjects(static_cast<DWORD>(processes.size()),
                                               processes.data(), FALSE, INFINITE);
    if (result == WAIT_OBJECT_0 + 1U) {
        terminate_process(game);
        return 1;
    }
    if (result != WAIT_OBJECT_0) {
        terminate_process(game);
        terminate_process(worker);
        return 1;
    }
    const auto result_code = process_exit_code(game);
    terminate_process(worker);
    return result_code;
}

} // namespace

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    int argument_count = 0;
    auto **arguments = CommandLineToArgvW(GetCommandLineW(), &argument_count);
    if (arguments == nullptr) {
        return 1;
    }
    int result = 1;
    if (argument_count == 4 &&
        std::wstring_view(arguments[1]) == L"--macro-sim-cleanup-watchdog") {
        try {
            const auto parent = std::stoul(arguments[2]);
            result = cleanup_runtime_after_parent(static_cast<DWORD>(parent),
                                                  std::filesystem::path(arguments[3]));
        } catch (...) {
            result = 1;
        }
    } else {
        result = run_launcher(argument_count, arguments);
    }
    LocalFree(arguments);
    return result;
}
