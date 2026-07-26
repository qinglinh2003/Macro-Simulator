#ifndef MACRO_SIM_CONTROL_M11_ARTIFACT_HPP
#define MACRO_SIM_CONTROL_M11_ARTIFACT_HPP

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include "macro_sim/error.hpp"

namespace macro_sim::control {

struct NativePolicyArtifactBuilder;

inline constexpr std::size_t kM11MaximumArtifactBytes =
    1024U * 1024U * 1024U;
inline constexpr std::size_t kM11MaximumManifestBytes = 4U * 1024U * 1024U;
inline constexpr std::size_t kM11MaximumParameterBytes =
    512U * 1024U * 1024U;

struct NativePolicyArtifactInfo final {
    std::string inference_capability{
        "msrl_v1_deterministic_inference"};
    std::string artifact_sha256;
    std::string context_contract_hash;
    std::string action_contract_hash;
    std::string model_contract_hash;
    std::string metadata_json;
    std::vector<std::string> action_levers;
    std::size_t observation_dimension{0};
    std::size_t action_dimension{0};
    std::size_t layer_count{0};
    bool float32{true};
    bool deterministic{true};
    double temperature{1.0};

    bool operator==(const NativePolicyArtifactInfo &) const = default;
};

class NativePolicyArtifact final {
  public:
    enum class Activation : std::uint8_t {
        tanh = 0,
        relu = 1,
    };

    struct DenseLayer final {
        std::size_t inputs{0};
        std::size_t outputs{0};
        std::vector<double> weights;
        std::vector<double> biases;
    };

    NativePolicyArtifact(const NativePolicyArtifact &) = default;
    NativePolicyArtifact &operator=(const NativePolicyArtifact &) = default;
    NativePolicyArtifact(NativePolicyArtifact &&) noexcept = default;
    NativePolicyArtifact &operator=(NativePolicyArtifact &&) noexcept = default;
    ~NativePolicyArtifact() = default;

    [[nodiscard]] static Result<NativePolicyArtifact>
    load_file(const std::filesystem::path &path);
    [[nodiscard]] static Result<NativePolicyArtifact>
    load_bytes(std::span<const std::uint8_t> artifact);

    [[nodiscard]] const NativePolicyArtifactInfo &info() const noexcept {
        return info_;
    }
    [[nodiscard]] const std::vector<std::string> &feature_names() const noexcept {
        return feature_names_;
    }
    [[nodiscard]] std::span<const std::uint8_t>
    source_bytes() const noexcept {
        return source_bytes_;
    }
    [[nodiscard]] Result<std::vector<double>>
    normalized_input(std::span<const double> observation) const;
    [[nodiscard]] Result<std::vector<double>>
    logits(std::span<const double> observation) const;
    [[nodiscard]] Result<std::vector<double>>
    probabilities(std::span<const double> observation,
                  std::span<const std::uint8_t> action_mask) const;
    [[nodiscard]] Result<std::vector<std::uint32_t>>
    predict_codes(std::span<const double> observation,
                  std::span<const std::uint8_t> action_mask) const;

  private:
    friend struct NativePolicyArtifactBuilder;
    NativePolicyArtifact() = default;
    [[nodiscard]] Result<std::vector<double>>
    forward_float32(std::span<const double> observation) const;
    [[nodiscard]] Result<std::vector<double>>
    forward_float64(std::span<const double> observation) const;

    NativePolicyArtifactInfo info_;
    std::vector<std::uint8_t> source_bytes_;
    std::vector<std::string> feature_names_;
    std::vector<double> input_mean_;
    std::vector<double> input_scale_;
    std::vector<DenseLayer> layers_;
    Activation activation_{Activation::tanh};
    double input_clip_{20.0};
    bool has_input_clip_{true};
};

} // namespace macro_sim::control

#endif
