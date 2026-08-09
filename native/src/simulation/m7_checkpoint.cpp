#include "macro_sim/simulation/m7_checkpoint.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include "macro_sim/simulation/m6_checkpoint.hpp"

namespace macro_sim::simulation {
namespace {

using Json = nlohmann::json;

constexpr std::array<std::uint8_t, 8> kMagic{
    'M', 'S', 'M', '7', 'C', 'P', '0', '2',
};
constexpr std::size_t kDigestBytes = 32;
constexpr std::size_t kWealthQuintiles = 5U;
constexpr std::size_t kMaximumCheckpointBytes = 512U * 1024U * 1024U;

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

[[nodiscard]] bool read_u32(std::span<const std::uint8_t> bytes, std::size_t &position,
                            std::uint32_t &value) noexcept {
    if (position > bytes.size() || bytes.size() - position < 4U) {
        return false;
    }
    value = 0;
    for (int index = 0; index < 4; ++index) {
        value = static_cast<std::uint32_t>((value << 8U) | bytes[position++]);
    }
    return true;
}

[[nodiscard]] bool read_u64(std::span<const std::uint8_t> bytes, std::size_t &position,
                            std::uint64_t &value) noexcept {
    if (position > bytes.size() || bytes.size() - position < 8U) {
        return false;
    }
    value = 0;
    for (int index = 0; index < 8; ++index) {
        value = (value << 8U) | bytes[position++];
    }
    return true;
}

[[nodiscard]] Status corrupt(const char *message) noexcept {
    return Status(ErrorCode::corrupt_input, message);
}

[[nodiscard]] Json encode_vital(const algorithms::VitalRates &value) {
    return Json::array({
        value.makeham_a,
        value.gompertz_b,
        value.gompertz_theta,
        value.infant_extra,
        value.total_fertility_rate,
        value.fertility_peak_age,
        value.fertility_width,
        value.sex_ratio_at_birth,
        value.maximum_age,
        value.interval,
    });
}

[[nodiscard]] algorithms::VitalRates decode_vital(const Json &row) {
    if (!row.is_array() || row.size() != 10U) {
        throw std::runtime_error("invalid M7 vital rates");
    }
    algorithms::VitalRates value;
    std::size_t index = 0;
    value.makeham_a = row[index++].get<double>();
    value.gompertz_b = row[index++].get<double>();
    value.gompertz_theta = row[index++].get<double>();
    value.infant_extra = row[index++].get<double>();
    value.total_fertility_rate = row[index++].get<double>();
    value.fertility_peak_age = row[index++].get<double>();
    value.fertility_width = row[index++].get<double>();
    value.sex_ratio_at_birth = row[index++].get<double>();
    value.maximum_age = row[index++].get<std::uint32_t>();
    value.interval = row[index++].get<double>();
    return value;
}

[[nodiscard]] Json encode_marriage_rules(const core::MarriageRules &value) {
    return Json::array({
        value.minimum_age,
        value.maximum_age,
        value.maximum_age_gap,
        value.preferred_age_gap,
        value.age_gap_penalty,
        value.assortativity,
        value.forbid_same_household,
        value.forbid_close_kin,
    });
}

[[nodiscard]] core::MarriageRules decode_marriage_rules(const Json &row) {
    if (!row.is_array() || row.size() != 8U) {
        throw std::runtime_error("invalid M7 marriage rules");
    }
    core::MarriageRules value;
    std::size_t index = 0;
    value.minimum_age = row[index++].get<std::uint32_t>();
    value.maximum_age = row[index++].get<std::uint32_t>();
    value.maximum_age_gap = row[index++].get<std::uint32_t>();
    value.preferred_age_gap = row[index++].get<double>();
    value.age_gap_penalty = row[index++].get<double>();
    value.assortativity = row[index++].get<double>();
    value.forbid_same_household = row[index++].get<bool>();
    value.forbid_close_kin = row[index++].get<bool>();
    return value;
}

[[nodiscard]] Json encode_rules(const M7Rules &value) {
    Json output;
    output["vital"] = encode_vital(value.vital_rates);
    output["marriage_rules"] = encode_marriage_rules(value.marriage_rules);
    output["genesis_union_target_profile"] = Json::array({
        value.genesis_union_target_profile.enabled,
        value.genesis_union_target_profile.shares[0],
        value.genesis_union_target_profile.shares[1],
        value.genesis_union_target_profile.shares[2],
        value.genesis_union_target_profile.shares[3],
        value.genesis_union_target_profile.shares[4],
        value.genesis_union_target_profile.shares[5],
    });
    output["social_union_target_profile"] = Json::array({
        value.social_union_target_profile.enabled,
        value.social_union_target_profile.shares[0],
        value.social_union_target_profile.shares[1],
        value.social_union_target_profile.shares[2],
        value.social_union_target_profile.shares[3],
        value.social_union_target_profile.shares[4],
        value.social_union_target_profile.shares[5],
    });
    output["values"] = Json::array({
        value.working_age,
        value.retirement_age,
        value.beneficial_ownership,
        value.estates,
        value.fertility,
        value.mortality,
        value.persistent_labor,
        value.fractional_hours,
        value.second_jobs,
        value.suspensions,
        value.annual_churn,
        value.firing_adjustment,
        value.layoff_band,
        value.target_smoothing,
        value.suspension_timeout_days,
        value.suspension_quit_discount,
        value.frictional_search,
        value.search_intensity,
        value.relationship_wages,
        value.job_ladder,
        value.ladder_search_intensity,
        value.ladder_premium,
        value.person_efficiency,
        value.efficiency_sigma,
        value.genesis_employment_rate,
        value.participation_margin,
        value.age_participation,
        value.young_participation_rate,
        value.prime_participation_rate,
        value.older_participation_rate,
        value.reservation_markup,
        value.welfare_quit_hazard,
        value.family_transfers,
        value.family_transfer_buffer,
        value.relationships,
        value.marriage,
        value.divorce,
        value.household_lifecycle,
        value.lifecycle_consumption,
        value.lifecycle_income_propensity,
        value.lifecycle_wealth_draw_propensity,
        value.leaving_home,
        value.leave_home_min_age,
        value.leave_home_peak_end_age,
        value.annual_leave_rate_peak,
        value.annual_leave_rate_late,
        value.marriage_interval_days,
        value.annual_marriage_rate,
        value.annual_divorce_rate,
        value.mortality_rank_gradient,
        value.fertility_rank_gradient,
        value.stratification_multiplier_minimum,
        value.stratification_multiplier_maximum,
        value.demographic_feedback_burnin_years,
        value.demographic_signal_halflife_years,
        value.fertility_income_elasticity,
        value.fertility_multiplier_minimum,
        value.fertility_multiplier_maximum,
        value.mortality_income_elasticity,
        value.mortality_multiplier_minimum,
        value.mortality_multiplier_maximum,
        value.genesis_parent_minimum_age_gap,
        value.genesis_parent_maximum_age_gap,
        value.genesis_ideal_parent_age_gap,
        value.genesis_parent_age_gap_stddev,
        value.genesis_spouse_maximum_age_gap,
        value.genesis_spouse_age_gap_stddev,
        value.genesis_target_partnered_adult_share,
        value.genesis_two_parent_assignment_share,
        value.genesis_maximum_children_per_parent,
        value.genesis_maximum_children_per_household,
        value.marriage_peak_age,
        value.marriage_age_width,
        value.marriage_age_gap_stddev,
        value.marriage_acceptance_base,
        value.marriage_acceptance_age_gap_penalty,
        value.remarriage_rate_multiplier,
        value.widowed_remarriage_multiplier,
        value.divorce_peak_duration_years,
        value.divorce_duration_width,
        value.divorce_peak_multiplier,
        value.divorce_child_multiplier,
        value.divorce_age_gap_multiplier_per_10y,
        value.guardian_search_grandparents,
        value.guardian_search_adult_siblings,
        value.guardian_search_same_household_adults,
        value.guardian_maximum_household_size,
    });
    return output;
}

[[nodiscard]] M7Rules decode_rules(const Json &input) {
    M7Rules value;
    value.vital_rates = decode_vital(input.at("vital"));
    value.marriage_rules = decode_marriage_rules(input.at("marriage_rules"));
    const auto decode_profile = [](const Json &row,
                                   M7UnionTargetProfile &profile) {
        if (!row.is_array() || row.size() != 7U) {
            throw std::runtime_error("invalid M7 union target profile");
        }
        profile.enabled = row[0].get<bool>();
        for (std::size_t index = 0; index < profile.shares.size(); ++index) {
            profile.shares[index] = row[index + 1U].get<double>();
        }
    };
    decode_profile(input.at("genesis_union_target_profile"),
                   value.genesis_union_target_profile);
    decode_profile(input.at("social_union_target_profile"),
                   value.social_union_target_profile);
    const auto &row = input.at("values");
    if (!row.is_array() || row.size() != 87U) {
        throw std::runtime_error("invalid M7 rules");
    }
    std::size_t index = 0;
    value.working_age = row[index++].get<std::uint32_t>();
    value.retirement_age = row[index++].get<std::uint32_t>();
    value.beneficial_ownership = row[index++].get<bool>();
    value.estates = row[index++].get<bool>();
    value.fertility = row[index++].get<bool>();
    value.mortality = row[index++].get<bool>();
    value.persistent_labor = row[index++].get<bool>();
    value.fractional_hours = row[index++].get<bool>();
    value.second_jobs = row[index++].get<bool>();
    value.suspensions = row[index++].get<bool>();
    value.annual_churn = row[index++].get<double>();
    value.firing_adjustment = row[index++].get<double>();
    value.layoff_band = row[index++].get<double>();
    value.target_smoothing = row[index++].get<double>();
    value.suspension_timeout_days = row[index++].get<std::uint32_t>();
    value.suspension_quit_discount = row[index++].get<double>();
    value.frictional_search = row[index++].get<bool>();
    value.search_intensity = row[index++].get<double>();
    value.relationship_wages = row[index++].get<bool>();
    value.job_ladder = row[index++].get<bool>();
    value.ladder_search_intensity = row[index++].get<double>();
    value.ladder_premium = row[index++].get<double>();
    value.person_efficiency = row[index++].get<bool>();
    value.efficiency_sigma = row[index++].get<double>();
    value.genesis_employment_rate = row[index++].get<double>();
    value.participation_margin = row[index++].get<bool>();
    value.age_participation = row[index++].get<bool>();
    value.young_participation_rate = row[index++].get<double>();
    value.prime_participation_rate = row[index++].get<double>();
    value.older_participation_rate = row[index++].get<double>();
    value.reservation_markup = row[index++].get<double>();
    value.welfare_quit_hazard = row[index++].get<double>();
    value.family_transfers = row[index++].get<bool>();
    value.family_transfer_buffer = row[index++].get<double>();
    value.relationships = row[index++].get<bool>();
    value.marriage = row[index++].get<bool>();
    value.divorce = row[index++].get<bool>();
    value.household_lifecycle = row[index++].get<bool>();
    value.lifecycle_consumption = row[index++].get<bool>();
    value.lifecycle_income_propensity = row[index++].get<double>();
    value.lifecycle_wealth_draw_propensity = row[index++].get<double>();
    value.leaving_home = row[index++].get<bool>();
    value.leave_home_min_age = row[index++].get<std::uint32_t>();
    value.leave_home_peak_end_age = row[index++].get<std::uint32_t>();
    value.annual_leave_rate_peak = row[index++].get<double>();
    value.annual_leave_rate_late = row[index++].get<double>();
    value.marriage_interval_days = row[index++].get<std::uint32_t>();
    value.annual_marriage_rate = row[index++].get<double>();
    value.annual_divorce_rate = row[index++].get<double>();
    value.mortality_rank_gradient = row[index++].get<double>();
    value.fertility_rank_gradient = row[index++].get<double>();
    value.stratification_multiplier_minimum = row[index++].get<double>();
    value.stratification_multiplier_maximum = row[index++].get<double>();
    value.demographic_feedback_burnin_years = row[index++].get<std::uint32_t>();
    value.demographic_signal_halflife_years = row[index++].get<double>();
    value.fertility_income_elasticity = row[index++].get<double>();
    value.fertility_multiplier_minimum = row[index++].get<double>();
    value.fertility_multiplier_maximum = row[index++].get<double>();
    value.mortality_income_elasticity = row[index++].get<double>();
    value.mortality_multiplier_minimum = row[index++].get<double>();
    value.mortality_multiplier_maximum = row[index++].get<double>();
    value.genesis_parent_minimum_age_gap = row[index++].get<std::uint32_t>();
    value.genesis_parent_maximum_age_gap = row[index++].get<std::uint32_t>();
    value.genesis_ideal_parent_age_gap = row[index++].get<double>();
    value.genesis_parent_age_gap_stddev = row[index++].get<double>();
    value.genesis_spouse_maximum_age_gap = row[index++].get<std::uint32_t>();
    value.genesis_spouse_age_gap_stddev = row[index++].get<double>();
    value.genesis_target_partnered_adult_share = row[index++].get<double>();
    value.genesis_two_parent_assignment_share = row[index++].get<double>();
    value.genesis_maximum_children_per_parent = row[index++].get<std::uint32_t>();
    value.genesis_maximum_children_per_household =
        row[index++].get<std::uint32_t>();
    value.marriage_peak_age = row[index++].get<double>();
    value.marriage_age_width = row[index++].get<double>();
    value.marriage_age_gap_stddev = row[index++].get<double>();
    value.marriage_acceptance_base = row[index++].get<double>();
    value.marriage_acceptance_age_gap_penalty = row[index++].get<double>();
    value.remarriage_rate_multiplier = row[index++].get<double>();
    value.widowed_remarriage_multiplier = row[index++].get<double>();
    value.divorce_peak_duration_years = row[index++].get<double>();
    value.divorce_duration_width = row[index++].get<double>();
    value.divorce_peak_multiplier = row[index++].get<double>();
    value.divorce_child_multiplier = row[index++].get<double>();
    value.divorce_age_gap_multiplier_per_10y = row[index++].get<double>();
    value.guardian_search_grandparents = row[index++].get<bool>();
    value.guardian_search_adult_siblings = row[index++].get<bool>();
    value.guardian_search_same_household_adults = row[index++].get<bool>();
    value.guardian_maximum_household_size = row[index++].get<std::uint32_t>();
    return value;
}

[[nodiscard]] Json encode_person(const core::PersonRecord &value) {
    return Json::array({
        value.id.value(),
        static_cast<std::uint8_t>(value.sex),
        value.birth_day,
        value.death_day,
        value.mother.value(),
        value.father.value(),
        value.partner.value(),
        value.guardian.value(),
        value.household.value(),
        value.marriage_start_day,
        value.last_divorce_day,
        value.last_widowed_day,
        value.marriage_count,
        value.efficiency,
        value.participating,
        value.searching,
        value.alive,
    });
}

[[nodiscard]] core::PersonRecord decode_person(const Json &row) {
    if (!row.is_array() || row.size() != 17U) {
        throw std::runtime_error("invalid M7 person");
    }
    core::PersonRecord value;
    std::size_t index = 0;
    value.id = PersonId(row[index++].get<std::uint64_t>());
    value.sex = static_cast<core::PersonSex>(row[index++].get<std::uint8_t>());
    value.birth_day = row[index++].get<std::int32_t>();
    value.death_day = row[index++].get<std::int32_t>();
    value.mother = PersonId(row[index++].get<std::uint64_t>());
    value.father = PersonId(row[index++].get<std::uint64_t>());
    value.partner = PersonId(row[index++].get<std::uint64_t>());
    value.guardian = PersonId(row[index++].get<std::uint64_t>());
    value.household = HouseholdId(row[index++].get<std::uint64_t>());
    value.marriage_start_day = row[index++].get<std::int32_t>();
    value.last_divorce_day = row[index++].get<std::int32_t>();
    value.last_widowed_day = row[index++].get<std::int32_t>();
    value.marriage_count = row[index++].get<std::uint32_t>();
    value.efficiency = row[index++].get<double>();
    value.participating = row[index++].get<bool>();
    value.searching = row[index++].get<bool>();
    value.alive = row[index++].get<bool>();
    return value;
}

[[nodiscard]] Json encode_labor(const core::LaborAccounts &value) {
    return Json::array({
        value.employed_fte,
        value.employed_heads,
        value.unemployed,
        value.suspended,
        value.job_guarantee,
        value.out_of_labor_force,
        value.labor_supply,
        value.vacancies,
        value.underemployed_heads,
        value.underemployment_hours,
        value.suspended_memo,
        value.second_job_heads,
        value.second_job_hours,
        value.nonsearching,
        value.hires_total,
        value.churn_separations_total,
        value.layoff_separations_total,
        value.cash_layoffs_total,
        value.firm_exit_separations_total,
        value.death_separations_total,
        value.retirement_separations_total,
        value.recalls_total,
        value.suspensions_total,
        value.suspension_poaches_total,
        value.welfare_quits_total,
        value.job_to_job_moves_total,
        value.private_fte_inflows_total,
        value.private_fte_outflows_total,
        value.previous_employed_fte,
        value.previous_fte_flow_balance,
        value.previous_employed_heads,
        value.previous_head_flow_balance,
    });
}

[[nodiscard]] core::LaborAccounts decode_labor(const Json &row) {
    if (!row.is_array() || row.size() != 32U) {
        throw std::runtime_error("invalid M7 labor accounts");
    }
    core::LaborAccounts value;
    std::size_t index = 0;
#define M7_LABOR(field) value.field = row[index++].get<double>()
    M7_LABOR(employed_fte);
    M7_LABOR(employed_heads);
    M7_LABOR(unemployed);
    M7_LABOR(suspended);
    M7_LABOR(job_guarantee);
    M7_LABOR(out_of_labor_force);
    M7_LABOR(labor_supply);
    M7_LABOR(vacancies);
    M7_LABOR(underemployed_heads);
    M7_LABOR(underemployment_hours);
    M7_LABOR(suspended_memo);
    M7_LABOR(second_job_heads);
    M7_LABOR(second_job_hours);
    M7_LABOR(nonsearching);
    M7_LABOR(hires_total);
    M7_LABOR(churn_separations_total);
    M7_LABOR(layoff_separations_total);
    M7_LABOR(cash_layoffs_total);
    M7_LABOR(firm_exit_separations_total);
    M7_LABOR(death_separations_total);
    M7_LABOR(retirement_separations_total);
    M7_LABOR(recalls_total);
    M7_LABOR(suspensions_total);
    M7_LABOR(suspension_poaches_total);
    M7_LABOR(welfare_quits_total);
    M7_LABOR(job_to_job_moves_total);
    M7_LABOR(private_fte_inflows_total);
    M7_LABOR(private_fte_outflows_total);
    M7_LABOR(previous_employed_fte);
    M7_LABOR(previous_fte_flow_balance);
    M7_LABOR(previous_employed_heads);
    M7_LABOR(previous_head_flow_balance);
#undef M7_LABOR
    return value;
}

[[nodiscard]] Json encode_metrics(const M7Metrics &value) {
    return Json::array({
        value.population,
        value.births,
        value.deaths,
        value.wealth_rank_mortality_multiplier_stddev,
        value.wealth_rank_fertility_multiplier_stddev,
        value.demographic_real_wage_signal,
        value.demographic_fertility_multiplier,
        value.demographic_mortality_multiplier,
        value.bottom_wealth_quintile_deaths,
        value.top_wealth_quintile_deaths,
        value.bottom_wealth_quintile_births,
        value.top_wealth_quintile_births,
        value.households_with_members,
        value.mean_household_size,
        value.working_age_share,
        value.dependency_ratio,
        value.mean_person_efficiency,
        value.person_efficiency_stddev,
        value.active_unions,
        value.mean_partner_age_gap,
        value.mean_partner_log_efficiency_gap,
        value.participation_rate,
        value.estates_settled,
        value.beneficial_lots_transferred,
        value.inheritance_tax_share,
        value.inheritance_tax_paid,
        value.pension_paid,
        value.beneficial_projection_error,
        value.employed_fte,
        value.employed_heads,
        value.unemployment,
        value.unemployment_rate,
        value.suspended,
        value.job_guarantee,
        value.out_of_labor_force,
        value.labor_supply,
        value.vacancies,
        value.underemployed_heads,
        value.underemployment_hours,
        value.suspended_memo,
        value.second_job_heads,
        value.second_job_hours,
        value.nonsearching,
        value.job_to_job_moves,
        value.mean_hourly_wage,
        value.family_transfer_total,
        value.family_transfer_recipients,
        value.family_exposed_households,
        value.hires,
        value.separations,
        value.churn_separations,
        value.demand_layoff_separations,
        value.cash_layoff_separations,
        value.firm_exit_separations,
        value.death_separations,
        value.retirement_separations,
        value.welfare_quits,
        value.suspensions_flow,
        value.suspension_poaches,
        value.recalls,
        value.marriages,
        value.divorces,
        value.widowhoods,
        value.remarriages,
        value.widowed_remarriages,
        value.guardian_same_household_assignments,
        value.guardian_grandparent_assignments,
        value.guardian_adult_sibling_assignments,
        value.guardian_parent_assignments,
        value.guardian_unresolved_assignments,
        value.partnered_adult_share,
        value.dual_parent_minor_share,
        value.guardian_only_minor_share,
        value.mean_mother_age_gap,
        value.mother_age_gap_stddev,
        value.mean_father_age_gap,
        value.father_age_gap_stddev,
        value.maximum_household_size,
        value.leaving_home_events,
    });
}

void decode_metrics(const Json &row, M7Metrics &value) {
    if (!row.is_array() || row.size() != 79U) {
        throw std::runtime_error("invalid M7 metrics");
    }
    std::size_t index = 0;
    value.population = row[index++].get<std::uint64_t>();
    value.births = row[index++].get<std::uint64_t>();
    value.deaths = row[index++].get<std::uint64_t>();
    value.wealth_rank_mortality_multiplier_stddev = row[index++].get<double>();
    value.wealth_rank_fertility_multiplier_stddev = row[index++].get<double>();
    value.demographic_real_wage_signal = row[index++].get<double>();
    value.demographic_fertility_multiplier = row[index++].get<double>();
    value.demographic_mortality_multiplier = row[index++].get<double>();
    value.bottom_wealth_quintile_deaths = row[index++].get<std::uint64_t>();
    value.top_wealth_quintile_deaths = row[index++].get<std::uint64_t>();
    value.bottom_wealth_quintile_births = row[index++].get<std::uint64_t>();
    value.top_wealth_quintile_births = row[index++].get<std::uint64_t>();
    value.households_with_members = row[index++].get<std::uint64_t>();
    value.mean_household_size = row[index++].get<double>();
    value.working_age_share = row[index++].get<double>();
    value.dependency_ratio = row[index++].get<double>();
    value.mean_person_efficiency = row[index++].get<double>();
    value.person_efficiency_stddev = row[index++].get<double>();
    value.active_unions = row[index++].get<std::uint64_t>();
    value.mean_partner_age_gap = row[index++].get<double>();
    value.mean_partner_log_efficiency_gap = row[index++].get<double>();
    value.participation_rate = row[index++].get<double>();
    value.estates_settled = row[index++].get<std::uint64_t>();
    value.beneficial_lots_transferred = row[index++].get<std::uint64_t>();
    value.inheritance_tax_share = row[index++].get<double>();
    value.inheritance_tax_paid = row[index++].get<double>();
    value.pension_paid = row[index++].get<double>();
    value.beneficial_projection_error = row[index++].get<double>();
    value.employed_fte = row[index++].get<double>();
    value.employed_heads = row[index++].get<double>();
    value.unemployment = row[index++].get<double>();
    value.unemployment_rate = row[index++].get<double>();
    value.suspended = row[index++].get<double>();
    value.job_guarantee = row[index++].get<double>();
    value.out_of_labor_force = row[index++].get<double>();
    value.labor_supply = row[index++].get<double>();
    value.vacancies = row[index++].get<double>();
    value.underemployed_heads = row[index++].get<double>();
    value.underemployment_hours = row[index++].get<double>();
    value.suspended_memo = row[index++].get<double>();
    value.second_job_heads = row[index++].get<double>();
    value.second_job_hours = row[index++].get<double>();
    value.nonsearching = row[index++].get<double>();
    value.job_to_job_moves = row[index++].get<double>();
    value.mean_hourly_wage = row[index++].get<double>();
    value.family_transfer_total = row[index++].get<double>();
    value.family_transfer_recipients = row[index++].get<double>();
    value.family_exposed_households = row[index++].get<double>();
    value.hires = row[index++].get<double>();
    value.separations = row[index++].get<double>();
    value.churn_separations = row[index++].get<double>();
    value.demand_layoff_separations = row[index++].get<double>();
    value.cash_layoff_separations = row[index++].get<double>();
    value.firm_exit_separations = row[index++].get<double>();
    value.death_separations = row[index++].get<double>();
    value.retirement_separations = row[index++].get<double>();
    value.welfare_quits = row[index++].get<double>();
    value.suspensions_flow = row[index++].get<double>();
    value.suspension_poaches = row[index++].get<double>();
    value.recalls = row[index++].get<double>();
    value.marriages = row[index++].get<std::uint64_t>();
    value.divorces = row[index++].get<std::uint64_t>();
    value.widowhoods = row[index++].get<std::uint64_t>();
    value.remarriages = row[index++].get<std::uint64_t>();
    value.widowed_remarriages = row[index++].get<std::uint64_t>();
    value.guardian_same_household_assignments =
        row[index++].get<std::uint64_t>();
    value.guardian_grandparent_assignments = row[index++].get<std::uint64_t>();
    value.guardian_adult_sibling_assignments =
        row[index++].get<std::uint64_t>();
    value.guardian_parent_assignments = row[index++].get<std::uint64_t>();
    value.guardian_unresolved_assignments = row[index++].get<std::uint64_t>();
    value.partnered_adult_share = row[index++].get<double>();
    value.dual_parent_minor_share = row[index++].get<double>();
    value.guardian_only_minor_share = row[index++].get<double>();
    value.mean_mother_age_gap = row[index++].get<double>();
    value.mother_age_gap_stddev = row[index++].get<double>();
    value.mean_father_age_gap = row[index++].get<double>();
    value.father_age_gap_stddev = row[index++].get<double>();
    value.maximum_household_size = row[index++].get<std::uint64_t>();
    value.leaving_home_events = row[index++].get<std::uint64_t>();
}

[[nodiscard]] Json encode_runtime(const M7Runtime &runtime) {
    Json output;
    output["policy"] = Json::array({
        runtime.policy.inheritance_tax_rate,
        runtime.policy.pension_replacement,
    });
    output["rules"] = encode_rules(runtime.rules);
    output["state"] = Json::array({
        runtime.start_calendar_day,
        runtime.current_calendar_day,
        runtime.next_event_id,
        runtime.population_rng_counter,
    });
    output["metrics"] = encode_metrics(runtime.last_metrics);
    output["labor"] = encode_labor(runtime.labor_accounts);
    output["firm_target_ema"] = runtime.firm_target_ema;
    output["stratification"] = Json{
        {"snapshot_day", runtime.stratification_snapshot_day},
        {"household_quintile", runtime.household_wealth_quintile},
        {"mortality_multiplier", runtime.household_mortality_multiplier},
        {"fertility_multiplier", runtime.household_fertility_multiplier},
        {"mortality_quintile", runtime.mortality_quintile_multiplier},
        {"fertility_quintile", runtime.fertility_quintile_multiplier},
    };
    output["demographic_signal"] = Json::array({
        runtime.demographic_signal_year,
        runtime.demographic_signal_years_completed,
        runtime.demographic_signal_ewma,
        runtime.demographic_signal_baseline,
        runtime.demographic_signal_x,
        runtime.demographic_signal_fertility_multiplier,
        runtime.demographic_signal_mortality_multiplier,
        runtime.demographic_signal_last_real_wage,
        runtime.demographic_signal_wage_sum,
        runtime.demographic_signal_labor_sum,
        runtime.demographic_signal_price_sum,
        runtime.demographic_signal_days,
    });
    output["persons"] = Json::array();
    for (const auto &person : runtime.persons.records()) {
        output["persons"].push_back(encode_person(person));
    }
    output["beneficial"] = Json::array();
    std::uint32_t beneficial_lot_id = 1U;
    for (const auto &lot : runtime.beneficial_ownership.records()) {
        output["beneficial"].push_back(Json::array({
            beneficial_lot_id++,
            static_cast<std::uint8_t>(lot.asset.kind),
            lot.asset.household.value(),
            lot.asset.value,
            lot.owner.value(),
            lot.share,
            lot.is_active(),
        }));
    }
    output["jobs"] = Json::array();
    for (const auto &job : runtime.employment.records()) {
        output["jobs"].push_back(Json::array({
            job.id.value(),
            job.person.value(),
            job.firm.value(),
            job.hire_day,
            job.separation_day,
            job.suspension_day,
            job.wage,
            job.hours,
            job.secondary,
            job.suspended,
            job.active,
            static_cast<std::uint8_t>(job.separation_kind),
        }));
    }
    output["job_rosters"] = Json::array();
    for (const auto &firm_roster : runtime.employment.firm_rosters()) {
        auto encoded_roster = Json::array();
        for (const auto job_id : firm_roster) {
            encoded_roster.push_back(job_id.value());
        }
        output["job_rosters"].push_back(std::move(encoded_roster));
    }
    output["unions"] = Json::array();
    for (const auto &record : runtime.relationships.unions()) {
        output["unions"].push_back(Json::array({
            record.event.value(),
            record.first.value(),
            record.second.value(),
            record.first_origin_household.value(),
            record.second_origin_household.value(),
            record.start_day,
            record.end_day,
            static_cast<std::uint8_t>(record.end_kind),
            record.active,
        }));
    }
    output["estates"] = Json::array();
    for (const auto &estate : runtime.estates) {
        output["estates"].push_back(Json::array({
            estate.event.value(),
            estate.deceased.value(),
            estate.heir.value(),
            estate.household.value(),
            estate.destination_household.value(),
            estate.opened_day,
            estate.settled_day,
            estate.transferred_lots,
            estate.gross_share,
            estate.tax_share,
            estate.gross_value,
            estate.liabilities,
            estate.tax_paid,
            estate.public_residual,
            estate.settled,
        }));
    }
    output["leaving_home"] = Json::array();
    for (const auto &event : runtime.leaving_home) {
        output["leaving_home"].push_back(Json::array({
            event.event.value(),
            event.person.value(),
            event.origin.value(),
            event.destination.value(),
            event.day,
        }));
    }
    return output;
}

void decode_runtime(const Json &input, M7Runtime &runtime) {
    const auto &policy = input.at("policy");
    if (!policy.is_array() || policy.size() != 2U) {
        throw std::runtime_error("invalid M7 policy");
    }
    runtime.policy.inheritance_tax_rate = policy[0].get<double>();
    runtime.policy.pension_replacement = policy[1].get<double>();
    runtime.rules = decode_rules(input.at("rules"));
    const auto &state = input.at("state");
    if (!state.is_array() || state.size() != 4U) {
        throw std::runtime_error("invalid M7 runtime");
    }
    runtime.start_calendar_day = state[0].get<std::int32_t>();
    runtime.current_calendar_day = state[1].get<std::int32_t>();
    runtime.next_event_id = state[2].get<std::uint64_t>();
    runtime.population_rng_counter = state[3].get<std::uint64_t>();
    decode_metrics(input.at("metrics"), runtime.last_metrics);
    runtime.labor_accounts = decode_labor(input.at("labor"));
    runtime.firm_target_ema = input.at("firm_target_ema").get<std::vector<double>>();
    const auto &stratification = input.at("stratification");
    runtime.stratification_snapshot_day =
        stratification.at("snapshot_day").get<std::int32_t>();
    runtime.household_wealth_quintile =
        stratification.at("household_quintile").get<std::vector<std::uint8_t>>();
    runtime.household_mortality_multiplier =
        stratification.at("mortality_multiplier").get<std::vector<double>>();
    runtime.household_fertility_multiplier =
        stratification.at("fertility_multiplier").get<std::vector<double>>();
    runtime.mortality_quintile_multiplier =
        stratification.at("mortality_quintile")
            .get<std::array<double, kWealthQuintiles>>();
    runtime.fertility_quintile_multiplier =
        stratification.at("fertility_quintile")
            .get<std::array<double, kWealthQuintiles>>();
    const auto &demographic_signal = input.at("demographic_signal");
    if (!demographic_signal.is_array() || demographic_signal.size() != 12U) {
        throw std::runtime_error("invalid M7 demographic signal");
    }
    std::size_t signal_index = 0U;
    runtime.demographic_signal_year =
        demographic_signal[signal_index++].get<std::int32_t>();
    runtime.demographic_signal_years_completed =
        demographic_signal[signal_index++].get<std::uint32_t>();
    runtime.demographic_signal_ewma =
        demographic_signal[signal_index++].get<double>();
    runtime.demographic_signal_baseline =
        demographic_signal[signal_index++].get<double>();
    runtime.demographic_signal_x =
        demographic_signal[signal_index++].get<double>();
    runtime.demographic_signal_fertility_multiplier =
        demographic_signal[signal_index++].get<double>();
    runtime.demographic_signal_mortality_multiplier =
        demographic_signal[signal_index++].get<double>();
    runtime.demographic_signal_last_real_wage =
        demographic_signal[signal_index++].get<double>();
    runtime.demographic_signal_wage_sum =
        demographic_signal[signal_index++].get<double>();
    runtime.demographic_signal_labor_sum =
        demographic_signal[signal_index++].get<double>();
    runtime.demographic_signal_price_sum =
        demographic_signal[signal_index++].get<double>();
    runtime.demographic_signal_days =
        demographic_signal[signal_index++].get<std::uint32_t>();

    std::vector<core::PersonRecord> persons;
    for (const auto &row : input.at("persons")) {
        persons.push_back(decode_person(row));
    }
    auto status = runtime.persons.replace_records(std::move(persons));
    if (!status.ok()) {
        throw std::runtime_error("invalid M7 person store");
    }
    status = runtime.membership.rebuild(runtime.persons);
    if (!status.ok()) {
        throw std::runtime_error("invalid M7 membership store");
    }

    std::vector<core::BeneficialLot> beneficial;
    for (const auto &row : input.at("beneficial")) {
        if (!row.is_array() || row.size() != 7U) {
            throw std::runtime_error("invalid M7 beneficial lot");
        }
        const auto expected_id = static_cast<std::uint64_t>(beneficial.size()) + 1U;
        const auto share = row[5].get<double>();
        const auto active = row[6].get<bool>();
        if (row[0].get<std::uint64_t>() != expected_id || active != (share > 0.0)) {
            throw std::runtime_error("invalid M7 beneficial lot");
        }
        beneficial.push_back({
            {
                static_cast<core::BeneficialAssetKind>(row[1].get<std::uint8_t>()),
                HouseholdId(row[2].get<std::uint64_t>()),
                row[3].get<std::uint32_t>(),
            },
            PersonId(row[4].get<std::uint64_t>()),
            share,
        });
    }
    status = runtime.beneficial_ownership.replace_records(std::move(beneficial));
    if (!status.ok()) {
        throw std::runtime_error("invalid M7 beneficial ownership store");
    }

    std::vector<core::JobRecord> jobs;
    for (const auto &row : input.at("jobs")) {
        if (!row.is_array() || row.size() != 12U) {
            throw std::runtime_error("invalid M7 job");
        }
        jobs.push_back({
            JobId(row[0].get<std::uint64_t>()),
            PersonId(row[1].get<std::uint64_t>()),
            FirmId(row[2].get<std::uint64_t>()),
            row[3].get<std::int32_t>(),
            row[4].get<std::int32_t>(),
            row[5].get<std::int32_t>(),
            row[6].get<double>(),
            row[7].get<double>(),
            row[8].get<bool>(),
            row[9].get<bool>(),
            row[10].get<bool>(),
            static_cast<core::SeparationKind>(row[11].get<std::uint8_t>()),
        });
    }
    status = runtime.employment.replace_records(std::move(jobs));
    if (!status.ok()) {
        throw std::runtime_error("invalid M7 employment store");
    }
    std::vector<std::vector<JobId>> job_rosters;
    for (const auto &encoded_roster : input.at("job_rosters")) {
        if (!encoded_roster.is_array()) {
            throw std::runtime_error("invalid M7 employment roster");
        }
        std::vector<JobId> roster;
        roster.reserve(encoded_roster.size());
        for (const auto &job_id : encoded_roster) {
            roster.emplace_back(job_id.get<std::uint64_t>());
        }
        job_rosters.push_back(std::move(roster));
    }
    status = runtime.employment.restore_firm_rosters(std::move(job_rosters));
    if (!status.ok()) {
        throw std::runtime_error("invalid M7 employment roster store");
    }

    std::vector<core::UnionRecord> unions;
    for (const auto &row : input.at("unions")) {
        if (!row.is_array() || row.size() != 9U) {
            throw std::runtime_error("invalid M7 union");
        }
        unions.push_back({
            EventId(row[0].get<std::uint64_t>()),
            PersonId(row[1].get<std::uint64_t>()),
            PersonId(row[2].get<std::uint64_t>()),
            HouseholdId(row[3].get<std::uint64_t>()),
            HouseholdId(row[4].get<std::uint64_t>()),
            row[5].get<std::int32_t>(),
            row[6].get<std::int32_t>(),
            static_cast<core::UnionEndKind>(row[7].get<std::uint8_t>()),
            row[8].get<bool>(),
        });
    }
    status = runtime.relationships.replace_unions(runtime.persons, std::move(unions));
    if (!status.ok()) {
        throw std::runtime_error("invalid M7 relationship store");
    }

    for (const auto &row : input.at("estates")) {
        if (!row.is_array() || row.size() != 15U) {
            throw std::runtime_error("invalid M7 estate");
        }
        runtime.estates.push_back({
            EventId(row[0].get<std::uint64_t>()),
            PersonId(row[1].get<std::uint64_t>()),
            PersonId(row[2].get<std::uint64_t>()),
            HouseholdId(row[3].get<std::uint64_t>()),
            HouseholdId(row[4].get<std::uint64_t>()),
            row[5].get<std::int32_t>(),
            row[6].get<std::int32_t>(),
            row[7].get<std::uint64_t>(),
            row[8].get<double>(),
            row[9].get<double>(),
            row[10].get<double>(),
            row[11].get<double>(),
            row[12].get<double>(),
            row[13].get<bool>(),
            row[14].get<bool>(),
        });
    }
    for (const auto &row : input.at("leaving_home")) {
        if (!row.is_array() || row.size() != 5U) {
            throw std::runtime_error("invalid M7 leaving-home event");
        }
        runtime.leaving_home.push_back({
            EventId(row[0].get<std::uint64_t>()),
            PersonId(row[1].get<std::uint64_t>()),
            HouseholdId(row[2].get<std::uint64_t>()),
            HouseholdId(row[3].get<std::uint64_t>()),
            row[4].get<std::int32_t>(),
        });
    }
}

} // namespace

bool is_m7_checkpoint(std::span<const std::uint8_t> bytes) noexcept {
    return bytes.size() >= kMagic.size() &&
           std::equal(kMagic.begin(), kMagic.end(), bytes.begin());
}

Result<std::vector<std::uint8_t>>
save_m7_checkpoint(const core::RootState &root, const M4Runtime &real_economy_runtime,
                   const M5Runtime &monetary_runtime,
                   const M6Runtime &financial_runtime, const M7Runtime &runtime,
                   Tick tick) {
    if (!validate_m7_state(root, real_economy_runtime, monetary_runtime,
                           financial_runtime, runtime, tick)
             .ok()) {
        return Status(ErrorCode::invariant_violation,
                      "M7 checkpoint state violates an invariant");
    }
    auto base = save_m6_checkpoint(root, real_economy_runtime, monetary_runtime,
                                   financial_runtime, tick);
    if (!base.ok()) {
        return base.status();
    }
    const std::string encoded = encode_runtime(runtime).dump();
    std::vector<std::uint8_t> bytes;
    bytes.reserve(kMagic.size() + 4U + 8U + base.get_if()->size() + 8U +
                  encoded.size() + kDigestBytes);
    bytes.insert(bytes.end(), kMagic.begin(), kMagic.end());
    append_u32(bytes, kM7CheckpointSchemaVersion);
    append_u64(bytes, base.get_if()->size());
    bytes.insert(bytes.end(), base.get_if()->begin(), base.get_if()->end());
    append_u64(bytes, encoded.size());
    bytes.insert(bytes.end(), encoded.begin(), encoded.end());
    const auto digest = core::sha256_digest(bytes);
    bytes.insert(bytes.end(), digest.bytes.begin(), digest.bytes.end());
    if (bytes.size() > kMaximumCheckpointBytes) {
        return Status(ErrorCode::out_of_range,
                      "M7 checkpoint exceeds the supported size");
    }
    return bytes;
}

Result<M7Checkpoint> load_m7_checkpoint(std::span<const std::uint8_t> bytes) {
    if (bytes.size() > kMaximumCheckpointBytes ||
        bytes.size() < kMagic.size() + 4U + 8U + 8U + kDigestBytes ||
        !is_m7_checkpoint(bytes)) {
        return corrupt("M7 checkpoint identity or size is invalid");
    }
    const auto payload = bytes.first(bytes.size() - kDigestBytes);
    const auto digest = core::sha256_digest(payload);
    if (!std::equal(digest.bytes.begin(), digest.bytes.end(),
                    bytes.end() - static_cast<std::ptrdiff_t>(kDigestBytes))) {
        return corrupt("M7 checkpoint checksum does not match");
    }
    std::size_t position = kMagic.size();
    std::uint32_t version = 0;
    std::uint64_t base_size = 0;
    if (!read_u32(payload, position, version) ||
        version != kM7CheckpointSchemaVersion ||
        !read_u64(payload, position, base_size) ||
        base_size > payload.size() - position) {
        return corrupt("M7 checkpoint header is invalid");
    }
    const auto base = payload.subspan(position, static_cast<std::size_t>(base_size));
    position += static_cast<std::size_t>(base_size);
    std::uint64_t json_size = 0;
    if (!read_u64(payload, position, json_size) ||
        json_size > payload.size() - position ||
        position + json_size != payload.size()) {
        return corrupt("M7 checkpoint payload size is invalid");
    }
    auto loaded = load_m6_checkpoint(base);
    if (!loaded.ok()) {
        return loaded.status();
    }
    try {
        const std::string encoded(
            reinterpret_cast<const char *>(payload.data() + position),
            static_cast<std::size_t>(json_size));
        const auto json = Json::parse(encoded);
        auto value = std::move(*loaded.get_if());
        M7Runtime runtime;
        decode_runtime(json, runtime);
        runtime.last_metrics.economy = value.runtime.last_metrics;
        if (!validate_m7_state(value.root, value.real_economy_runtime,
                               value.monetary_runtime, value.runtime, runtime,
                               value.tick)
                 .ok()) {
            return corrupt("M7 checkpoint restored state is invalid");
        }
        return M7Checkpoint{
            std::move(value.root),
            std::move(value.real_economy_runtime),
            std::move(value.monetary_runtime),
            std::move(value.runtime),
            std::move(runtime),
            value.tick,
        };
    } catch (...) {
        return corrupt("M7 checkpoint JSON payload is invalid");
    }
}

Result<core::StateDigest> m7_state_digest(const core::RootState &root,
                                          const M4Runtime &real_economy_runtime,
                                          const M5Runtime &monetary_runtime,
                                          const M6Runtime &financial_runtime,
                                          const M7Runtime &runtime, Tick tick) {
    auto checkpoint = save_m7_checkpoint(root, real_economy_runtime, monetary_runtime,
                                         financial_runtime, runtime, tick);
    if (!checkpoint.ok()) {
        return checkpoint.status();
    }
    return core::sha256_digest(*checkpoint.get_if());
}

} // namespace macro_sim::simulation
