#include <cassert>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <vector>

#include "macro_sim/control/m11_artifact.hpp"

namespace {

using macro_sim::ErrorCode;
using macro_sim::control::NativePolicyArtifact;

[[nodiscard]] std::filesystem::path artifact_path() {
    return std::filesystem::path(MACRO_SIM_SOURCE_DIR) /
           "macro_sim/rl/artifacts/fiscal_stabilization_v1.msrl";
}

void test_builtin_artifact_and_golden_vectors() {
    auto loaded = NativePolicyArtifact::load_file(artifact_path());
    assert(loaded.ok());
    auto artifact = std::move(*loaded.get_if());
    const auto &info = artifact.info();
    assert(
        info.artifact_sha256 ==
        "1cfc9b0f3b0d2f18ea9b54bbc4130ff447936cbb685aa14e01dd35ef28d107e6");
    assert(info.observation_dimension == 101U);
    assert(info.action_dimension == 1U);
    assert(info.layer_count == 3U);
    assert(info.float32);
    assert(info.deterministic);
    assert(info.inference_capability ==
           "msrl_v1_deterministic_inference");
    assert(info.temperature == 1.0);
    assert(artifact.feature_names().size() == 101U);

    std::vector<double> zeros(101U, 0.0);
    auto logits = artifact.logits(zeros);
    assert(logits.ok());
    const std::vector<double> expected{
        0.22628672420978546,
        0.07251507043838501,
        -0.20737363398075104,
    };
    assert(logits.get_if()->size() == expected.size());
    for (std::size_t index = 0; index < expected.size(); ++index) {
        assert(std::abs((*logits.get_if())[index] - expected[index]) < 2.0e-5);
    }
    const std::vector<std::uint8_t> all_allowed{1U, 1U, 1U};
    auto probabilities = artifact.probabilities(zeros, all_allowed);
    assert(probabilities.ok());
    const std::vector<double> expected_probabilities{
        0.3991059670350246,
        0.3422205249993660,
        0.2586735079656094,
    };
    for (std::size_t index = 0; index < expected_probabilities.size();
         ++index) {
        assert(std::abs(
                   (*probabilities.get_if())[index] -
                   expected_probabilities[index]) < 2.0e-12);
    }
    auto code = artifact.predict_codes(zeros, all_allowed);
    assert(code.ok());
    assert(*code.get_if() == std::vector<std::uint32_t>{0U});

    std::vector<double> ramp(101U);
    for (std::size_t index = 0; index < ramp.size(); ++index) {
        ramp[index] = -2.0 + 4.0 * static_cast<double>(index) / 100.0;
    }
    logits = artifact.logits(ramp);
    assert(logits.ok());
    const std::vector<double> ramp_expected{
        -0.0359668955206871,
        -0.015131252817809582,
        0.054109569638967514,
    };
    for (std::size_t index = 0; index < ramp_expected.size(); ++index) {
        assert(
            std::abs((*logits.get_if())[index] - ramp_expected[index]) <
            2.0e-5);
    }
    code = artifact.predict_codes(ramp, all_allowed);
    assert(code.ok());
    assert(*code.get_if() == std::vector<std::uint32_t>{2U});

    const std::vector<std::uint8_t> hold_only{0U, 1U, 0U};
    code = artifact.predict_codes(ramp, hold_only);
    assert(code.ok());
    assert(*code.get_if() == std::vector<std::uint32_t>{1U});
}

void test_corruption_and_shape_rejection() {
    std::ifstream stream(artifact_path(), std::ios::binary | std::ios::ate);
    assert(stream);
    const auto ending = stream.tellg();
    assert(ending > 0);
    std::vector<std::uint8_t> valid(static_cast<std::size_t>(ending));
    stream.seekg(0, std::ios::beg);
    stream.read(
        reinterpret_cast<char *>(valid.data()),
        static_cast<std::streamsize>(valid.size()));
    assert(stream);
    assert(!valid.empty());
    auto corrupt = valid;
    corrupt[corrupt.size() / 2U] ^= 0x1U;
    auto loaded = NativePolicyArtifact::load_bytes(corrupt);
    assert(!loaded.ok());
    assert(loaded.status().code() == ErrorCode::corrupt_input);

    loaded = NativePolicyArtifact::load_file(
        artifact_path().parent_path() / "absent.msrl");
    assert(!loaded.ok());
    assert(loaded.status().code() == ErrorCode::not_found);

    loaded = NativePolicyArtifact::load_bytes(valid);
    assert(loaded.ok());
    std::vector<double> short_observation(100U, 0.0);
    auto logits = loaded.get_if()->logits(short_observation);
    assert(!logits.ok());
    assert(logits.status().code() == ErrorCode::invalid_argument);
    std::vector<double> observation(101U, 0.0);
    auto code = loaded.get_if()->predict_codes(
        observation, std::vector<std::uint8_t>{1U, 1U});
    assert(!code.ok());
    assert(code.status().code() == ErrorCode::invalid_argument);
}

} // namespace

int main() {
    test_builtin_artifact_and_golden_vectors();
    test_corruption_and_shape_rejection();
    return 0;
}
