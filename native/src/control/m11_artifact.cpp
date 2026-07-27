#include "macro_sim/control/m11_artifact.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <limits>
#include <map>
#include <regex>
#include <set>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>
#include <zlib.h>

#include "macro_sim/core/digest.hpp"

namespace macro_sim::control {

struct NativePolicyArtifactBuilder final {
    [[nodiscard]] static NativePolicyArtifact
    build(NativePolicyArtifactInfo info, std::vector<std::string> feature_names,
          std::vector<double> input_mean, std::vector<double> input_scale,
          std::vector<NativePolicyArtifact::DenseLayer> layers,
          NativePolicyArtifact::Activation activation, double input_clip,
          bool has_input_clip) {
        NativePolicyArtifact output;
        output.info_ = std::move(info);
        output.feature_names_ = std::move(feature_names);
        output.input_mean_ = std::move(input_mean);
        output.input_scale_ = std::move(input_scale);
        output.layers_ = std::move(layers);
        output.activation_ = activation;
        output.input_clip_ = input_clip;
        output.has_input_clip_ = has_input_clip;
        return output;
    }
};

namespace {

using Json = nlohmann::json;

constexpr std::uint32_t kLocalHeader = 0x04034b50U;
constexpr std::uint32_t kCentralHeader = 0x02014b50U;
constexpr std::uint32_t kEndHeader = 0x06054b50U;
constexpr std::size_t kMaximumWeightsBytes = std::size_t{1024} * 1024U * 1024U;
constexpr std::size_t kMaximumTotalParameterBytes = std::size_t{1024} * 1024U * 1024U;

struct ZipMember final {
    std::string name;
    std::vector<std::uint8_t> bytes;
};

struct NumericArray final {
    bool float32{true};
    std::vector<std::size_t> shape;
    std::vector<double> values;
};

class UnsupportedArtifact final : public std::runtime_error {
  public:
    using std::runtime_error::runtime_error;
};

[[nodiscard]] std::uint16_t read_u16(std::span<const std::uint8_t> bytes,
                                     std::size_t offset) {
    if (offset > bytes.size() || bytes.size() - offset < 2U) {
        throw std::runtime_error("truncated integer");
    }
    return static_cast<std::uint16_t>(
        static_cast<std::uint16_t>(bytes[offset]) |
        static_cast<std::uint16_t>(static_cast<std::uint16_t>(bytes[offset + 1U])
                                   << 8U));
}

[[nodiscard]] std::uint32_t read_u32(std::span<const std::uint8_t> bytes,
                                     std::size_t offset) {
    if (offset > bytes.size() || bytes.size() - offset < 4U) {
        throw std::runtime_error("truncated integer");
    }
    return static_cast<std::uint32_t>(bytes[offset]) |
           (static_cast<std::uint32_t>(bytes[offset + 1U]) << 8U) |
           (static_cast<std::uint32_t>(bytes[offset + 2U]) << 16U) |
           (static_cast<std::uint32_t>(bytes[offset + 3U]) << 24U);
}

[[nodiscard]] std::size_t checked_add(std::size_t left, std::size_t right) {
    if (right > std::numeric_limits<std::size_t>::max() - left) {
        throw std::runtime_error("size overflow");
    }
    return left + right;
}

[[nodiscard]] std::size_t checked_product(const std::vector<std::size_t> &shape,
                                          std::size_t item_size) {
    std::size_t result = 1U;
    for (const auto dimension : shape) {
        if (dimension == 0U ||
            result > std::numeric_limits<std::size_t>::max() / dimension) {
            throw std::runtime_error("invalid array shape");
        }
        result *= dimension;
    }
    if (item_size != 0U &&
        result > std::numeric_limits<std::size_t>::max() / item_size) {
        throw std::runtime_error("array size overflow");
    }
    return result * item_size;
}

[[nodiscard]] std::vector<std::uint8_t>
inflate_raw(std::span<const std::uint8_t> compressed, std::size_t output_size) {
    if (compressed.size() > std::numeric_limits<uInt>::max() ||
        output_size > std::numeric_limits<uInt>::max()) {
        throw std::runtime_error("compressed member exceeds zlib limits");
    }
    std::vector<std::uint8_t> output(output_size);
    z_stream stream{};
    stream.next_in =
        const_cast<Bytef *>(reinterpret_cast<const Bytef *>(compressed.data()));
    stream.avail_in = static_cast<uInt>(compressed.size());
    stream.next_out = reinterpret_cast<Bytef *>(output.data());
    stream.avail_out = static_cast<uInt>(output.size());
    if (inflateInit2(&stream, -MAX_WBITS) != Z_OK) {
        throw std::runtime_error("cannot initialize deflate stream");
    }
    const auto result = inflate(&stream, Z_FINISH);
    const auto final_size = stream.total_out;
    inflateEnd(&stream);
    if (result != Z_STREAM_END || final_size != static_cast<uLong>(output_size)) {
        throw std::runtime_error("deflate member length differs");
    }
    return output;
}

[[nodiscard]] std::vector<ZipMember> read_zip(std::span<const std::uint8_t> bytes,
                                              std::size_t maximum_total) {
    if (bytes.size() < 22U || bytes.size() > maximum_total) {
        throw std::runtime_error("ZIP container size is invalid");
    }
    const auto search_floor = bytes.size() > 65'557U ? bytes.size() - 65'557U : 0U;
    std::size_t end_offset = std::numeric_limits<std::size_t>::max();
    for (std::size_t cursor = bytes.size() - 22U;; --cursor) {
        if (read_u32(bytes, cursor) == kEndHeader) {
            end_offset = cursor;
            break;
        }
        if (cursor == search_floor) {
            break;
        }
    }
    if (end_offset == std::numeric_limits<std::size_t>::max()) {
        throw std::runtime_error("ZIP end record is absent");
    }
    const auto disk = read_u16(bytes, end_offset + 4U);
    const auto central_disk = read_u16(bytes, end_offset + 6U);
    const auto disk_count = read_u16(bytes, end_offset + 8U);
    const auto member_count = read_u16(bytes, end_offset + 10U);
    const auto central_size = read_u32(bytes, end_offset + 12U);
    const auto central_offset = read_u32(bytes, end_offset + 16U);
    const auto comment_size = read_u16(bytes, end_offset + 20U);
    if (disk != 0U || central_disk != 0U || disk_count != member_count ||
        member_count == std::numeric_limits<std::uint16_t>::max() ||
        central_size == std::numeric_limits<std::uint32_t>::max() ||
        central_offset == std::numeric_limits<std::uint32_t>::max() ||
        checked_add(end_offset + 22U, comment_size) != bytes.size() ||
        checked_add(central_offset, central_size) != end_offset) {
        throw std::runtime_error("ZIP end record is unsupported");
    }

    std::vector<ZipMember> output;
    output.reserve(member_count);
    std::set<std::string> names;
    std::size_t cursor = central_offset;
    std::size_t total_uncompressed = 0U;
    for (std::size_t index = 0; index < member_count; ++index) {
        if (read_u32(bytes, cursor) != kCentralHeader) {
            throw std::runtime_error("ZIP central record is invalid");
        }
        const auto flags = read_u16(bytes, cursor + 8U);
        const auto method = read_u16(bytes, cursor + 10U);
        const auto expected_crc = read_u32(bytes, cursor + 16U);
        const auto compressed_size = read_u32(bytes, cursor + 20U);
        const auto uncompressed_size = read_u32(bytes, cursor + 24U);
        const auto name_size = read_u16(bytes, cursor + 28U);
        const auto extra_size = read_u16(bytes, cursor + 30U);
        const auto member_comment_size = read_u16(bytes, cursor + 32U);
        const auto member_disk = read_u16(bytes, cursor + 34U);
        const auto local_offset = read_u32(bytes, cursor + 42U);
        const auto record_size = checked_add(
            46U, checked_add(name_size, checked_add(extra_size, member_comment_size)));
        if (cursor > end_offset || record_size > end_offset - cursor ||
            (flags & 0x1U) != 0U || (method != 0U && method != 8U) ||
            member_disk != 0U ||
            compressed_size == std::numeric_limits<std::uint32_t>::max() ||
            uncompressed_size == std::numeric_limits<std::uint32_t>::max()) {
            throw std::runtime_error("ZIP member metadata is unsupported");
        }
        const auto name_offset = cursor + 46U;
        std::string name(reinterpret_cast<const char *>(bytes.data() + name_offset),
                         name_size);
        if (name.empty() || name.find('\0') != std::string::npos ||
            !names.insert(name).second) {
            throw std::runtime_error("ZIP member name is invalid");
        }
        if (read_u32(bytes, local_offset) != kLocalHeader) {
            throw std::runtime_error("ZIP local record is invalid");
        }
        const auto local_flags = read_u16(bytes, local_offset + 6U);
        const auto local_method = read_u16(bytes, local_offset + 8U);
        const auto local_name_size = read_u16(bytes, local_offset + 26U);
        const auto local_extra_size = read_u16(bytes, local_offset + 28U);
        const auto data_offset = checked_add(
            local_offset + 30U, checked_add(local_name_size, local_extra_size));
        const auto data_end = checked_add(data_offset, compressed_size);
        if (local_flags != flags || local_method != method ||
            local_name_size != name_size || data_end > bytes.size() ||
            std::string(
                reinterpret_cast<const char *>(bytes.data() + local_offset + 30U),
                local_name_size) != name) {
            throw std::runtime_error("ZIP local metadata differs");
        }
        total_uncompressed = checked_add(total_uncompressed, uncompressed_size);
        if (total_uncompressed > maximum_total) {
            throw std::runtime_error("ZIP uncompressed content is too large");
        }
        const auto compressed = bytes.subspan(data_offset, compressed_size);
        std::vector<std::uint8_t> content;
        if (method == 0U) {
            if (compressed_size != uncompressed_size) {
                throw std::runtime_error("stored ZIP member size differs");
            }
            content.assign(compressed.begin(), compressed.end());
        } else {
            content = inflate_raw(compressed, uncompressed_size);
        }
        const auto actual_crc = static_cast<std::uint32_t>(
            crc32(0U, reinterpret_cast<const Bytef *>(content.data()),
                  static_cast<uInt>(content.size())));
        if (actual_crc != expected_crc) {
            throw std::runtime_error("ZIP member CRC differs");
        }
        output.push_back({std::move(name), std::move(content)});
        cursor += record_size;
    }
    if (cursor != end_offset) {
        throw std::runtime_error("ZIP central directory has trailing data");
    }
    return output;
}

[[nodiscard]] bool exact_keys(const Json &value,
                              std::initializer_list<std::string_view> keys) {
    if (!value.is_object() || value.size() != keys.size()) {
        return false;
    }
    return std::all_of(keys.begin(), keys.end(), [&](std::string_view key) {
        return value.contains(std::string(key));
    });
}

[[nodiscard]] std::vector<std::size_t> json_shape(const Json &value) {
    if (!value.is_array()) {
        throw std::runtime_error("parameter shape is not an array");
    }
    std::vector<std::size_t> shape;
    shape.reserve(value.size());
    for (const auto &dimension : value) {
        if (!dimension.is_number_unsigned()) {
            throw std::runtime_error("parameter shape is invalid");
        }
        const auto checked = dimension.get<std::uint64_t>();
        if (checked == 0U || checked > std::numeric_limits<std::size_t>::max()) {
            throw std::runtime_error("parameter dimension is invalid");
        }
        shape.push_back(static_cast<std::size_t>(checked));
    }
    if (shape.empty()) {
        throw std::runtime_error("scalar parameters are unsupported");
    }
    return shape;
}

[[nodiscard]] NumericArray read_npy(std::span<const std::uint8_t> bytes,
                                    const std::vector<std::size_t> &expected_shape,
                                    bool expected_float32) {
    constexpr std::array<std::uint8_t, 6> magic{
        0x93U, 'N', 'U', 'M', 'P', 'Y',
    };
    if (bytes.size() < 10U || !std::equal(magic.begin(), magic.end(), bytes.begin())) {
        throw std::runtime_error("NPY magic differs");
    }
    const auto major = bytes[6U];
    std::size_t header_length = 0U;
    std::size_t header_offset = 0U;
    if (major == 1U) {
        header_length = read_u16(bytes, 8U);
        header_offset = 10U;
    } else if (major == 2U || major == 3U) {
        header_length = read_u32(bytes, 8U);
        header_offset = 12U;
    } else {
        throw std::runtime_error("NPY version is unsupported");
    }
    const auto data_offset = checked_add(header_offset, header_length);
    if (data_offset > bytes.size()) {
        throw std::runtime_error("NPY header is truncated");
    }
    const std::string header(
        reinterpret_cast<const char *>(bytes.data() + header_offset), header_length);
    std::smatch match;
    const std::regex descr_pattern(R"(['"]descr['"]\s*:\s*['"]([^'"]+)['"])");
    const std::regex order_pattern(R"(['"]fortran_order['"]\s*:\s*(True|False))");
    const std::regex shape_pattern(R"(['"]shape['"]\s*:\s*\(([^\)]*)\))");
    if (!std::regex_search(header, match, descr_pattern)) {
        throw std::runtime_error("NPY dtype is absent");
    }
    const auto descr = match[1].str();
    const bool float32 = descr == "<f4" || descr == "=f4" || descr == "|f4";
    const bool float64 = descr == "<f8" || descr == "=f8" || descr == "|f8";
    if ((!float32 && !float64) || float32 != expected_float32 ||
        std::endian::native != std::endian::little) {
        throw std::runtime_error("NPY dtype is unsupported");
    }
    if (!std::regex_search(header, match, order_pattern) || match[1].str() != "False") {
        throw std::runtime_error("Fortran-order NPY is unsupported");
    }
    if (!std::regex_search(header, match, shape_pattern)) {
        throw std::runtime_error("NPY shape is absent");
    }
    std::vector<std::size_t> shape;
    const auto shape_text = match[1].str();
    const std::regex dimension_pattern(R"((\d+))");
    for (auto iterator = std::sregex_iterator(shape_text.begin(), shape_text.end(),
                                              dimension_pattern);
         iterator != std::sregex_iterator(); ++iterator) {
        const auto raw = std::stoull((*iterator)[1].str());
        if (raw == 0U || raw > std::numeric_limits<std::size_t>::max()) {
            throw std::runtime_error("NPY dimension is invalid");
        }
        shape.push_back(static_cast<std::size_t>(raw));
    }
    if (shape != expected_shape) {
        throw std::runtime_error("NPY shape differs from manifest");
    }
    const auto item_size = float32 ? sizeof(float) : sizeof(double);
    const auto data_size = checked_product(shape, item_size);
    if (data_size > kM11MaximumParameterBytes ||
        checked_add(data_offset, data_size) != bytes.size()) {
        throw std::runtime_error("NPY data length differs");
    }
    const auto element_count = data_size / item_size;
    NumericArray output{float32, shape, {}};
    output.values.resize(element_count);
    for (std::size_t index = 0; index < element_count; ++index) {
        double value = 0.0;
        if (float32) {
            float raw = 0.0F;
            std::memcpy(&raw, bytes.data() + data_offset + index * sizeof(float),
                        sizeof(float));
            value = static_cast<double>(raw);
        } else {
            std::memcpy(&value, bytes.data() + data_offset + index * sizeof(double),
                        sizeof(double));
        }
        if (!std::isfinite(value)) {
            throw std::runtime_error("NPY contains a non-finite value");
        }
        output.values[index] = value;
    }
    return output;
}

[[nodiscard]] std::string digest(std::span<const std::uint8_t> bytes) {
    return core::sha256_digest(bytes).hex();
}

[[nodiscard]] std::string digest(std::string_view text) {
    return digest(std::span<const std::uint8_t>(
        reinterpret_cast<const std::uint8_t *>(text.data()), text.size()));
}

[[nodiscard]] const std::vector<std::uint8_t> &
member(const std::vector<ZipMember> &members, std::string_view name) {
    const auto found =
        std::find_if(members.begin(), members.end(),
                     [name](const ZipMember &item) { return item.name == name; });
    if (found == members.end()) {
        throw std::runtime_error("required ZIP member is absent");
    }
    return found->bytes;
}

[[nodiscard]] Result<NativePolicyArtifact>
parse_artifact(std::span<const std::uint8_t> artifact) {
    try {
        const auto outer = read_zip(artifact, kM11MaximumArtifactBytes);
        if (outer.size() != 2U) {
            throw std::runtime_error("artifact member count differs");
        }
        const std::set<std::string> outer_names{
            outer[0].name,
            outer[1].name,
        };
        if (outer_names != std::set<std::string>{"manifest.json", "weights.npz"}) {
            throw std::runtime_error("artifact members differ");
        }
        const auto &manifest_bytes = member(outer, "manifest.json");
        const auto &weights_bytes = member(outer, "weights.npz");
        if (manifest_bytes.size() > kM11MaximumManifestBytes ||
            weights_bytes.size() > kMaximumWeightsBytes) {
            throw std::runtime_error("artifact member exceeds its limit");
        }
        const std::string manifest_text(
            reinterpret_cast<const char *>(manifest_bytes.data()),
            manifest_bytes.size());
        const auto manifest = Json::parse(manifest_text);
        if (manifest.dump() != manifest_text ||
            !exact_keys(manifest, {"action_codec", "action_contract_hash",
                                   "artifact_format", "artifact_schema_version",
                                   "context_codec", "context_contract_hash", "metadata",
                                   "model", "model_contract_hash", "weights"}) ||
            manifest.at("artifact_schema_version") != 1 ||
            manifest.at("artifact_format") != "macro_sim_rl_policy_v1") {
            throw std::runtime_error("artifact manifest contract differs");
        }
        const auto &weights_spec = manifest.at("weights");
        if (!exact_keys(weights_spec, {"file", "sha256", "size_bytes"}) ||
            weights_spec.at("file") != "weights.npz" ||
            !weights_spec.at("size_bytes").is_number_unsigned() ||
            weights_spec.at("size_bytes").get<std::uint64_t>() !=
                weights_bytes.size() ||
            weights_spec.at("sha256") != digest(weights_bytes)) {
            throw std::runtime_error("artifact weight digest differs");
        }
        const auto context_text = manifest.at("context_codec").dump();
        const auto action_text = manifest.at("action_codec").dump();
        const auto model_text = manifest.at("model").dump();
        if (manifest.at("context_contract_hash") != digest(context_text) ||
            manifest.at("action_contract_hash") != digest(action_text) ||
            manifest.at("model_contract_hash") != digest(model_text)) {
            throw std::runtime_error("artifact contract digest differs");
        }

        const auto &context = manifest.at("context_codec");
        const auto &features = context.at("feature_names");
        if (!context.is_object() || !features.is_array() || features.empty()) {
            throw std::runtime_error("artifact context codec is invalid");
        }
        std::vector<std::string> feature_names;
        feature_names.reserve(features.size());
        std::set<std::string> unique_features;
        for (const auto &feature : features) {
            if (!feature.is_string()) {
                throw std::runtime_error("artifact feature name is invalid");
            }
            auto name = feature.get<std::string>();
            if (name.empty() || !unique_features.insert(name).second) {
                throw std::runtime_error("artifact feature names are invalid");
            }
            feature_names.push_back(std::move(name));
        }
        const auto &action = manifest.at("action_codec");
        const auto &dimensions = action.at("action_dimensions");
        if (!action.is_object() || !dimensions.is_array() || dimensions.empty()) {
            throw std::runtime_error("artifact action codec is invalid");
        }
        std::vector<std::string> action_levers;
        action_levers.reserve(dimensions.size());
        std::set<std::string> unique_action_levers;
        for (const auto &dimension : dimensions) {
            if (!dimension.is_array() || dimension.size() != 2U ||
                !dimension[0U].is_string() || !dimension[1U].is_null()) {
                throw UnsupportedArtifact(
                    "targeted action dimensions are not supported");
            }
            auto lever = dimension[0U].get<std::string>();
            if (lever.empty() || !unique_action_levers.insert(lever).second) {
                throw std::runtime_error("artifact action dimensions are invalid");
            }
            action_levers.push_back(std::move(lever));
        }

        const auto &model = manifest.at("model");
        if (!exact_keys(model, {"action_contract_hash", "activation", "architecture",
                                "context_contract_hash", "deterministic", "dtype",
                                "input_clip", "layer_count", "parameter_specs",
                                "schema_version", "seed", "temperature"}) ||
            model.at("schema_version") != 1 ||
            model.at("architecture") != "numpy_mlp_categorical_v1" ||
            model.at("context_contract_hash") != manifest.at("context_contract_hash") ||
            model.at("action_contract_hash") != manifest.at("action_contract_hash") ||
            !model.at("deterministic").is_boolean() ||
            !model.at("layer_count").is_number_unsigned() ||
            !model.at("temperature").is_number() ||
            model.at("temperature").get<double>() <= 0.0) {
            throw std::runtime_error("artifact model contract is invalid");
        }
        const auto dtype = model.at("dtype").get<std::string>();
        const bool float32 = dtype == "float32";
        if (!float32 && dtype != "float64") {
            throw std::runtime_error("artifact model dtype is unsupported");
        }
        const auto layer_count = model.at("layer_count").get<std::size_t>();
        if (layer_count == 0U || layer_count > 64U) {
            throw std::runtime_error("artifact model layer count is invalid");
        }
        const auto activation = model.at("activation").get<std::string>();
        if (activation != "tanh" && activation != "relu") {
            throw std::runtime_error("artifact activation is unsupported");
        }

        const auto &parameter_specs = model.at("parameter_specs");
        if (!parameter_specs.is_object() ||
            parameter_specs.size() != 2U + layer_count * 2U) {
            throw std::runtime_error("artifact parameter set differs");
        }
        std::map<std::string, std::vector<std::size_t>> expected;
        std::size_t total_parameter_bytes = 0U;
        for (const auto &[name, spec] : parameter_specs.items()) {
            if (!exact_keys(spec, {"dtype", "shape"}) || spec.at("dtype") != dtype) {
                throw std::runtime_error("artifact parameter spec differs");
            }
            auto shape = json_shape(spec.at("shape"));
            const auto bytes =
                checked_product(shape, float32 ? sizeof(float) : sizeof(double));
            total_parameter_bytes = checked_add(total_parameter_bytes, bytes);
            if (bytes > kM11MaximumParameterBytes ||
                total_parameter_bytes > kMaximumTotalParameterBytes) {
                throw std::runtime_error("artifact parameters exceed limits");
            }
            expected.emplace(name, std::move(shape));
        }
        if (!expected.contains("input_mean") || !expected.contains("input_scale")) {
            throw std::runtime_error("artifact input normalization is absent");
        }
        for (std::size_t index = 0; index < layer_count; ++index) {
            if (!expected.contains("layer_" + std::to_string(index) + "_weight") ||
                !expected.contains("layer_" + std::to_string(index) + "_bias")) {
                throw std::runtime_error("artifact dense layer is incomplete");
            }
        }

        const auto npz = read_zip(weights_bytes, kMaximumWeightsBytes);
        if (npz.size() != expected.size()) {
            throw std::runtime_error("NPZ member count differs");
        }
        std::map<std::string, NumericArray> arrays;
        for (const auto &item : npz) {
            if (item.name.size() <= 4U ||
                item.name.substr(item.name.size() - 4U) != ".npy") {
                throw std::runtime_error("NPZ member name is invalid");
            }
            const auto name = item.name.substr(0U, item.name.size() - 4U);
            const auto specification = expected.find(name);
            if (specification == expected.end() || arrays.contains(name)) {
                throw std::runtime_error("NPZ parameter differs");
            }
            arrays.emplace(name, read_npy(item.bytes, specification->second, float32));
        }

        const auto deterministic = model.at("deterministic").get<bool>();
        if (!deterministic) {
            throw UnsupportedArtifact("stochastic msrl v1 inference is not portable");
        }
        const auto temperature = model.at("temperature").get<double>();
        if (!std::isfinite(temperature)) {
            throw std::runtime_error("artifact temperature is invalid");
        }
        NativePolicyArtifactInfo info{
            "msrl_v1_deterministic_inference",
            digest(artifact),
            manifest.at("context_contract_hash").get<std::string>(),
            manifest.at("action_contract_hash").get<std::string>(),
            manifest.at("model_contract_hash").get<std::string>(),
            manifest.at("metadata").dump(),
            std::move(action_levers),
            feature_names.size(),
            dimensions.size(),
            layer_count,
            float32,
            deterministic,
            temperature,
        };
        auto input_mean = arrays.at("input_mean").values;
        auto input_scale = arrays.at("input_scale").values;
        if (input_mean.size() != info.observation_dimension ||
            input_scale.size() != info.observation_dimension ||
            std::any_of(input_scale.begin(), input_scale.end(),
                        [](double value) { return value <= 0.0; })) {
            throw std::runtime_error("artifact input normalization differs");
        }
        const auto native_activation = activation == "tanh"
                                           ? NativePolicyArtifact::Activation::tanh
                                           : NativePolicyArtifact::Activation::relu;
        bool has_input_clip = true;
        double input_clip = 20.0;
        if (model.at("input_clip").is_null()) {
            has_input_clip = false;
        } else if (model.at("input_clip").is_number() &&
                   std::isfinite(model.at("input_clip").get<double>()) &&
                   model.at("input_clip").get<double>() > 0.0) {
            input_clip = model.at("input_clip").get<double>();
        } else {
            throw std::runtime_error("artifact input clip is invalid");
        }

        std::size_t previous = info.observation_dimension;
        std::vector<NativePolicyArtifact::DenseLayer> layers;
        layers.reserve(layer_count);
        for (std::size_t index = 0; index < layer_count; ++index) {
            const auto prefix = "layer_" + std::to_string(index);
            const auto &weight = arrays.at(prefix + "_weight");
            const auto &bias = arrays.at(prefix + "_bias");
            if (weight.shape.size() != 2U || bias.shape.size() != 1U ||
                weight.shape[1U] != previous || weight.shape[0U] != bias.shape[0U]) {
                throw std::runtime_error("artifact dense shape is invalid");
            }
            layers.push_back({
                weight.shape[1U],
                weight.shape[0U],
                weight.values,
                bias.values,
            });
            previous = weight.shape[0U];
        }
        if (previous != info.action_dimension * 3U) {
            throw std::runtime_error("artifact output dimension differs");
        }
        return NativePolicyArtifactBuilder::build(
            std::move(info), std::move(feature_names), std::move(input_mean),
            std::move(input_scale), std::move(layers), native_activation, input_clip,
            has_input_clip);
    } catch (const UnsupportedArtifact &) {
        return Status(ErrorCode::unsupported,
                      "M11 artifact requires unsupported inference");
    } catch (const std::bad_alloc &) {
        return Status(ErrorCode::allocation_failure, "M11 artifact allocation failed");
    } catch (const std::exception &) {
        return Status(ErrorCode::corrupt_input, "M11 artifact validation failed");
    }
}

template <typename Scalar>
[[nodiscard]] Result<std::vector<Scalar>>
normalize(std::span<const double> observation, std::size_t expected_dimension,
          const std::vector<double> &mean, const std::vector<double> &scale,
          bool has_clip, double input_clip) {
    if (observation.size() != expected_dimension) {
        return Status(ErrorCode::invalid_argument, "M11 observation dimension differs");
    }
    std::vector<Scalar> values(observation.size());
    for (std::size_t index = 0; index < observation.size(); ++index) {
        if (!std::isfinite(observation[index])) {
            return Status(ErrorCode::invalid_argument,
                          "M11 observation contains a non-finite value");
        }
        auto value = static_cast<Scalar>((static_cast<Scalar>(observation[index]) -
                                          static_cast<Scalar>(mean[index])) /
                                         static_cast<Scalar>(scale[index]));
        if (has_clip) {
            const auto bound = static_cast<Scalar>(input_clip);
            value = std::clamp(value, -bound, bound);
        }
        values[index] = value;
    }
    return values;
}

template <typename Scalar>
[[nodiscard]] Result<std::vector<double>>
forward(const NativePolicyArtifact &artifact, std::span<const double> observation,
        const std::vector<double> &mean, const std::vector<double> &scale,
        const std::vector<NativePolicyArtifact::DenseLayer> &layers,
        NativePolicyArtifact::Activation activation, bool has_clip, double input_clip) {
    auto normalized =
        normalize<Scalar>(observation, artifact.info().observation_dimension, mean,
                          scale, has_clip, input_clip);
    if (!normalized.ok()) {
        return normalized.status();
    }
    auto values = std::move(*normalized.get_if());
    for (std::size_t layer_index = 0; layer_index < layers.size(); ++layer_index) {
        const auto &layer = layers[layer_index];
        std::vector<Scalar> next(layer.outputs);
        for (std::size_t row = 0; row < layer.outputs; ++row) {
            auto accumulator = static_cast<Scalar>(layer.biases[row]);
            const auto offset = row * layer.inputs;
            for (std::size_t column = 0; column < layer.inputs; ++column) {
                accumulator += static_cast<Scalar>(layer.weights[offset + column]) *
                               values[column];
            }
            if (layer_index + 1U != layers.size()) {
                if (activation == NativePolicyArtifact::Activation::tanh) {
                    accumulator = std::tanh(accumulator);
                } else {
                    accumulator = std::max(Scalar{0}, accumulator);
                }
            }
            if (!std::isfinite(accumulator)) {
                return Status(ErrorCode::invariant_violation,
                              "M11 model produced a non-finite value");
            }
            next[row] = accumulator;
        }
        values = std::move(next);
    }
    std::vector<double> output(values.size());
    std::transform(values.begin(), values.end(), output.begin(),
                   [](Scalar value) { return static_cast<double>(value); });
    return output;
}

} // namespace

Result<NativePolicyArtifact>
NativePolicyArtifact::load_file(const std::filesystem::path &path) {
    try {
        std::ifstream stream(path, std::ios::binary | std::ios::ate);
        if (!stream) {
            return Status(ErrorCode::not_found, "M11 artifact file was not found");
        }
        const auto ending = stream.tellg();
        if (ending < 0 ||
            static_cast<std::uint64_t>(ending) > kM11MaximumArtifactBytes) {
            return Status(ErrorCode::out_of_range, "M11 artifact file is too large");
        }
        std::vector<std::uint8_t> bytes(static_cast<std::size_t>(ending));
        stream.seekg(0, std::ios::beg);
        if (!bytes.empty() &&
            !stream.read(reinterpret_cast<char *>(bytes.data()),
                         static_cast<std::streamsize>(bytes.size()))) {
            return Status(ErrorCode::corrupt_input,
                          "M11 artifact file could not be read");
        }
        return load_bytes(bytes);
    } catch (const std::bad_alloc &) {
        return Status(ErrorCode::allocation_failure, "M11 artifact allocation failed");
    }
}

Result<NativePolicyArtifact>
NativePolicyArtifact::load_bytes(std::span<const std::uint8_t> artifact) {
    if (artifact.empty() || artifact.size() > kM11MaximumArtifactBytes) {
        return Status(ErrorCode::out_of_range, "M11 artifact byte length is invalid");
    }
    auto parsed = parse_artifact(artifact);
    if (parsed.ok()) {
        parsed.get_if()->source_bytes_.assign(artifact.begin(), artifact.end());
    }
    return parsed;
}

Result<std::vector<double>>
NativePolicyArtifact::forward_float32(std::span<const double> observation) const {
    return forward<float>(*this, observation, input_mean_, input_scale_, layers_,
                          activation_, has_input_clip_, input_clip_);
}

Result<std::vector<double>>
NativePolicyArtifact::forward_float64(std::span<const double> observation) const {
    return forward<double>(*this, observation, input_mean_, input_scale_, layers_,
                           activation_, has_input_clip_, input_clip_);
}

Result<std::vector<double>>
NativePolicyArtifact::logits(std::span<const double> observation) const {
    return info_.float32 ? forward_float32(observation) : forward_float64(observation);
}

Result<std::vector<double>>
NativePolicyArtifact::normalized_input(std::span<const double> observation) const {
    if (info_.float32) {
        auto calculated =
            normalize<float>(observation, info_.observation_dimension, input_mean_,
                             input_scale_, has_input_clip_, input_clip_);
        if (!calculated.ok()) {
            return calculated.status();
        }
        std::vector<double> result(calculated.get_if()->size());
        std::transform(calculated.get_if()->begin(), calculated.get_if()->end(),
                       result.begin(),
                       [](float value) { return static_cast<double>(value); });
        return result;
    }
    return normalize<double>(observation, info_.observation_dimension, input_mean_,
                             input_scale_, has_input_clip_, input_clip_);
}

Result<std::vector<double>>
NativePolicyArtifact::probabilities(std::span<const double> observation,
                                    std::span<const std::uint8_t> action_mask) const {
    if (action_mask.size() != info_.action_dimension * 3U) {
        return Status(ErrorCode::invalid_argument, "M11 action mask dimension differs");
    }
    auto calculated = logits(observation);
    if (!calculated.ok()) {
        return calculated.status();
    }
    const auto &values = *calculated.get_if();
    std::vector<double> result(values.size(), 0.0);
    for (std::size_t dimension = 0; dimension < info_.action_dimension; ++dimension) {
        bool permitted = false;
        double maximum = -std::numeric_limits<double>::infinity();
        for (std::uint32_t code = 0U; code < 3U; ++code) {
            const auto index = dimension * 3U + code;
            if (action_mask[index] > 1U) {
                return Status(ErrorCode::invalid_argument,
                              "M11 action mask value is invalid");
            }
            if (action_mask[index] == 0U) {
                continue;
            }
            permitted = true;
            maximum = std::max(maximum, values[index] / info_.temperature);
        }
        if (!permitted) {
            return Status(ErrorCode::contract_violation,
                          "M11 action dimension has no permitted code");
        }
        double total = 0.0;
        for (std::uint32_t code = 0U; code < 3U; ++code) {
            const auto index = dimension * 3U + code;
            if (action_mask[index] == 0U) {
                continue;
            }
            result[index] = std::exp(values[index] / info_.temperature - maximum);
            total += result[index];
        }
        if (!std::isfinite(total) || total <= 0.0) {
            return Status(ErrorCode::invariant_violation,
                          "M11 model produced an invalid distribution");
        }
        for (std::uint32_t code = 0U; code < 3U; ++code) {
            const auto index = dimension * 3U + code;
            result[index] /= total;
            if (!std::isfinite(result[index])) {
                return Status(ErrorCode::invariant_violation,
                              "M11 model produced a non-finite probability");
            }
        }
    }
    return result;
}

Result<std::vector<std::uint32_t>>
NativePolicyArtifact::predict_codes(std::span<const double> observation,
                                    std::span<const std::uint8_t> action_mask) const {
    auto calculated = probabilities(observation, action_mask);
    if (!calculated.ok()) {
        return calculated.status();
    }
    const auto &values = *calculated.get_if();
    std::vector<std::uint32_t> result(info_.action_dimension);
    for (std::size_t dimension = 0; dimension < info_.action_dimension; ++dimension) {
        bool permitted = false;
        std::uint32_t selected = 0U;
        double selected_value = -std::numeric_limits<double>::infinity();
        for (std::uint32_t code = 0U; code < 3U; ++code) {
            const auto index = dimension * 3U + code;
            if (action_mask[index] == 0U) {
                continue;
            }
            if (!permitted || values[index] > selected_value) {
                permitted = true;
                selected = code;
                selected_value = values[index];
            }
        }
        if (!permitted) {
            return Status(ErrorCode::contract_violation,
                          "M11 action dimension has no permitted code");
        }
        result[dimension] = selected;
    }
    return result;
}

} // namespace macro_sim::control
