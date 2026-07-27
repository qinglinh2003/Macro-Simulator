#ifndef MACRO_SIM_CONTROL_M11_RELEASE_HPP
#define MACRO_SIM_CONTROL_M11_RELEASE_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include "macro_sim/control/m11_kernel.hpp"
#include "macro_sim/error.hpp"
#include "macro_sim/reporting/m10.hpp"
#include "macro_sim/simulation/m9.hpp"

namespace macro_sim::control {

enum class M11ObservationSource : std::uint8_t {
    economy = 0,
    world = 1,
    release = 2,
    shock = 3,
};

enum class M11ReleaseAggregation : std::uint8_t {
    last = 0,
    mean = 1,
    sum = 2,
};

enum class M11ReleaseAccess : std::uint8_t {
    public_access = 0,
    confidential = 1,
    operational = 2,
    oracle = 3,
};

struct M11ObservationFieldDescriptor final {
    std::string_view series_id;
    std::string_view source_key;
    M11ObservationSource source{M11ObservationSource::economy};
    M11ReleaseAggregation aggregation{M11ReleaseAggregation::last};
    std::uint32_t window_ticks{1U};
    std::uint32_t frequency_ticks{1U};
    std::uint32_t publication_lag_ticks{0U};
    std::uint32_t phase_offset_ticks{0U};
    M11ReleaseAccess access{M11ReleaseAccess::public_access};
    std::string_view roles;
    bool require_full_window{true};
    bool economy_indexed{false};
    std::optional<double> normalization_scale{};
    std::string_view unit;

    bool operator==(const M11ObservationFieldDescriptor &) const = default;
};

#include "macro_sim/control/generated_m11_observation_contract.inc"

struct M11ReleasedObservation final {
    std::string series_id;
    std::optional<double> value{};
    Tick observed_at{};
    Tick released_at{};
    std::uint32_t revision{0U};

    bool operator==(const M11ReleasedObservation &) const = default;
};

[[nodiscard]] std::span<const M11ObservationFieldDescriptor>
m11_observation_fields() noexcept;
[[nodiscard]] const M11ObservationFieldDescriptor *
find_m11_observation_field(std::string_view series_id) noexcept;
[[nodiscard]] bool m11_release_permitted(const M11ObservationFieldDescriptor &field,
                                         std::string_view role) noexcept;

class M11ReleaseService final {
  public:
    [[nodiscard]] Result<std::size_t>
    publish_due(const reporting::MetricPipeline &metrics,
                const simulation::M9World &world, Tick boundary,
                std::uint64_t source_event_sequence, M11ReleaseStream &stream) const;
    [[nodiscard]] Result<std::vector<M11ReleasedObservation>>
    observation(const M11ReleaseStream &stream, EconomyId economy, Tick as_of,
                std::string_view role) const;
    [[nodiscard]] std::vector<M11MetricSample>
    trigger_samples(const M11ReleaseStream &stream, EconomyId economy,
                    Tick as_of) const;

  private:
    [[nodiscard]] Result<std::optional<double>>
    aggregate(const reporting::MetricHistoryPage &history,
              const M11ObservationFieldDescriptor &field, EconomyId economy,
              Tick endpoint) const;
};

} // namespace macro_sim::control

#endif
