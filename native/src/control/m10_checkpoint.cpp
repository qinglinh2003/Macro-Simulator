#include "macro_sim/control/m10.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

namespace macro_sim::control {
namespace {

using Json = nlohmann::json;

constexpr std::array<std::uint8_t, 8> kMagic{
    'M', 'S', '1', '0', 'H', '0', '0', '1',
};
constexpr std::uint32_t kVersion = 1U;
constexpr std::size_t kDigestBytes = 32U;
constexpr std::size_t kMaximumMetadataBytes = 256U * 1024U * 1024U;
constexpr std::size_t kMaximumObjectiveBytes = 64U * 1024U * 1024U;

void append_u32(std::vector<std::uint8_t> &bytes, std::uint32_t value) {
    for (int shift = 24; shift >= 0; shift -= 8) {
        bytes.push_back(static_cast<std::uint8_t>(value >> shift));
    }
}

void append_u64(std::vector<std::uint8_t> &bytes, std::uint64_t value) {
    for (int shift = 56; shift >= 0; shift -= 8) {
        bytes.push_back(static_cast<std::uint8_t>(value >> shift));
    }
}

[[nodiscard]] bool read_u32(std::span<const std::uint8_t> bytes,
                            std::size_t &position,
                            std::uint32_t &value) noexcept {
    if (position > bytes.size() || bytes.size() - position < 4U) {
        return false;
    }
    value = 0U;
    for (int index = 0; index < 4; ++index) {
        value = static_cast<std::uint32_t>((value << 8U) | bytes[position++]);
    }
    return true;
}

[[nodiscard]] bool read_u64(std::span<const std::uint8_t> bytes,
                            std::size_t &position,
                            std::uint64_t &value) noexcept {
    if (position > bytes.size() || bytes.size() - position < 8U) {
        return false;
    }
    value = 0U;
    for (int index = 0; index < 8; ++index) {
        value = (value << 8U) | bytes[position++];
    }
    return true;
}

[[nodiscard]] Status corrupt() noexcept {
    return Status(ErrorCode::corrupt_input,
                  "M10 hybrid checkpoint is invalid");
}

[[nodiscard]] Json digest_json(const core::StateDigest &digest) {
    return std::vector<std::uint8_t>(digest.bytes.begin(), digest.bytes.end());
}

[[nodiscard]] core::StateDigest digest_from_json(const Json &input) {
    const auto bytes = input.get<std::vector<std::uint8_t>>();
    if (bytes.size() != 32U) {
        throw std::runtime_error("invalid digest");
    }
    core::StateDigest result;
    std::copy(bytes.begin(), bytes.end(), result.bytes.begin());
    return result;
}

[[nodiscard]] Json envelope_json(const CanonicalControllerEnvelope &value) {
    return Json{
        {"schema_version", value.schema_version},
        {"boundary", value.boundary.value()},
        {"policy_generation", value.policy_generation},
        {"event_sequence", value.event_sequence},
        {"release_cursor", value.release_cursor},
        {"decision_versions", value.decision_versions},
        {"effective_versions", value.effective_versions},
        {"canonical_payload", value.canonical_payload},
        {"hash", digest_json(value.hash)},
    };
}

[[nodiscard]] CanonicalControllerEnvelope
envelope_from_json(const Json &input) {
    CanonicalControllerEnvelope value;
    value.schema_version = input.at("schema_version").get<std::uint32_t>();
    value.boundary = Tick(input.at("boundary").get<std::uint64_t>());
    value.policy_generation =
        input.at("policy_generation").get<std::uint64_t>();
    value.event_sequence = input.at("event_sequence").get<std::uint64_t>();
    value.release_cursor = input.at("release_cursor").get<std::uint64_t>();
    value.decision_versions =
        input.at("decision_versions").get<std::vector<std::uint64_t>>();
    value.effective_versions =
        input.at("effective_versions").get<std::vector<std::uint64_t>>();
    value.canonical_payload =
        input.at("canonical_payload").get<std::vector<std::uint8_t>>();
    value.hash = digest_from_json(input.at("hash"));
    return value;
}

[[nodiscard]] Json frame_json(const reporting::MetricFrame &frame) {
    return Json{
        {"tick", frame.tick.value()},
        {"economy_count", frame.economy_count},
        {"values", frame.values},
        {"valid", frame.valid},
    };
}

[[nodiscard]] reporting::MetricFrame frame_from_json(const Json &input) {
    reporting::MetricFrame frame;
    frame.tick = Tick(input.at("tick").get<std::uint64_t>());
    frame.economy_count = input.at("economy_count").get<std::size_t>();
    frame.values = input.at("values").get<std::vector<double>>();
    frame.valid = input.at("valid").get<std::vector<std::uint8_t>>();
    return frame;
}

} // namespace

Result<std::vector<std::uint8_t>>
save_hybrid_checkpoint(const HybridControlledBridge &bridge,
                       std::span<const std::uint8_t> objective_envelope) {
    auto available = bridge.require_available();
    if (!available.ok()) {
        return available;
    }
    if (objective_envelope.size() > kMaximumObjectiveBytes) {
        return Status(ErrorCode::out_of_range,
                      "M10 objective envelope exceeds the supported size");
    }
    auto world = bridge.engine_.world().checkpoint();
    if (!world.ok()) {
        return world.status();
    }
    const auto &history = bridge.engine_.metrics().history();
    auto history_page =
        history.page(history.oldest_sequence(), history.size());
    if (!history_page.ok()) {
        return history_page.status();
    }

    Json metadata{
        {"envelope", envelope_json(bridge.envelope_)},
        {"history_capacity", history.capacity()},
        {"history_oldest_sequence", history.oldest_sequence()},
        {"history_next_sequence", history.next_sequence()},
        {"history", Json::array()},
        {"receipts", Json::array()},
    };
    for (const auto &frame : history_page.get_if()->frames) {
        metadata["history"].push_back(frame_json(frame));
    }
    for (const auto &receipt : bridge.receipts_) {
        metadata["receipts"].push_back(Json{
            {"operation_id", receipt.operation_id},
            {"request_hash", digest_json(receipt.request_hash)},
            {"prior_hash", digest_json(receipt.prior_hash)},
            {"result_hash", digest_json(receipt.result_hash)},
            {"boundary", receipt.boundary.value()},
            {"acknowledged", receipt.acknowledged},
        });
    }
    const std::string encoded = metadata.dump();
    if (encoded.size() > kMaximumMetadataBytes) {
        return Status(ErrorCode::out_of_range,
                      "M10 hybrid metadata exceeds the supported size");
    }

    std::vector<std::uint8_t> bytes;
    bytes.reserve(kMagic.size() + 4U + 8U + encoded.size() + 8U +
                  world.get_if()->size() + 8U + objective_envelope.size() +
                  kDigestBytes);
    bytes.insert(bytes.end(), kMagic.begin(), kMagic.end());
    append_u32(bytes, kVersion);
    append_u64(bytes, encoded.size());
    bytes.insert(bytes.end(), encoded.begin(), encoded.end());
    append_u64(bytes, world.get_if()->size());
    bytes.insert(bytes.end(), world.get_if()->begin(), world.get_if()->end());
    append_u64(bytes, objective_envelope.size());
    bytes.insert(bytes.end(), objective_envelope.begin(),
                 objective_envelope.end());
    const auto digest = core::sha256_digest(bytes);
    bytes.insert(bytes.end(), digest.bytes.begin(), digest.bytes.end());
    return bytes;
}

Result<LoadedHybridComposite>
load_hybrid_checkpoint(std::span<const std::uint8_t> checkpoint) {
    if (checkpoint.size() < kMagic.size() + 4U + 8U + 8U + 8U +
                                kDigestBytes ||
        !std::equal(kMagic.begin(), kMagic.end(), checkpoint.begin())) {
        return corrupt();
    }
    const auto payload = checkpoint.first(checkpoint.size() - kDigestBytes);
    const auto digest = core::sha256_digest(payload);
    if (!std::equal(digest.bytes.begin(), digest.bytes.end(),
                    checkpoint.end() -
                        static_cast<std::ptrdiff_t>(kDigestBytes))) {
        return corrupt();
    }
    std::size_t position = kMagic.size();
    std::uint32_t version = 0U;
    std::uint64_t metadata_size = 0U;
    if (!read_u32(payload, position, version) || version != kVersion ||
        !read_u64(payload, position, metadata_size) ||
        metadata_size > kMaximumMetadataBytes ||
        metadata_size > payload.size() - position) {
        return corrupt();
    }
    try {
        const std::string metadata_bytes(
            reinterpret_cast<const char *>(payload.data() + position),
            static_cast<std::size_t>(metadata_size));
        position += static_cast<std::size_t>(metadata_size);
        const auto metadata = Json::parse(metadata_bytes);

        std::uint64_t world_size = 0U;
        if (!read_u64(payload, position, world_size) ||
            world_size > payload.size() - position) {
            return corrupt();
        }
        auto world = simulation::M9World::restore(
            payload.subspan(position, static_cast<std::size_t>(world_size)));
        if (!world.ok()) {
            return corrupt();
        }
        position += static_cast<std::size_t>(world_size);

        std::uint64_t objective_size = 0U;
        if (!read_u64(payload, position, objective_size) ||
            objective_size > kMaximumObjectiveBytes ||
            objective_size > payload.size() - position ||
            position + objective_size != payload.size()) {
            return corrupt();
        }
        std::vector<std::uint8_t> objective(
            payload.begin() + static_cast<std::ptrdiff_t>(position),
            payload.end());

        const auto capacity =
            metadata.at("history_capacity").get<std::size_t>();
        if (capacity == 0U) {
            return corrupt();
        }
        std::vector<reporting::MetricFrame> frames;
        frames.reserve(metadata.at("history").size());
        for (const auto &item : metadata.at("history")) {
            frames.push_back(frame_from_json(item));
        }
        auto restored_history = reporting::MetricHistory::restore(
            world.get_if()->economy_count(),
            reporting::kM10PublicMetricCount, capacity,
            metadata.at("history_oldest_sequence").get<std::uint64_t>(),
            frames);
        if (!restored_history.ok()) {
            return corrupt();
        }
        auto history = std::move(*restored_history.get_if());
        if (history.oldest_sequence() !=
                metadata.at("history_oldest_sequence").get<std::uint64_t>() ||
            history.next_sequence() !=
                metadata.at("history_next_sequence").get<std::uint64_t>()) {
            return corrupt();
        }
        auto restored_pipeline =
            reporting::MetricPipeline::restore(std::move(history));
        if (!restored_pipeline.ok() ||
            restored_pipeline.get_if()->current().tick !=
                world.get_if()->tick()) {
            return corrupt();
        }

        EngineSession engine(std::move(*world.get_if()),
                             std::move(*restored_pipeline.get_if()));
        auto envelope = envelope_from_json(metadata.at("envelope"));
        auto bridge_result =
            HybridControlledBridge::create(std::move(engine),
                                           std::move(envelope));
        if (!bridge_result.ok()) {
            return corrupt();
        }
        auto bridge = std::move(*bridge_result.get_if());
        for (const auto &item : metadata.at("receipts")) {
            ControllerUpdateReceipt receipt;
            receipt.operation_id = item.at("operation_id").get<std::string>();
            receipt.request_hash = digest_from_json(item.at("request_hash"));
            receipt.prior_hash = digest_from_json(item.at("prior_hash"));
            receipt.result_hash = digest_from_json(item.at("result_hash"));
            receipt.boundary =
                Tick(item.at("boundary").get<std::uint64_t>());
            receipt.acknowledged = item.at("acknowledged").get<bool>();
            bridge.receipts_.push_back(std::move(receipt));
        }
        return LoadedHybridComposite{std::move(bridge),
                                     std::move(objective)};
    } catch (...) {
        return corrupt();
    }
}

} // namespace macro_sim::control
