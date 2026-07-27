#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include "macro_sim/c_api.h"
#include "macro_sim/control/m11_artifact.hpp"
#include "macro_sim/control/m11_session.hpp"
#include "macro_sim/core/checkpoint.hpp"
#include "macro_sim/desktop/m11_protocol.hpp"

namespace {

using namespace macro_sim;
using namespace macro_sim::control;
using namespace macro_sim::desktop;

inline constexpr std::string_view kToken = "0123456789abcdef0123456789abcdef"
                                           "0123456789abcdef0123456789abcdef";

[[nodiscard]] std::vector<std::uint8_t> read_bytes(const std::filesystem::path &path) {
    std::ifstream stream(path, std::ios::binary);
    assert(stream);
    return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

class ParserFuzzTarget final {
  public:
    ParserFuzzTarget() : protocol_(make_protocol()) {}

    void exercise(std::span<const std::uint8_t> bytes) {
        static constexpr char kEmpty = '\0';
        const auto *characters =
            bytes.empty() ? &kEmpty : reinterpret_cast<const char *>(bytes.data());
        const std::string_view frame(characters, bytes.size());
        static_cast<void>(protocol_.handle_frame(frame));
        static_cast<void>(NativePolicyArtifact::load_bytes(bytes));
        static_cast<void>(load_m11_checkpoint(bytes));
        static_cast<void>(core::load_checkpoint(bytes));

        macro_sim_scalar scalar{};
        scalar.kind = MACRO_SIM_SCALAR_STRING;
        scalar.string_value = characters;
        scalar.string_size = bytes.size();
        macro_sim_validation_code validation = MACRO_SIM_VALIDATION_OK;
        static_cast<void>(
            macro_sim_validate_scalar(characters, bytes.size(), &scalar, &validation));
    }

  private:
    [[nodiscard]] static M11ProtocolWorker make_protocol() {
        M11ProtocolOptions options;
        options.capability_token = std::string(kToken);
        auto result = M11ProtocolWorker::create(std::move(options));
        assert(result.ok());
        return std::move(*result.get_if());
    }

    M11ProtocolWorker protocol_;
};

void exercise_prefixes(ParserFuzzTarget &target,
                       const std::vector<std::uint8_t> &seed) {
    const auto prefix_count = std::min<std::size_t>(seed.size(), 256U);
    for (std::size_t size = 0; size <= prefix_count; ++size) {
        target.exercise(std::span(seed.data(), size));
    }
}

void exercise_mutations(ParserFuzzTarget &target,
                        const std::vector<std::uint8_t> &seed) {
    const auto mutation_count = std::min<std::size_t>(seed.size(), 512U);
    auto mutated = seed;
    for (std::size_t index = 0; index < mutation_count; index += 2U) {
        mutated[index] ^= static_cast<std::uint8_t>(1U << (index % 8U));
        target.exercise(mutated);
        mutated[index] = seed[index];
    }
}

void exercise_generated(ParserFuzzTarget &target) {
    std::uint64_t state = 0x5a17c9e4d2038b6fULL;
    for (std::size_t case_index = 0; case_index < 512U; ++case_index) {
        state ^= state << 13U;
        state ^= state >> 7U;
        state ^= state << 17U;
        const auto size = static_cast<std::size_t>(state % 4097U);
        std::vector<std::uint8_t> bytes(size);
        for (auto &value : bytes) {
            state ^= state << 13U;
            state ^= state >> 7U;
            state ^= state << 17U;
            value = static_cast<std::uint8_t>(state);
        }
        target.exercise(bytes);
    }
}

} // namespace

int main() {
    ParserFuzzTarget target;
    const std::string hello =
        R"JSON({"protocol_version":5,"request_id":"fuzz","connection_id":"fuzz-client","sequence":1,"token":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","command":"hello"})JSON";
    const std::vector<std::uint8_t> protocol_seed(hello.begin(), hello.end());
    const auto artifact_seed =
        read_bytes(std::filesystem::path(MACRO_SIM_SOURCE_DIR) /
                   "macro_sim/rl/artifacts/fiscal_stabilization_v1.msrl");

    exercise_prefixes(target, protocol_seed);
    exercise_mutations(target, protocol_seed);
    exercise_prefixes(target, artifact_seed);
    exercise_mutations(target, artifact_seed);
    exercise_generated(target);
    return 0;
}
