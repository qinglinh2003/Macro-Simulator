#include "macro_sim/simulation/m7.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <numeric>
#include <queue>
#include <tuple>
#include <utility>

#include "macro_sim/core/transaction.hpp"

namespace macro_sim::simulation {
namespace {

constexpr double kDaysPerYear = 365.2425;
constexpr double kDailyYear = 1.0 / kDaysPerYear;
constexpr std::uint64_t kMortalityStream = 0x4d4f5254414c4954ULL;
constexpr std::uint64_t kFertilityStream = 0x46455254494c4954ULL;
constexpr std::uint64_t kSexStream = 0x4249525448534558ULL;
constexpr std::uint64_t kAgeStream = 0x47454e4553495341ULL;
constexpr std::uint64_t kOffsetStream = 0x47454e455349534fULL;
constexpr std::uint64_t kChurnStream = 0x4c41424f52434855ULL;
constexpr std::uint64_t kLayoffStream = 0x4c41594f46463031ULL;
constexpr std::uint64_t kWelfareStream = 0x57454c4641524551ULL;
constexpr std::uint64_t kParticipationStream = 0x5041525449434950ULL;
constexpr std::uint64_t kSecondJobStream = 0x5345434f4e444a42ULL;
constexpr std::uint64_t kLadderStream = 0x4c41444445523031ULL;
constexpr std::uint64_t kLadderFirmStream = 0x4c41444445523032ULL;
constexpr std::uint64_t kDivorceStream = 0x4449564f52434530ULL;
constexpr std::uint64_t kMarriageStream = 0x4d41525249414745ULL;
constexpr std::uint64_t kLeavingHomeStream = 0x4c45415645484f4dULL;
constexpr std::uint64_t kEfficiencyNormalStream = 0x454646494349454eULL;
constexpr std::uint64_t kEfficiencyAngleStream = 0x454646494349414eULL;
constexpr std::uint64_t kGenesisPartnerOrderStream = 0x47454e504152544eULL;
constexpr std::uint64_t kGenesisSpouseGapStream = 0x47454e5350474150ULL;
constexpr std::uint64_t kGenesisParentGapStream = 0x47454e5041474150ULL;
constexpr std::uint64_t kGenesisTwoParentStream = 0x47454e54574f5041ULL;
constexpr double kTwoPi = 6.283185307179586476925286766559;
constexpr double kLaborTolerance = 1.0e-8;
constexpr std::size_t kWealthQuintiles = 5U;
constexpr std::uint8_t kUnrankedWealthQuintile = 5U;

[[nodiscard]] bool finite(double value) noexcept { return std::isfinite(value); }

[[nodiscard]] bool government_enabled(const M4Runtime &runtime) noexcept {
    return (runtime.capability_mask & capability_bit(M4Capability::government)) != 0U;
}

[[nodiscard]] std::uint64_t splitmix64(std::uint64_t value) noexcept {
    value += 0x9e3779b97f4a7c15ULL;
    value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
    value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
    return value ^ (value >> 31U);
}

[[nodiscard]] double unit_draw(std::uint64_t seed, std::uint64_t identity,
                               std::int64_t day, std::uint64_t stream) noexcept {
    const auto day_bits = static_cast<std::uint64_t>(day);
    const auto bits =
        splitmix64(seed ^ splitmix64(identity) ^ splitmix64(day_bits) ^ stream);
    return static_cast<double>(bits >> 11U) * 0x1.0p-53;
}

[[nodiscard]] double normal_draw(std::uint64_t seed, std::uint64_t identity,
                                 std::int64_t day,
                                 std::uint64_t stream) noexcept {
    const double radial = std::max(
        unit_draw(seed, identity, day, stream),
        std::numeric_limits<double>::min());
    const double angle = unit_draw(seed, identity, day, stream ^ 0x9e3779b97f4a7c15ULL);
    return std::sqrt(-2.0 * std::log(radial)) * std::cos(kTwoPi * angle);
}

[[nodiscard]] std::size_t union_age_band(double age) noexcept {
    if (age < 25.0) {
        return 0U;
    }
    if (age < 35.0) {
        return 1U;
    }
    if (age < 50.0) {
        return 2U;
    }
    if (age < 65.0) {
        return 3U;
    }
    if (age < 75.0) {
        return 4U;
    }
    return 5U;
}

[[nodiscard]] double union_target_share(const M7UnionTargetProfile &profile,
                                        double age) noexcept {
    if (!profile.enabled || age < 18.0 || age > 100.0) {
        return 0.0;
    }
    return profile.shares[union_age_band(age)];
}

[[nodiscard]] double person_efficiency_draw(const M7Rules &rules, std::uint64_t seed,
                                            PersonId person,
                                            std::int32_t birth_day) noexcept {
    if (!rules.person_efficiency || rules.efficiency_sigma <= 0.0) {
        return 1.0;
    }
    const double radial_draw =
        std::max(unit_draw(seed, person.value(), birth_day, kEfficiencyNormalStream),
                 std::numeric_limits<double>::min());
    const double angle_draw =
        unit_draw(seed, person.value(), birth_day, kEfficiencyAngleStream);
    const double standard_normal =
        std::sqrt(-2.0 * std::log(radial_draw)) * std::cos(kTwoPi * angle_draw);
    const double sigma = rules.efficiency_sigma;
    return std::exp(sigma * standard_normal - 0.5 * sigma * sigma);
}

[[nodiscard]] double completed_age(const core::PersonRecord &person,
                                   std::int32_t day) noexcept {
    return std::max(0.0, static_cast<double>(day - person.birth_day) / kDaysPerYear);
}

[[nodiscard]] std::int32_t calendar_year_from_ordinal(std::int32_t ordinal) noexcept {
    if (ordinal < 1) {
        return static_cast<std::int32_t>(
            std::floor(static_cast<double>(ordinal) / kDaysPerYear));
    }
    // Python's date ordinal 719163 is 1970-01-01.  Convert with the inverse of
    // Howard Hinnant's civil calendar algorithm so year boundaries follow the
    // actual Gregorian calendar used by the product start-date contract.
    std::int64_t days = static_cast<std::int64_t>(ordinal) - 719163;
    days += 719468;
    const std::int64_t era = (days >= 0 ? days : days - 146096) / 146097;
    const auto day_of_era = static_cast<std::uint32_t>(days - era * 146097);
    const auto year_of_era = static_cast<std::uint32_t>(
        (day_of_era - day_of_era / 1460U + day_of_era / 36524U -
         day_of_era / 146096U) /
        365U);
    std::int64_t year = static_cast<std::int64_t>(year_of_era) + era * 400;
    const auto day_of_year =
        day_of_era - (365U * year_of_era + year_of_era / 4U - year_of_era / 100U);
    const auto month_prime = (5U * day_of_year + 2U) / 153U;
    year += month_prime < 10U ? 0 : 1;
    return static_cast<std::int32_t>(year);
}

[[nodiscard]] double lifecycle_income_capacity(double age, const M7Rules &rules) {
    const double entry = static_cast<double>(rules.working_age);
    const double retirement = static_cast<double>(rules.retirement_age);
    if (age < entry || age >= retirement) {
        return 0.0;
    }
    const double ramp_up_end = entry + 6.0;
    if (age <= ramp_up_end) {
        return 0.5 + 0.5 * (age - entry) / std::max(1.0, ramp_up_end - entry);
    }
    if (age < retirement - 14.0) {
        return 1.0;
    }
    const double decline_years = std::max(1.0, retirement - (retirement - 14.0) - 1.0);
    return std::clamp(1.0 - 0.3 * (age - (retirement - 14.0)) / decline_years,
                      0.0, 1.0);
}

[[nodiscard]] std::vector<double>
expected_remaining_life_by_age(const algorithms::VitalRates &rates) {
    const auto maximum_age = static_cast<std::size_t>(rates.maximum_age);
    std::vector<double> survivorship(maximum_age + 1U, 1.0);
    for (std::size_t age = 1; age <= maximum_age; ++age) {
        const auto survival = algorithms::survival_probability(
            rates, static_cast<double>(age - 1U), 1.0);
        if (!survival.ok()) {
            return {};
        }
        survivorship[age] = survivorship[age - 1U] * *survival.get_if();
    }
    std::vector<double> remaining(maximum_age + 1U, 0.0);
    double tail = 0.0;
    for (std::size_t offset = 0; offset <= maximum_age; ++offset) {
        const auto age = maximum_age - offset;
        tail += survivorship[age];
        if (survivorship[age] > kLaborTolerance) {
            remaining[age] = tail / survivorship[age];
        }
    }
    return remaining;
}

[[nodiscard]] Status apply_lifecycle_consumption(
    const core::RootState &state, const M7Rules &rules,
    const core::PersonStore &persons, std::int32_t calendar_day,
    M4TickScratch &real, const M5TickScratch &monetary,
    const M6TickScratch &financial, M7TickScratch &scratch) {
    if (!rules.lifecycle_consumption) {
        return Status::success();
    }
    const auto count = real.household_ids_.size();
    scratch.lifecycle_need_units_.assign(count, 0.0);
    scratch.lifecycle_income_capacity_.assign(count, 0.0);
    scratch.lifecycle_inverse_life_days_.assign(count, 0.0);
    scratch.lifecycle_net_wealth_.assign(count, 0.0);
    std::vector<std::uint32_t> members(count, 0U);
    std::vector<std::uint32_t> adults(count, 0U);
    const auto remaining_life = expected_remaining_life_by_age(rules.vital_rates);
    if (remaining_life.empty()) {
        return Status(ErrorCode::invalid_argument,
                      "M7 lifecycle consumption has invalid vital rates");
    }
    for (std::size_t index = 0; index < count; ++index) {
        const auto *household = state.households.get(real.household_ids_[index]);
        if (household == nullptr) {
            return Status(ErrorCode::invariant_violation,
                          "M7 lifecycle household is absent");
        }
        const auto account =
            static_cast<std::size_t>(household->primary_account.value());
        if (account >= real.balances_.size()) {
            return Status(ErrorCode::invariant_violation,
                          "M7 lifecycle household account is stale");
        }
        scratch.lifecycle_net_wealth_[index] = real.balances_[account];
        if (account < monetary.debt_by_account_.size()) {
            scratch.lifecycle_net_wealth_[index] -= monetary.debt_by_account_[account];
        }
    }
    for (const auto &lot : financial.securities_.lots()) {
        if (!lot.active() || lot.holder.kind() != core::OwnerKind::household) {
            continue;
        }
        const auto identity = static_cast<std::size_t>(lot.holder.value());
        const auto index = identity < real.household_dense_index_.size()
                               ? real.household_dense_index_[identity]
                               : std::numeric_limits<std::size_t>::max();
        if (index >= count) {
            continue;
        }
        if (lot.security.kind() == core::SecurityKind::equity) {
            const auto *contract =
                financial.securities_.get(EquityId(lot.security.value()));
            if (contract != nullptr && contract->active) {
                scratch.lifecycle_net_wealth_[index] +=
                    lot.units * contract->price.value();
            }
        } else {
            const auto *contract =
                financial.securities_.get(BondId(lot.security.value()));
            if (contract != nullptr && contract->active) {
                scratch.lifecycle_net_wealth_[index] += lot.units;
            }
        }
    }
    for (const auto person_id : persons.alive_ids()) {
        const auto *person = persons.get(person_id);
        if (person == nullptr || !person->alive) {
            continue;
        }
        const auto identity = static_cast<std::size_t>(person->household.value());
        const auto index = identity < real.household_dense_index_.size()
                               ? real.household_dense_index_[identity]
                               : std::numeric_limits<std::size_t>::max();
        if (index >= count) {
            continue;
        }
        const double age = completed_age(*person, calendar_day);
        scratch.lifecycle_need_units_[index] +=
            age < 18.0 ? 0.65 : (age >= 65.0 ? 0.90 : 1.0);
        scratch.lifecycle_income_capacity_[index] +=
            lifecycle_income_capacity(age, rules) * person->efficiency;
        if (age >= static_cast<double>(rules.working_age) &&
            age < static_cast<double>(rules.retirement_age)) {
            ++adults[index];
        }
        const auto integer_age = std::min<std::size_t>(
            remaining_life.size() - 1U,
            static_cast<std::size_t>(std::max(0.0, std::floor(age))));
        scratch.lifecycle_inverse_life_days_[index] +=
            1.0 / std::max(1.0, remaining_life[integer_age] * kDaysPerYear);
        ++members[index];
    }
    for (std::size_t index = 0; index < count; ++index) {
        auto &work = real.household_work_[index];
        if (members[index] == 0U) {
            work.consumption_budget = 0.0;
            work.wealth_consumption_budget = 0.0;
            continue;
        }
        double adjusted_income = 0.0;
        if (adults[index] > 0U) {
            const double capacity_per_adult =
                scratch.lifecycle_income_capacity_[index] /
                static_cast<double>(adults[index]);
            adjusted_income = std::max(0.0, work.income_expected) *
                              capacity_per_adult *
                              scratch.lifecycle_need_units_[index] /
                              static_cast<double>(adults[index]);
        }
        const double wealth_draw =
            std::max(0.0, scratch.lifecycle_net_wealth_[index]) *
            scratch.lifecycle_inverse_life_days_[index] /
            static_cast<double>(members[index]);
        work.consumption_budget = std::max(
            0.0, rules.lifecycle_income_propensity * adjusted_income +
                     rules.lifecycle_wealth_draw_propensity * wealth_draw);
        work.wealth_consumption_budget =
            rules.lifecycle_wealth_draw_propensity * wealth_draw;
    }
    return Status::success();
}

void finalize_demographic_signal_year(const M7Rules &rules, M7TickScratch &scratch) {
    double real_wage = scratch.demographic_signal_last_real_wage_;
    if (scratch.demographic_signal_labor_sum_ > kLaborTolerance &&
        scratch.demographic_signal_price_sum_ > kLaborTolerance &&
        scratch.demographic_signal_days_ > 0U) {
        const double mean_price =
            scratch.demographic_signal_price_sum_ /
            static_cast<double>(scratch.demographic_signal_days_);
        real_wage = (scratch.demographic_signal_wage_sum_ /
                     scratch.demographic_signal_labor_sum_) /
                    mean_price;
        scratch.demographic_signal_last_real_wage_ = real_wage;
    }
    scratch.demographic_signal_wage_sum_ = 0.0;
    scratch.demographic_signal_labor_sum_ = 0.0;
    scratch.demographic_signal_price_sum_ = 0.0;
    scratch.demographic_signal_days_ = 0U;
    ++scratch.demographic_signal_years_completed_;
    if (real_wage <= kLaborTolerance ||
        scratch.demographic_signal_years_completed_ <=
            rules.demographic_feedback_burnin_years) {
        return;
    }
    if (scratch.demographic_signal_ewma_ <= kLaborTolerance) {
        scratch.demographic_signal_ewma_ = real_wage;
        scratch.demographic_signal_baseline_ = real_wage;
    } else {
        const double alpha =
            1.0 - std::pow(0.5, 1.0 / rules.demographic_signal_halflife_years);
        scratch.demographic_signal_ewma_ +=
            alpha * (real_wage - scratch.demographic_signal_ewma_);
    }
    scratch.demographic_signal_x_ =
        scratch.demographic_signal_ewma_ /
        std::max(kLaborTolerance, scratch.demographic_signal_baseline_);
    scratch.demographic_signal_fertility_multiplier_ =
        rules.fertility_income_elasticity > 0.0
            ? std::clamp(
                  std::pow(scratch.demographic_signal_x_,
                           -rules.fertility_income_elasticity),
                  rules.fertility_multiplier_minimum,
                  rules.fertility_multiplier_maximum)
            : 1.0;
    scratch.demographic_signal_mortality_multiplier_ =
        rules.mortality_income_elasticity > 0.0
            ? std::clamp(
                  std::pow(scratch.demographic_signal_x_,
                           -rules.mortality_income_elasticity),
                  rules.mortality_multiplier_minimum,
                  rules.mortality_multiplier_maximum)
            : 1.0;
}

struct FirmLaborTotals final {
    double effective_labor{0.0};
    double payroll{0.0};
};

[[nodiscard]] FirmLaborTotals firm_labor_totals(const core::EmploymentBook &employment,
                                                const core::PersonStore &persons,
                                                FirmId firm) noexcept {
    FirmLaborTotals totals;
    for (const auto job_id : employment.roster(firm)) {
        const auto *job = employment.get(job_id);
        if (job == nullptr || !job->active || job->suspended) {
            continue;
        }
        const auto *person = persons.get(job->person);
        if (person != nullptr && person->alive) {
            const double effective_labor = job->hours * person->efficiency;
            totals.effective_labor += effective_labor;
            totals.payroll += effective_labor * job->wage;
        }
    }
    return totals;
}

[[nodiscard]] double structural_participation_rate(const M7Rules &rules,
                                                   double age) noexcept {
    if (age < 25.0) {
        return rules.young_participation_rate;
    }
    if (age < 55.0) {
        return rules.prime_participation_rate;
    }
    return rules.older_participation_rate;
}

[[nodiscard]] bool structurally_participates(const M7Rules &rules, std::uint64_t seed,
                                             PersonId person, double age) noexcept {
    return !rules.age_participation ||
           unit_draw(seed, person.value(), 0, kParticipationStream) <
               structural_participation_rate(rules, age);
}

[[nodiscard]] Status
validate_vital_rates(const algorithms::VitalRates &rates) noexcept {
    const auto female = algorithms::female_birth_share(rates);
    if (!female.ok()) {
        return female.status();
    }
    const auto mortality = algorithms::survival_probability(rates, 40.0, kDailyYear);
    if (!mortality.ok()) {
        return mortality.status();
    }
    const auto fertility = algorithms::fertility_rate(rates, 28.0);
    return fertility.ok() ? Status::success() : fertility.status();
}

[[nodiscard]] std::vector<double>
stable_age_weights(const algorithms::VitalRates &rates) {
    std::vector<double> weights(static_cast<std::size_t>(rates.maximum_age) + 1U, 0.0);
    double survival = 1.0;
    for (std::uint32_t age = 0; age <= rates.maximum_age; ++age) {
        weights[age] = survival;
        if (age == rates.maximum_age) {
            break;
        }
        const auto next =
            algorithms::survival_probability(rates, static_cast<double>(age), 1.0);
        if (!next.ok()) {
            return {};
        }
        survival *= *next.get_if();
    }
    const double total = std::accumulate(weights.begin(), weights.end(), 0.0);
    if (!finite(total) || total <= 0.0) {
        return {};
    }
    for (auto &weight : weights) {
        weight /= total;
    }
    return weights;
}

[[nodiscard]] std::uint32_t sample_age(std::span<const double> weights,
                                       double draw) noexcept {
    double cumulative = 0.0;
    for (std::size_t age = 0; age < weights.size(); ++age) {
        cumulative += weights[age];
        if (draw < cumulative) {
            return static_cast<std::uint32_t>(age);
        }
    }
    return static_cast<std::uint32_t>(weights.size() - 1U);
}

[[nodiscard]] PersonId
first_alive_member(const core::HouseholdMembershipBook &membership,
                   const core::PersonStore &persons, HouseholdId household,
                   PersonId excluded) noexcept {
    PersonId selected{};
    for (const auto candidate : membership.members(household)) {
        if (candidate != excluded && persons.alive(candidate) &&
            (!selected.valid() || candidate < selected)) {
            selected = candidate;
        }
    }
    return selected;
}

[[nodiscard]] PersonId
first_alive_beneficial_owner(const core::BeneficialOwnershipBook &ownership,
                             const core::PersonStore &persons,
                             core::BeneficialAssetKey asset, PersonId excluded) {
    PersonId selected{};
    for (const auto lot_id : ownership.lots_for_asset(asset)) {
        const auto *lot = ownership.get(lot_id);
        if (lot == nullptr || !lot->is_active() || lot->owner == excluded ||
            !persons.alive(lot->owner)) {
            continue;
        }
        if (!selected.valid() || lot->owner < selected) {
            selected = lot->owner;
        }
    }
    return selected;
}

[[nodiscard]] double
beneficial_projection_error(const core::BeneficialOwnershipBook &ownership) {
    return ownership.maximum_projection_error();
}

[[nodiscard]] constexpr core::SecurityId
security_from_token(std::uint64_t token) noexcept {
    return {
        (token & 1U) == 0U ? core::SecurityKind::bond : core::SecurityKind::equity,
        static_cast<std::uint32_t>(token >> 1U),
    };
}

[[nodiscard]] bool
household_has_security_portfolio(const core::SecurityBook &securities,
                                 HouseholdId household) noexcept {
    for (const auto lot_id :
         securities.lots_for_holder(core::OwnerId::household(household))) {
        const auto *lot = securities.get(lot_id);
        if (lot != nullptr && lot->active() && lot->units > kLaborTolerance) {
            return true;
        }
    }
    return false;
}

[[nodiscard]] double
household_security_portfolio_value(const core::SecurityBook &securities,
                                   HouseholdId household) noexcept {
    double value = 0.0;
    for (const auto lot_id :
         securities.lots_for_holder(core::OwnerId::household(household))) {
        const auto *lot = securities.get(lot_id);
        if (lot == nullptr || !lot->active()) {
            continue;
        }
        if (lot->security.kind() == core::SecurityKind::equity) {
            const auto *contract = securities.get(EquityId(lot->security.value()));
            if (contract != nullptr && contract->active) {
                value += lot->units * contract->price.value();
            }
        } else {
            value += lot->units;
        }
    }
    return value;
}

[[nodiscard]] std::array<double, kWealthQuintiles>
wealth_rank_multipliers(double gradient,
                        const std::array<double, kWealthQuintiles> &exposure,
                        double minimum, double maximum) noexcept {
    std::array<double, kWealthQuintiles> multipliers{1.0, 1.0, 1.0, 1.0, 1.0};
    if (gradient == 0.0) {
        return multipliers;
    }
    const double total_exposure =
        std::accumulate(exposure.begin(), exposure.end(), 0.0);
    if (total_exposure <= 0.0) {
        return multipliers;
    }
    std::array<double, kWealthQuintiles> raw{};
    double weighted_total = 0.0;
    for (std::size_t bucket = 0; bucket < kWealthQuintiles; ++bucket) {
        const double rank =
            (static_cast<double>(bucket) + 0.5) /
            static_cast<double>(kWealthQuintiles);
        raw[bucket] = std::exp(gradient * (0.5 - rank));
        weighted_total += exposure[bucket] * raw[bucket];
    }
    const double weighted_mean = weighted_total / total_exposure;
    if (!finite(weighted_mean) || weighted_mean <= 0.0) {
        return multipliers;
    }
    for (std::size_t bucket = 0; bucket < kWealthQuintiles; ++bucket) {
        multipliers[bucket] =
            std::clamp(raw[bucket] / weighted_mean, minimum, maximum);
    }
    return multipliers;
}

[[nodiscard]] double
quintile_multiplier_stddev(
    const std::array<double, kWealthQuintiles> &multipliers) noexcept {
    const double mean =
        std::accumulate(multipliers.begin(), multipliers.end(), 0.0) /
        static_cast<double>(kWealthQuintiles);
    double variance = 0.0;
    for (const double value : multipliers) {
        variance += (value - mean) * (value - mean);
    }
    return std::sqrt(variance / static_cast<double>(kWealthQuintiles));
}

[[nodiscard]] Status refresh_wealth_stratification(
    const core::RootState &state, const M7Rules &rules,
    const core::PersonStore &persons, const M4TickScratch &real,
    const M5TickScratch &monetary, const M6TickScratch &financial,
    std::int32_t calendar_day, M7TickScratch &scratch) {
    const auto identity_count = real.household_dense_index_.size();
    scratch.household_wealth_quintile_.assign(identity_count,
                                              kUnrankedWealthQuintile);
    scratch.household_mortality_multiplier_.assign(identity_count, 1.0);
    scratch.household_fertility_multiplier_.assign(identity_count, 1.0);

    std::vector<double> net_wealth(real.household_ids_.size(), 0.0);
    std::vector<double> need_units(real.household_ids_.size(), 0.0);
    for (std::size_t index = 0; index < real.household_ids_.size(); ++index) {
        const auto *household = state.households.get(real.household_ids_[index]);
        if (household == nullptr) {
            return Status(ErrorCode::invariant_violation,
                          "M7 wealth-rank household is absent");
        }
        const auto account =
            static_cast<std::size_t>(household->primary_account.value());
        if (account >= real.balances_.size()) {
            return Status(ErrorCode::invariant_violation,
                          "M7 wealth-rank account is stale");
        }
        net_wealth[index] = real.balances_[account];
        if (account < monetary.debt_by_account_.size()) {
            net_wealth[index] -= monetary.debt_by_account_[account];
        }
    }
    for (const auto &lot : financial.securities_.lots()) {
        if (!lot.active() || lot.holder.kind() != core::OwnerKind::household) {
            continue;
        }
        const auto identity = static_cast<std::size_t>(lot.holder.value());
        const auto index = identity < real.household_dense_index_.size()
                               ? real.household_dense_index_[identity]
                               : std::numeric_limits<std::size_t>::max();
        if (index >= net_wealth.size()) {
            continue;
        }
        if (lot.security.kind() == core::SecurityKind::equity) {
            const auto *contract =
                financial.securities_.get(EquityId(lot.security.value()));
            if (contract != nullptr && contract->active) {
                net_wealth[index] += lot.units * contract->price.value();
            }
        } else {
            const auto *contract =
                financial.securities_.get(BondId(lot.security.value()));
            if (contract != nullptr && contract->active) {
                net_wealth[index] += lot.units;
            }
        }
    }
    for (const auto person_id : persons.alive_ids()) {
        const auto *person = persons.get(person_id);
        const auto identity = static_cast<std::size_t>(person->household.value());
        const auto index = identity < real.household_dense_index_.size()
                               ? real.household_dense_index_[identity]
                               : std::numeric_limits<std::size_t>::max();
        if (index >= need_units.size()) {
            continue;
        }
        const double age = completed_age(*person, calendar_day);
        need_units[index] += age < 18.0 ? 0.65 : (age >= 65.0 ? 0.90 : 1.0);
    }

    struct RankedHousehold final {
        double wealth_per_need{0.0};
        HouseholdId household{};
        std::size_t dense_index{0};
    };
    std::vector<RankedHousehold> ranked;
    ranked.reserve(real.household_ids_.size());
    for (std::size_t index = 0; index < real.household_ids_.size(); ++index) {
        if (need_units[index] <= 0.0) {
            continue;
        }
        ranked.push_back({net_wealth[index] / need_units[index],
                          real.household_ids_[index], index});
    }
    std::sort(ranked.begin(), ranked.end(),
              [](const RankedHousehold &left, const RankedHousehold &right) {
                  if (left.wealth_per_need != right.wealth_per_need) {
                      return left.wealth_per_need < right.wealth_per_need;
                  }
                  return left.household < right.household;
              });
    for (std::size_t rank = 0; rank < ranked.size(); ++rank) {
        const auto bucket = static_cast<std::uint8_t>(std::min<std::size_t>(
            kWealthQuintiles - 1U, rank * kWealthQuintiles / ranked.size()));
        const auto identity =
            static_cast<std::size_t>(ranked[rank].household.value());
        if (identity < scratch.household_wealth_quintile_.size()) {
            scratch.household_wealth_quintile_[identity] = bucket;
        }
    }

    std::array<double, kWealthQuintiles> mortality_exposure{};
    std::array<double, kWealthQuintiles> fertility_exposure{};
    for (const auto person_id : persons.alive_ids()) {
        const auto *person = persons.get(person_id);
        const auto identity = static_cast<std::size_t>(person->household.value());
        if (identity >= scratch.household_wealth_quintile_.size()) {
            continue;
        }
        const auto bucket = scratch.household_wealth_quintile_[identity];
        if (bucket >= kWealthQuintiles) {
            continue;
        }
        const double age = completed_age(*person, calendar_day);
        if (age >= static_cast<double>(rules.vital_rates.maximum_age)) {
            mortality_exposure[bucket] += 1.0;
        } else {
            const auto survival = algorithms::survival_probability(
                rules.vital_rates, age, kDailyYear);
            if (!survival.ok()) {
                return survival.status();
            }
            mortality_exposure[bucket] += 1.0 - *survival.get_if();
        }
        if (person->sex == core::PersonSex::female && age >= 15.0 && age <= 49.0) {
            const auto fertility = algorithms::fertility_rate(rules.vital_rates, age);
            if (!fertility.ok()) {
                return fertility.status();
            }
            fertility_exposure[bucket] += *fertility.get_if();
        }
    }
    scratch.mortality_quintile_multiplier_ = wealth_rank_multipliers(
        rules.mortality_rank_gradient, mortality_exposure,
        rules.stratification_multiplier_minimum,
        rules.stratification_multiplier_maximum);
    scratch.fertility_quintile_multiplier_ = wealth_rank_multipliers(
        rules.fertility_rank_gradient, fertility_exposure,
        rules.stratification_multiplier_minimum,
        rules.stratification_multiplier_maximum);
    for (const auto &entry : ranked) {
        const auto identity = static_cast<std::size_t>(entry.household.value());
        const auto bucket = scratch.household_wealth_quintile_[identity];
        scratch.household_mortality_multiplier_[identity] =
            scratch.mortality_quintile_multiplier_[bucket];
        scratch.household_fertility_multiplier_[identity] =
            scratch.fertility_quintile_multiplier_[bucket];
    }
    scratch.stratification_snapshot_day_ = calendar_day;
    return Status::success();
}

[[nodiscard]] double household_rank_multiplier(
    HouseholdId household, std::span<const double> multipliers) noexcept {
    const auto identity = static_cast<std::size_t>(household.value());
    return identity < multipliers.size() ? multipliers[identity] : 1.0;
}

[[nodiscard]] std::uint8_t household_wealth_quintile(
    HouseholdId household, std::span<const std::uint8_t> quintiles) noexcept {
    const auto identity = static_cast<std::size_t>(household.value());
    return identity < quintiles.size() ? quintiles[identity]
                                       : kUnrankedWealthQuintile;
}

[[nodiscard]] Status create_equal_claims(
    core::BeneficialAssetKey asset, const core::HouseholdMembershipBook &membership,
    const core::PersonStore &persons, core::BeneficialOwnershipBook &ownership,
    bool refresh_presence = false) {
    const bool present = refresh_presence ? ownership.touch_asset_presence(asset)
                                          : ownership.contains_asset(asset);
    if (present) {
        return Status::success();
    }
    std::size_t alive_members = 0;
    for (const auto person : membership.members(asset.household)) {
        alive_members += persons.alive(person) ? 1U : 0U;
    }
    if (alive_members == 0) {
        const core::BeneficialAssetKey cash{
            core::BeneficialAssetKind::household_cash,
            asset.household,
            asset.household.value(),
        };
        double projected = 0.0;
        for (const auto lot_id : ownership.lots_for_asset(cash)) {
            const auto *lot = ownership.get(lot_id);
            if (lot == nullptr || !lot->is_active() || !persons.alive(lot->owner)) {
                continue;
            }
            const auto owner = lot->owner;
            const double share = lot->share;
            const auto created = ownership.create_lot(asset, owner, share);
            if (!created.ok()) {
                return created.status();
            }
            projected += share;
        }
        if (projected < 1.0 - kLaborTolerance) {
            return Status(ErrorCode::invariant_violation,
                          "empty household has no beneficial owner");
        }
        return !refresh_presence || ownership.touch_asset_presence(asset)
                   ? Status::success()
                   : Status(ErrorCode::invariant_violation,
                            "beneficial asset refresh is inconsistent");
    }
    const double share = 1.0 / static_cast<double>(alive_members);
    for (const auto person : membership.members(asset.household)) {
        if (!persons.alive(person)) {
            continue;
        }
        const auto lot = ownership.create_lot(asset, person, share);
        if (!lot.ok()) {
            return lot.status();
        }
    }
    return !refresh_presence || ownership.touch_asset_presence(asset)
               ? Status::success()
               : Status(ErrorCode::invariant_violation,
                        "beneficial asset refresh is inconsistent");
}

[[nodiscard]] const core::LoanRecord *
find_loan(const std::vector<core::LoanRecord> &loans, LoanId id) noexcept {
    if (!id.valid() || id.value() > loans.size()) {
        return nullptr;
    }
    const auto &loan = loans[static_cast<std::size_t>(id.value() - 1U)];
    return loan.id == id ? &loan : nullptr;
}

[[nodiscard]] bool canonical_claim_exists(const core::RootState &state,
                                          const M4TickScratch &real,
                                          const std::vector<core::LoanRecord> &loans,
                                          const core::SecurityBook &securities,
                                          core::BeneficialAssetKey asset) noexcept {
    const auto *household = state.households.get(asset.household);
    if (household == nullptr) {
        return false;
    }
    switch (asset.kind) {
    case core::BeneficialAssetKind::household_cash:
        return household->primary_account.value() < real.balances_.size();
    case core::BeneficialAssetKind::household_debt: {
        const auto *loan = find_loan(loans, LoanId(asset.value));
        return loan != nullptr && loan->active &&
               loan->borrower == core::OwnerId::household(asset.household);
    }
    case core::BeneficialAssetKind::security_position:
        if (asset.value == 0U) {
            return household_has_security_portfolio(securities, asset.household);
        }
        return securities.units_held(security_from_token(asset.value),
                                     core::OwnerId::household(asset.household)) >
               kLaborTolerance;
    case core::BeneficialAssetKind::generic_position:
        return true;
    }
    return false;
}

[[nodiscard]] Status synchronize_beneficial_claims(
    const core::RootState &state, const M4TickScratch &real,
    const std::vector<core::LoanRecord> &loans, core::SecurityBook &securities,
    const core::HouseholdMembershipBook &membership, const core::PersonStore &persons,
    core::BeneficialOwnershipBook &ownership,
    std::vector<core::BeneficialAssetKey> &asset_buffer) {
    Status status = Status::success();
    state.households.for_each_alive(
        [&](HouseholdId household, const core::HouseholdComponent &) {
            if (!status.ok() || membership.members(household).empty()) {
                return;
            }
            status = create_equal_claims(
                {
                    core::BeneficialAssetKind::household_cash,
                    household,
                    household.value(),
                },
                membership, persons, ownership);
        });
    if (!status.ok()) {
        return status;
    }
    asset_buffer.clear();
    asset_buffer.reserve(securities.household_position_changes().size());
    for (const auto &change : securities.household_position_changes()) {
        asset_buffer.push_back({
            core::BeneficialAssetKind::security_position,
            HouseholdId(change.holder.value()),
            0U,
        });
    }
    std::sort(asset_buffer.begin(), asset_buffer.end());
    asset_buffer.erase(std::unique(asset_buffer.begin(), asset_buffer.end()),
                       asset_buffer.end());
    for (const auto asset : asset_buffer) {
        if (household_has_security_portfolio(securities, asset.household)) {
            status = create_equal_claims(asset, membership, persons, ownership);
        } else if (ownership.contains_asset(asset)) {
            status = ownership.retire_asset(asset);
        }
        if (!status.ok()) {
            return status;
        }
    }
    for (const auto &loan : loans) {
        if (!loan.active || loan.borrower.kind() != core::OwnerKind::household) {
            continue;
        }
        const auto household = HouseholdId(loan.borrower.value());
        status = create_equal_claims(
            {
                core::BeneficialAssetKind::household_debt,
                household,
                loan.id.value(),
            },
            membership, persons, ownership);
        if (!status.ok()) {
            return status;
        }
    }

    ownership.active_assets_except(core::BeneficialAssetKind::security_position,
                                   asset_buffer);
    for (const auto asset : asset_buffer) {
        if (canonical_claim_exists(state, real, loans, securities, asset)) {
            continue;
        }
        status = ownership.retire_asset(asset);
        if (!status.ok()) {
            return status;
        }
    }
    securities.clear_household_position_changes();
    return Status::success();
}

[[nodiscard]] PersonId select_heir(const core::PersonStore &persons,
                                   const core::HouseholdMembershipBook &membership,
                                   const core::RelationshipBook &relationships,
                                   const core::PersonRecord &deceased) noexcept {
    if (persons.alive(deceased.partner)) {
        return deceased.partner;
    }
    for (const auto child : relationships.children(deceased.id)) {
        if (persons.alive(child)) {
            return child;
        }
    }
    for (const auto parent : std::array{deceased.mother, deceased.father}) {
        if (persons.alive(parent)) {
            return parent;
        }
    }
    const auto household_heir =
        first_alive_member(membership, persons, deceased.household, deceased.id);
    return household_heir;
}

[[nodiscard]] double claim_value(const core::RootState &state,
                                 const M4TickScratch &real,
                                 const std::vector<core::LoanRecord> &loans,
                                 const core::SecurityBook &securities,
                                 core::BeneficialAssetKey asset) noexcept {
    const auto *household = state.households.get(asset.household);
    if (household == nullptr) {
        return 0.0;
    }
    switch (asset.kind) {
    case core::BeneficialAssetKind::household_cash: {
        const auto index = static_cast<std::size_t>(household->primary_account.value());
        return index < real.balances_.size() ? std::max(0.0, real.balances_[index])
                                             : 0.0;
    }
    case core::BeneficialAssetKind::household_debt: {
        const auto *loan = find_loan(loans, LoanId(asset.value));
        return loan != nullptr && loan->active ? std::max(0.0, loan->principal.value())
                                               : 0.0;
    }
    case core::BeneficialAssetKind::security_position: {
        if (asset.value == 0U) {
            return household_security_portfolio_value(securities, asset.household);
        }
        const auto security = security_from_token(asset.value);
        const double units =
            securities.units_held(security, core::OwnerId::household(asset.household));
        if (security.kind() == core::SecurityKind::equity) {
            const auto *contract = securities.get(EquityId(security.value()));
            return contract == nullptr ? 0.0 : units * contract->price.value();
        }
        return units;
    }
    case core::BeneficialAssetKind::generic_position:
        return 0.0;
    }
    return 0.0;
}

void record_head_separation(core::SeparationKind kind,
                            core::LaborAccounts &accounts) noexcept {
    switch (kind) {
    case core::SeparationKind::churn:
        accounts.churn_separations_total += 1.0;
        break;
    case core::SeparationKind::demand_layoff:
        accounts.layoff_separations_total += 1.0;
        break;
    case core::SeparationKind::cash_layoff:
        accounts.cash_layoffs_total += 1.0;
        accounts.layoff_separations_total += 1.0;
        break;
    case core::SeparationKind::firm_exit:
        accounts.firm_exit_separations_total += 1.0;
        break;
    case core::SeparationKind::death:
        accounts.death_separations_total += 1.0;
        break;
    case core::SeparationKind::retirement:
        accounts.retirement_separations_total += 1.0;
        break;
    case core::SeparationKind::welfare_quit:
        accounts.welfare_quits_total += 1.0;
        break;
    case core::SeparationKind::job_to_job:
        accounts.job_to_job_moves_total += 1.0;
        break;
    }
}

[[nodiscard]] double annual_marriage_entry_rate(
    const core::PersonRecord &person, const M7Rules &rules,
    std::int32_t day) noexcept {
    const double age = completed_age(person, day);
    double profile_multiplier = 1.0;
    if (rules.social_union_target_profile.enabled) {
        const double maximum = *std::max_element(
            rules.social_union_target_profile.shares.begin(),
            rules.social_union_target_profile.shares.end());
        profile_multiplier = maximum <= 0.0
                                 ? 0.0
                                 : union_target_share(
                                       rules.social_union_target_profile, age) /
                                       maximum;
    } else {
        const double z = (age - rules.marriage_peak_age) /
                         rules.marriage_age_width;
        profile_multiplier = std::exp(-0.5 * z * z);
    }
    double rate = rules.annual_marriage_rate * profile_multiplier;
    if (person.marriage_count > 0U || person.last_divorce_day >= 0) {
        rate *= rules.remarriage_rate_multiplier;
    }
    if (person.last_widowed_day >= 0) {
        rate *= rules.widowed_remarriage_multiplier;
    }
    return std::clamp(rate, 0.0, 1.0);
}

[[nodiscard]] bool union_has_minor_child(
    const core::PersonStore &persons,
    const core::RelationshipBook &relationships,
    const core::UnionRecord &record, std::int32_t day) noexcept {
    for (const auto parent : std::array{record.first, record.second}) {
        for (const auto child : relationships.children(parent)) {
            const auto *person = persons.get(child);
            if (person != nullptr && person->alive &&
                completed_age(*person, day) < 18.0) {
                return true;
            }
        }
    }
    return false;
}

[[nodiscard]] double annual_divorce_hazard(
    const core::PersonStore &persons,
    const core::RelationshipBook &relationships,
    const core::UnionRecord &record, const M7Rules &rules,
    std::int32_t day) noexcept {
    const double duration_years = std::max(
        0.0, static_cast<double>(day - record.start_day) / kDaysPerYear);
    const double duration_z =
        (duration_years - rules.divorce_peak_duration_years) /
        rules.divorce_duration_width;
    const double duration_peak = std::exp(-0.5 * duration_z * duration_z);
    double rate = rules.annual_divorce_rate *
                  (1.0 + (rules.divorce_peak_multiplier - 1.0) *
                             duration_peak);
    if (union_has_minor_child(persons, relationships, record, day)) {
        rate *= rules.divorce_child_multiplier;
    }
    const auto *first = persons.get(record.first);
    const auto *second = persons.get(record.second);
    if (first != nullptr && second != nullptr) {
        const double age_gap = std::abs(completed_age(*first, day) -
                                        completed_age(*second, day));
        rate *= std::pow(rules.divorce_age_gap_multiplier_per_10y,
                         age_gap / 10.0);
    }
    return std::clamp(rate, 0.0, 1.0);
}

[[nodiscard]] Status separate_job(core::EmploymentBook &employment, JobId job_id,
                                  std::int32_t day, core::SeparationKind kind,
                                  core::LaborAccounts &accounts);

void measure_population(const core::RootState &state, const M7Rules &rules,
                        const core::PersonStore &persons,
                        const core::HouseholdMembershipBook &membership,
                        const core::RelationshipBook &relationships, std::int32_t day,
                        M7Metrics &metrics) {
    metrics.population = persons.alive_count();
    std::uint64_t working = 0;
    std::uint64_t dependents = 0;
    std::uint64_t adults = 0;
    std::uint64_t partnered_adults = 0;
    std::uint64_t minors = 0;
    std::uint64_t dual_parent_minors = 0;
    std::uint64_t guardian_only_minors = 0;
    std::uint64_t mothers = 0;
    std::uint64_t fathers = 0;
    double mother_gap_sum = 0.0;
    double mother_gap_square_sum = 0.0;
    double father_gap_sum = 0.0;
    double father_gap_square_sum = 0.0;
    for (const auto id : persons.alive_ids()) {
        const auto *person = persons.get(id);
        const double age = completed_age(*person, day);
        if (age >= static_cast<double>(rules.working_age)) {
            ++adults;
            partnered_adults += person->partner.valid() ? 1U : 0U;
        } else {
            ++minors;
            const bool has_mother = persons.alive(person->mother);
            const bool has_father = persons.alive(person->father);
            dual_parent_minors += has_mother && has_father ? 1U : 0U;
            guardian_only_minors +=
                !has_mother && !has_father && persons.alive(person->guardian)
                    ? 1U
                    : 0U;
            if (has_mother) {
                const double gap =
                    completed_age(*persons.get(person->mother), day) - age;
                mother_gap_sum += gap;
                mother_gap_square_sum += gap * gap;
                ++mothers;
            }
            if (has_father) {
                const double gap =
                    completed_age(*persons.get(person->father), day) - age;
                father_gap_sum += gap;
                father_gap_square_sum += gap * gap;
                ++fathers;
            }
        }
        if (age >= static_cast<double>(rules.working_age) &&
            age < static_cast<double>(rules.retirement_age)) {
            ++working;
        } else {
            ++dependents;
        }
    }
    std::uint64_t active_households = 0;
    metrics.maximum_household_size = 0U;
    state.households.for_each_alive(
        [&](HouseholdId household, const core::HouseholdComponent &) {
            const auto member_count = membership.members(household).size();
            if (member_count > 0U) {
                ++active_households;
                metrics.maximum_household_size = std::max(
                    metrics.maximum_household_size,
                    static_cast<std::uint64_t>(member_count));
            }
        });
    metrics.households_with_members = active_households;
    metrics.mean_household_size = active_households == 0
                                      ? 0.0
                                      : static_cast<double>(metrics.population) /
                                            static_cast<double>(active_households);
    metrics.working_age_share =
        metrics.population == 0
            ? 0.0
            : static_cast<double>(working) / static_cast<double>(metrics.population);
    metrics.dependency_ratio =
        working == 0 ? static_cast<double>(dependents)
                     : static_cast<double>(dependents) / static_cast<double>(working);
    metrics.partnered_adult_share =
        adults == 0U ? 0.0
                     : static_cast<double>(partnered_adults) /
                           static_cast<double>(adults);
    metrics.dual_parent_minor_share =
        minors == 0U ? 0.0
                     : static_cast<double>(dual_parent_minors) /
                           static_cast<double>(minors);
    metrics.guardian_only_minor_share =
        minors == 0U ? 0.0
                     : static_cast<double>(guardian_only_minors) /
                           static_cast<double>(minors);
    metrics.mean_mother_age_gap =
        mothers == 0U ? 0.0 : mother_gap_sum / static_cast<double>(mothers);
    metrics.mother_age_gap_stddev =
        mothers == 0U
            ? 0.0
            : std::sqrt(std::max(
                  0.0, mother_gap_square_sum / static_cast<double>(mothers) -
                           metrics.mean_mother_age_gap *
                               metrics.mean_mother_age_gap));
    metrics.mean_father_age_gap =
        fathers == 0U ? 0.0 : father_gap_sum / static_cast<double>(fathers);
    metrics.father_age_gap_stddev =
        fathers == 0U
            ? 0.0
            : std::sqrt(std::max(
                  0.0, father_gap_square_sum / static_cast<double>(fathers) -
                           metrics.mean_father_age_gap *
                               metrics.mean_father_age_gap));
    double efficiency_sum = 0.0;
    double efficiency_square_sum = 0.0;
    for (const auto id : persons.alive_ids()) {
        const double efficiency = persons.get(id)->efficiency;
        efficiency_sum += efficiency;
        efficiency_square_sum += efficiency * efficiency;
    }
    const double population = static_cast<double>(metrics.population);
    metrics.mean_person_efficiency =
        population <= 0.0 ? 0.0 : efficiency_sum / population;
    metrics.person_efficiency_stddev =
        population <= 0.0
            ? 0.0
            : std::sqrt(std::max(0.0, efficiency_square_sum / population -
                                          metrics.mean_person_efficiency *
                                              metrics.mean_person_efficiency));
    metrics.active_unions = 0;
    metrics.mean_partner_age_gap = 0.0;
    metrics.mean_partner_log_efficiency_gap = 0.0;
    for (const auto &union_record : relationships.unions()) {
        if (!union_record.active) {
            continue;
        }
        const auto *first = persons.get(union_record.first);
        const auto *second = persons.get(union_record.second);
        if (first == nullptr || second == nullptr || !first->alive || !second->alive) {
            continue;
        }
        ++metrics.active_unions;
        metrics.mean_partner_age_gap +=
            std::abs(completed_age(*first, day) - completed_age(*second, day));
        metrics.mean_partner_log_efficiency_gap +=
            std::abs(std::log(first->efficiency) - std::log(second->efficiency));
    }
    if (metrics.active_unions > 0U) {
        const double denominator = static_cast<double>(metrics.active_unions);
        metrics.mean_partner_age_gap /= denominator;
        metrics.mean_partner_log_efficiency_gap /= denominator;
    }
}

[[nodiscard]] Status transfer_household_residual(
    const core::RootState &state, M4TickScratch &real, M5TickScratch &monetary,
    M6TickScratch &financial, core::BeneficialOwnershipBook &ownership,
    HouseholdId source_household, HouseholdId destination_household,
    std::vector<core::SecurityId> &security_buffer) {
    const auto *source = state.households.get(source_household);
    const auto *destination = state.households.get(destination_household);
    if (source == nullptr ||
        (destination_household.valid() && destination == nullptr)) {
        return Status(ErrorCode::invariant_violation,
                      "estate household reference is absent");
    }
    const auto source_owner = core::OwnerId::household(source_household);
    const auto destination_owner =
        destination_household.valid()
            ? core::OwnerId::household(destination_household)
            : core::OwnerId::institutional(core::OwnerKind::treasury);
    const auto destination_account = destination_household.valid()
                                         ? destination->primary_account
                                         : state.institutions.treasury_account;

    security_buffer.clear();
    for (const auto lot_id : financial.securities_.lots_for_holder(source_owner)) {
        const auto *lot = financial.securities_.get(lot_id);
        if (lot != nullptr && lot->active()) {
            security_buffer.push_back(lot->security);
        }
    }
    std::sort(security_buffer.begin(), security_buffer.end());
    security_buffer.erase(std::unique(security_buffer.begin(), security_buffer.end()),
                          security_buffer.end());
    auto status = financial.securities_.begin_batch();
    if (!status.ok()) {
        return status;
    }
    for (const auto security : security_buffer) {
        const double units = financial.securities_.units_held(security, source_owner);
        double cost_basis = 0.0;
        for (const auto lot_id : financial.securities_.lots_for_holder(source_owner)) {
            const auto *lot = financial.securities_.get(lot_id);
            if (lot != nullptr && lot->active() && lot->security == security) {
                cost_basis += lot->cost_basis.value();
            }
        }
        if (units <= 0.0) {
            continue;
        }
        status = financial.securities_.transfer_units(
            security, source_owner, destination_owner, units, Money(cost_basis));
        if (!status.ok()) {
            return status;
        }
    }
    status = financial.securities_.finish_batch();
    if (!status.ok()) {
        return status;
    }
    for (auto &loan : monetary.loans_) {
        if (!loan.active || loan.borrower != source_owner) {
            continue;
        }
        const auto old_index = static_cast<std::size_t>(loan.borrower_account.value());
        const auto new_index = static_cast<std::size_t>(destination_account.value());
        if (old_index < monetary.debt_by_account_.size()) {
            monetary.debt_by_account_[old_index] -= loan.principal.value();
        }
        if (new_index < monetary.debt_by_account_.size()) {
            monetary.debt_by_account_[new_index] += loan.principal.value();
        }
        loan.borrower = destination_owner;
        loan.borrower_account = destination_account;
    }
    const auto source_index = static_cast<std::size_t>(source->primary_account.value());
    const double residual_cash = source_index < real.balances_.size()
                                     ? std::max(0.0, real.balances_[source_index])
                                     : 0.0;
    if (residual_cash > kLaborTolerance) {
        status = stage_m4_transfer(state, real, source->primary_account,
                                   destination_account, residual_cash);
        if (!status.ok()) {
            return status;
        }
    }
    if (destination_household.valid()) {
        if (destination_household == source_household) {
            return Status(ErrorCode::invariant_violation,
                          "estate destination aliases source household");
        }
        const core::BeneficialAssetKey source_portfolio{
            core::BeneficialAssetKind::security_position,
            source_household,
            0U,
        };
        const core::BeneficialAssetKey destination_portfolio{
            core::BeneficialAssetKind::security_position,
            destination_household,
            0U,
        };
        if (ownership.contains_asset(source_portfolio) &&
            ownership.contains_asset(destination_portfolio)) {
            status = ownership.retire_asset(source_portfolio);
            if (!status.ok()) {
                return status;
            }
        }
    }
    return destination_household.valid()
               ? ownership.rekey_household(source_household, destination_household)
               : ownership.retire_household(source_household);
}

[[nodiscard]] Status settle_death(
    const core::RootState &state, M4TickScratch &real, M5TickScratch &monetary,
    M6TickScratch &financial, core::PersonStore &persons,
    core::HouseholdMembershipBook &membership, core::BeneficialOwnershipBook &ownership,
    core::EmploymentBook &employment, core::RelationshipBook &relationships,
    core::LaborAccounts &labor_accounts, std::vector<EstateRecord> &estates,
    std::vector<HouseholdId> &retired_households, std::uint64_t &next_event_id,
    PersonId deceased, std::int32_t day, const M7PolicyState &policy,
    const M7Rules &rules, M7Metrics &metrics,
    std::vector<std::uint32_t> &guardian_heads,
    std::vector<std::uint32_t> &guardian_next, std::vector<BeneficialLotId> &lot_buffer,
    std::vector<core::SecurityId> &security_buffer) {
    auto *record = persons.get(deceased);
    if (record == nullptr || !record->alive) {
        return Status(ErrorCode::contract_violation, "death target is not alive");
    }
    const auto household = record->household;
    const auto heir = select_heir(persons, membership, relationships, *record);
    const auto destination_household =
        heir.valid() ? persons.get(heir)->household : HouseholdId{};
    const bool last_household_member = membership.members(household).size() == 1U;
    const bool was_partnered = record->partner.valid();
    auto relationship_status = relationships.widow(persons, deceased, day);
    if (!relationship_status.ok()) {
        return relationship_status;
    }
    if (was_partnered) {
        ++metrics.widowhoods;
    }
    auto encoded_ward = deceased.value() < guardian_heads.size()
                            ? guardian_heads[static_cast<std::size_t>(deceased.value())]
                            : 0U;
    if (deceased.value() < guardian_heads.size()) {
        guardian_heads[static_cast<std::size_t>(deceased.value())] = 0U;
    }
    while (encoded_ward != 0U) {
        const auto person_id = PersonId(encoded_ward);
        const auto person_index = static_cast<std::size_t>(encoded_ward);
        const auto next_ward =
            person_index < guardian_next.size() ? guardian_next[person_index] : 0U;
        if (person_index < guardian_next.size()) {
            guardian_next[person_index] = 0U;
        }
        auto *dependent = persons.get(person_id);
        if (dependent == nullptr || !dependent->alive ||
            dependent->guardian != deceased) {
            encoded_ward = next_ward;
            continue;
        }
        PersonId replacement{};
        enum class GuardianRoute : std::uint8_t {
            none,
            parent,
            grandparent,
            adult_sibling,
            same_household,
        };
        auto route = GuardianRoute::none;
        const auto eligible_guardian = [&](PersonId candidate) {
            if (!persons.alive(candidate) || candidate == deceased ||
                candidate == dependent->id) {
                return false;
            }
            const auto *candidate_record = persons.get(candidate);
            return candidate_record != nullptr &&
                   completed_age(*candidate_record, day) >=
                       static_cast<double>(rules.working_age) &&
                   membership.members(candidate_record->household).size() <
                       static_cast<std::size_t>(
                           rules.guardian_maximum_household_size);
        };
        for (const auto parent : std::array{dependent->mother, dependent->father}) {
            if (eligible_guardian(parent)) {
                replacement = parent;
                route = GuardianRoute::parent;
                break;
            }
        }
        if (!replacement.valid() && rules.guardian_search_grandparents) {
            for (const auto parent_id :
                 std::array{dependent->mother, dependent->father}) {
                const auto *parent = persons.get(parent_id);
                if (parent == nullptr) {
                    continue;
                }
                for (const auto grandparent :
                     std::array{parent->mother, parent->father}) {
                    if (eligible_guardian(grandparent)) {
                        replacement = grandparent;
                        route = GuardianRoute::grandparent;
                        break;
                    }
                }
                if (replacement.valid()) {
                    break;
                }
            }
        }
        if (!replacement.valid() && rules.guardian_search_adult_siblings) {
            for (const auto parent_id :
                 std::array{dependent->mother, dependent->father}) {
                if (!parent_id.valid()) {
                    continue;
                }
                for (const auto sibling : relationships.children(parent_id)) {
                    if (eligible_guardian(sibling)) {
                        replacement = sibling;
                        route = GuardianRoute::adult_sibling;
                        break;
                    }
                }
                if (replacement.valid()) {
                    break;
                }
            }
        }
        if (!replacement.valid() &&
            rules.guardian_search_same_household_adults) {
            for (const auto candidate : membership.members(dependent->household)) {
                if (eligible_guardian(candidate)) {
                    replacement = candidate;
                    route = GuardianRoute::same_household;
                    break;
                }
            }
        }
        dependent->guardian = replacement;
        switch (route) {
        case GuardianRoute::parent:
            ++metrics.guardian_parent_assignments;
            break;
        case GuardianRoute::grandparent:
            ++metrics.guardian_grandparent_assignments;
            break;
        case GuardianRoute::adult_sibling:
            ++metrics.guardian_adult_sibling_assignments;
            break;
        case GuardianRoute::same_household:
            ++metrics.guardian_same_household_assignments;
            break;
        case GuardianRoute::none:
            ++metrics.guardian_unresolved_assignments;
            break;
        }
        if (replacement.valid() && replacement.value() < guardian_heads.size() &&
            person_index < guardian_next.size()) {
            const auto replacement_index =
                static_cast<std::size_t>(replacement.value());
            guardian_next[person_index] = guardian_heads[replacement_index];
            guardian_heads[replacement_index] =
                static_cast<std::uint32_t>(person_id.value());
        }
        encoded_ward = next_ward;
    }
    const auto deceased_claims = ownership.lots_for_person(deceased);
    lot_buffer.assign(deceased_claims.begin(), deceased_claims.end());
    EstateRecord estate;
    estate.event = EventId(next_event_id++);
    estate.deceased = deceased;
    estate.heir = heir;
    estate.household = household;
    estate.destination_household = destination_household;
    estate.opened_day = day;
    estate.settled_day = day;
    estate.settled = true;
    const auto first_orphan_household = retired_households.size();
    for (const auto lot_id : lot_buffer) {
        const auto *lot = ownership.get(lot_id);
        if (lot == nullptr || !lot->is_active()) {
            return Status(ErrorCode::invariant_violation,
                          "estate references an absent beneficial lot");
        }
        estate.gross_share += lot->share;
        const double value =
            lot->share * claim_value(state, real, monetary.loans_,
                                     financial.securities_, lot->asset);
        if (lot->asset.kind == core::BeneficialAssetKind::household_debt) {
            estate.liabilities += value;
        } else {
            estate.gross_value += value;
        }
        PersonId beneficiary = heir;
        if (!beneficiary.valid()) {
            beneficiary =
                first_alive_beneficial_owner(ownership, persons, lot->asset, deceased);
        }
        if (!beneficiary.valid() &&
            lot->asset.kind != core::BeneficialAssetKind::household_cash) {
            const core::BeneficialAssetKey cash{
                core::BeneficialAssetKind::household_cash,
                lot->asset.household,
                lot->asset.household.value(),
            };
            beneficiary =
                first_alive_beneficial_owner(ownership, persons, cash, deceased);
        }
        if (!beneficiary.valid()) {
            beneficiary =
                first_alive_member(membership, persons, lot->asset.household, deceased);
        }
        if (!beneficiary.valid() && lot->asset.household != household &&
            membership.members(lot->asset.household).empty() &&
            state.households.get(lot->asset.household) != nullptr &&
            std::find(retired_households.begin(), retired_households.end(),
                      lot->asset.household) == retired_households.end()) {
            retired_households.push_back(lot->asset.household);
        }
        const auto status = beneficiary.valid()
                                ? ownership.transfer(lot_id, beneficiary, lot->share)
                                : ownership.retire(lot_id);
        if (!status.ok()) {
            return status;
        }
        ++estate.transferred_lots;
    }
    for (auto index = first_orphan_household; index < retired_households.size();
         ++index) {
        const auto orphan = retired_households[index];
        const auto residual_status =
            transfer_household_residual(state, real, monetary, financial, ownership,
                                        orphan, HouseholdId{}, security_buffer);
        if (!residual_status.ok()) {
            return residual_status;
        }
    }
    estate.tax_share = estate.gross_share * policy.inheritance_tax_rate;
    const auto *source_household = state.households.get(household);
    if (source_household == nullptr) {
        return Status(ErrorCode::invariant_violation, "estate household is absent");
    }
    const double taxable_value = std::max(0.0, estate.gross_value - estate.liabilities);
    const auto source_account = source_household->primary_account;
    const auto source_index = static_cast<std::size_t>(source_account.value());
    const double available_cash = source_index < real.balances_.size()
                                      ? std::max(0.0, real.balances_[source_index])
                                      : 0.0;
    estate.tax_paid =
        std::min(available_cash, taxable_value * policy.inheritance_tax_rate);
    if (estate.tax_paid > kLaborTolerance) {
        const auto tax_status =
            stage_m4_transfer(state, real, source_account,
                              state.institutions.treasury_account, estate.tax_paid);
        if (!tax_status.ok()) {
            return tax_status;
        }
    }

    if (last_household_member) {
        const auto residual_status = transfer_household_residual(
            state, real, monetary, financial, ownership, household,
            destination_household, security_buffer);
        if (!residual_status.ok()) {
            return residual_status;
        }
        estate.public_residual = !heir.valid();
    }

    for (const auto job_id : std::array{employment.primary_job(deceased),
                                        employment.secondary_job(deceased)}) {
        const auto *job = employment.get(job_id);
        if (job == nullptr || !job->active) {
            continue;
        }
        const auto job_status = separate_job(
            employment, job_id, day, core::SeparationKind::death, labor_accounts);
        if (!job_status.ok()) {
            return job_status;
        }
    }

    auto status = membership.remove(deceased);
    if (!status.ok()) {
        return status;
    }
    status = persons.mark_dead(deceased, day);
    if (!status.ok()) {
        return status;
    }
    estates.push_back(estate);
    ++metrics.deaths;
    ++metrics.estates_settled;
    metrics.beneficial_lots_transferred += estate.transferred_lots;
    metrics.inheritance_tax_share += estate.tax_share;
    metrics.inheritance_tax_paid += estate.tax_paid;
    return Status::success();
}

[[nodiscard]] Status separate_job(core::EmploymentBook &employment, JobId job_id,
                                  std::int32_t day, core::SeparationKind kind,
                                  core::LaborAccounts &accounts) {
    const auto *job = employment.get(job_id);
    if (job == nullptr || !job->active) {
        return Status::success();
    }
    const auto person = job->person;
    const double before_fte = employment.active_hours(person);
    const bool before_head = before_fte > kLaborTolerance;
    const auto status = employment.separate(job_id, day, kind);
    if (!status.ok()) {
        return status;
    }
    const double after_fte = employment.active_hours(person);
    const bool after_head = after_fte > kLaborTolerance;
    accounts.private_fte_outflows_total += std::max(0.0, before_fte - after_fte);
    if (before_head && !after_head) {
        record_head_separation(kind, accounts);
    } else if (kind == core::SeparationKind::job_to_job) {
        accounts.job_to_job_moves_total += 1.0;
    }
    return Status::success();
}

[[nodiscard]] Result<JobId> hire_job(core::EmploymentBook &employment, PersonId person,
                                     FirmId firm, std::int32_t day, double wage,
                                     double hours, bool secondary,
                                     core::LaborAccounts &accounts) {
    const double before_fte = employment.active_hours(person);
    const bool before_head = before_fte > kLaborTolerance;
    const auto result = employment.hire(person, firm, day, wage, hours, secondary);
    if (!result.ok()) {
        return result.status();
    }
    const double after_fte = employment.active_hours(person);
    accounts.private_fte_inflows_total += std::max(0.0, after_fte - before_fte);
    if (!before_head && after_fte > kLaborTolerance) {
        accounts.hires_total += 1.0;
    }
    return *result.get_if();
}

[[nodiscard]] Status set_job_hours(core::EmploymentBook &employment, JobId job,
                                   double hours, core::LaborAccounts &accounts) {
    const auto *record = employment.get(job);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found, "active employment contract is absent");
    }
    const double before = employment.active_hours(record->person);
    const auto status = employment.set_hours(job, hours);
    if (!status.ok()) {
        return status;
    }
    const double after = employment.active_hours(record->person);
    if (after >= before) {
        accounts.private_fte_inflows_total += after - before;
    } else {
        accounts.private_fte_outflows_total += before - after;
    }
    return Status::success();
}

[[nodiscard]] Status suspend_job(core::EmploymentBook &employment, JobId job,
                                 std::int32_t day, core::LaborAccounts &accounts) {
    const auto *record = employment.get(job);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found, "active employment contract is absent");
    }
    const auto person = record->person;
    const double before = employment.active_hours(person);
    const auto status = employment.suspend(job, day);
    if (!status.ok()) {
        return status;
    }
    const double after = employment.active_hours(person);
    accounts.private_fte_outflows_total += std::max(0.0, before - after);
    if (before > kLaborTolerance && after <= kLaborTolerance) {
        accounts.suspensions_total += 1.0;
    }
    return Status::success();
}

[[nodiscard]] Status recall_job(core::EmploymentBook &employment, JobId job,
                                core::LaborAccounts &accounts) {
    const auto *record = employment.get(job);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found, "active employment contract is absent");
    }
    const auto person = record->person;
    const double before = employment.active_hours(person);
    const auto status = employment.recall(job);
    if (!status.ok()) {
        return status;
    }
    const double after = employment.active_hours(person);
    accounts.private_fte_inflows_total += std::max(0.0, after - before);
    if (before <= kLaborTolerance && after > kLaborTolerance) {
        accounts.recalls_total += 1.0;
    }
    return Status::success();
}

[[nodiscard]] Status separate_person(core::EmploymentBook &employment, PersonId person,
                                     std::int32_t day, core::SeparationKind kind,
                                     core::LaborAccounts &accounts) {
    const auto primary = employment.primary_job(person);
    const auto secondary = employment.secondary_job(person);
    auto status = separate_job(employment, secondary, day, kind, accounts);
    if (!status.ok()) {
        return status;
    }
    return separate_job(employment, primary, day, kind, accounts);
}

void measure_labor(const core::RootState &state, const M7Rules &rules,
                   const M5PolicyState &policy, const core::PersonStore &persons,
                   const core::EmploymentBook &employment, const M4TickScratch &real,
                   std::int32_t day, core::LaborAccounts &accounts,
                   M7Metrics &metrics) {
    accounts.employed_fte = 0.0;
    accounts.employed_heads = 0.0;
    accounts.unemployed = 0.0;
    accounts.suspended = 0.0;
    accounts.job_guarantee = 0.0;
    accounts.out_of_labor_force = 0.0;
    accounts.labor_supply = 0.0;
    accounts.vacancies = 0.0;
    accounts.underemployed_heads = 0.0;
    accounts.underemployment_hours = 0.0;
    accounts.suspended_memo = static_cast<double>(employment.suspended_count());
    accounts.second_job_heads = 0.0;
    accounts.second_job_hours = 0.0;
    accounts.nonsearching = 0.0;
    double working_age_total = 0.0;
    double wage_bill = 0.0;
    double wage_hours = 0.0;
    for (const auto person_id : persons.alive_ids()) {
        const auto *person = persons.get(person_id);
        const double age = completed_age(*person, day);
        const bool working_age = age >= static_cast<double>(rules.working_age) &&
                                 age < static_cast<double>(rules.retirement_age);
        working_age_total += working_age ? 1.0 : 0.0;
        if (!working_age || !person->participating) {
            accounts.out_of_labor_force += 1.0;
            accounts.nonsearching += working_age && !person->searching ? 1.0 : 0.0;
            continue;
        }
        accounts.labor_supply += 1.0;
        accounts.nonsearching += person->searching ? 0.0 : 1.0;
        const double hours = employment.active_hours(person_id);
        const auto *primary = employment.get(employment.primary_job(person_id));
        const auto *secondary = employment.get(employment.secondary_job(person_id));
        const bool suspended =
            (primary != nullptr && primary->active && primary->suspended) ||
            (secondary != nullptr && secondary->active && secondary->suspended);
        if (secondary != nullptr && secondary->active && !secondary->suspended) {
            accounts.second_job_heads += 1.0;
            accounts.second_job_hours += secondary->hours;
        }
        for (const auto *job : std::array{primary, secondary}) {
            if (job == nullptr || !job->active || job->suspended) {
                continue;
            }
            wage_bill += job->hours * job->wage * person->efficiency;
            wage_hours += job->hours;
        }
        if (hours <= kLaborTolerance) {
            if (suspended) {
                accounts.suspended += 1.0;
                continue;
            }
            if (policy.job_guarantee && policy.job_guarantee_wage_ratio > 0.0) {
                accounts.job_guarantee += 1.0;
            } else {
                accounts.unemployed += 1.0;
            }
            continue;
        }
        accounts.employed_heads += 1.0;
        accounts.employed_fte += hours;
        const double residual = std::max(0.0, 1.0 - hours);
        if (policy.job_guarantee && policy.job_guarantee_wage_ratio > 0.0) {
            accounts.job_guarantee += residual;
        } else {
            accounts.unemployed += residual;
        }
        if (hours < 1.0 - kLaborTolerance) {
            accounts.underemployed_heads += 1.0;
            accounts.underemployment_hours += 1.0 - hours;
        }
    }
    for (std::size_t index = 0; index < real.firm_ids_.size(); ++index) {
        accounts.vacancies += std::max(
            0.0, real.firm_work_[index].labor_demand_effective -
                     firm_labor_totals(employment, persons, real.firm_ids_[index])
                         .effective_labor);
    }
    const double head_flow_balance =
        accounts.hires_total + accounts.recalls_total -
        accounts.churn_separations_total - accounts.layoff_separations_total -
        accounts.firm_exit_separations_total - accounts.death_separations_total -
        accounts.retirement_separations_total - accounts.suspensions_total -
        accounts.welfare_quits_total;
    const double fte_flow_balance =
        accounts.private_fte_inflows_total - accounts.private_fte_outflows_total;
    if (accounts.previous_employed_heads >= 0.0) {
        const double expected = accounts.previous_employed_heads + head_flow_balance -
                                accounts.previous_head_flow_balance;
        const double tolerance =
            kLaborTolerance *
            std::max({1.0, std::abs(expected), std::abs(accounts.employed_heads)});
        if (std::abs(expected - accounts.employed_heads) > tolerance) {
            accounts.employed_heads = std::numeric_limits<double>::quiet_NaN();
        }
    }
    if (accounts.previous_employed_fte >= 0.0) {
        const double expected = accounts.previous_employed_fte + fte_flow_balance -
                                accounts.previous_fte_flow_balance;
        const double tolerance =
            kLaborTolerance *
            std::max({1.0, std::abs(expected), std::abs(accounts.employed_fte)});
        if (std::abs(expected - accounts.employed_fte) > tolerance) {
            accounts.employed_fte = std::numeric_limits<double>::quiet_NaN();
        }
    }
    accounts.previous_employed_heads = accounts.employed_heads;
    accounts.previous_head_flow_balance = head_flow_balance;
    accounts.previous_employed_fte = accounts.employed_fte;
    accounts.previous_fte_flow_balance = fte_flow_balance;

    metrics.employed_fte = accounts.employed_fte;
    metrics.employed_heads = accounts.employed_heads;
    // A suspended contract carries a recall option, but it provides no hours,
    // pay, or output. Workers on temporary layoff therefore remain part of
    // headline labor slack while the separate suspended stock preserves the
    // useful recall-state decomposition.
    metrics.unemployment = accounts.unemployed + accounts.suspended;
    metrics.unemployment_rate = accounts.labor_supply <= 0.0
                                    ? 0.0
                                    : metrics.unemployment / accounts.labor_supply;
    metrics.suspended = accounts.suspended;
    metrics.job_guarantee = accounts.job_guarantee;
    metrics.out_of_labor_force = accounts.out_of_labor_force;
    metrics.labor_supply = accounts.labor_supply;
    metrics.vacancies = accounts.vacancies;
    metrics.underemployed_heads = accounts.underemployed_heads;
    metrics.underemployment_hours = accounts.underemployment_hours;
    metrics.suspended_memo = accounts.suspended_memo;
    metrics.second_job_heads = accounts.second_job_heads;
    metrics.second_job_hours = accounts.second_job_hours;
    metrics.nonsearching = accounts.nonsearching;
    metrics.mean_hourly_wage =
        wage_hours > kLaborTolerance ? wage_bill / wage_hours : 0.0;
    metrics.participation_rate =
        working_age_total > 0.0 ? accounts.labor_supply / working_age_total : 0.0;
    static_cast<void>(state);
}

class M7Extension final : public M6TickExtension {
  public:
    M7Extension(M7Runtime &runtime, M7TickScratch &scratch,
                const M7AdvanceOptions &options, M7TickExtension *extension) noexcept
        : runtime_(runtime), scratch_(scratch), options_(options),
          extension_(extension) {}

    ~M7Extension() override {
        if (memory_efficient_staging_ && !committed_) {
            runtime_.persons = std::move(scratch_.persons_);
            runtime_.membership = std::move(scratch_.membership_);
            runtime_.beneficial_ownership = std::move(scratch_.beneficial_ownership_);
            runtime_.employment = std::move(scratch_.employment_);
            runtime_.relationships = std::move(scratch_.relationships_);
            runtime_.firm_target_ema = std::move(scratch_.firm_target_ema_);
            runtime_.estates = std::move(scratch_.estates_);
            runtime_.leaving_home = std::move(scratch_.leaving_home_);
            runtime_.household_wealth_quintile =
                std::move(scratch_.household_wealth_quintile_);
            runtime_.household_mortality_multiplier =
                std::move(scratch_.household_mortality_multiplier_);
            runtime_.household_fertility_multiplier =
                std::move(scratch_.household_fertility_multiplier_);
        }
    }

    Status prepare_tick(const core::RootState &state, M4Runtime &real_runtime,
                        M4TickScratch &real, M5Runtime &monetary_runtime,
                        M5TickScratch &monetary, M6Runtime &financial_runtime,
                        M6TickScratch &financial, Tick tick, PhiloxRng &rng) override {
        if (options_.force_death.has_value() &&
            !runtime_.persons.alive(*options_.force_death)) {
            return Status(ErrorCode::contract_violation,
                          "forced death target is not alive");
        }
        if (options_.force_birth.has_value() &&
            !runtime_.persons.alive(*options_.force_birth)) {
            return Status(ErrorCode::contract_violation,
                          "forced birth target is not alive");
        }
        if (options_.force_leave_home.has_value() &&
            !runtime_.persons.alive(*options_.force_leave_home)) {
            return Status(ErrorCode::contract_violation,
                          "forced leaving-home target is not alive");
        }
        memory_efficient_staging_ = options_.base.base.base.memory_efficient_staging;
        if (memory_efficient_staging_) {
            scratch_.persons_ = std::move(runtime_.persons);
            scratch_.membership_ = std::move(runtime_.membership);
            scratch_.beneficial_ownership_ = std::move(runtime_.beneficial_ownership);
            scratch_.employment_ = std::move(runtime_.employment);
            scratch_.relationships_ = std::move(runtime_.relationships);
            scratch_.firm_target_ema_ = std::move(runtime_.firm_target_ema);
            scratch_.estates_ = std::move(runtime_.estates);
            scratch_.leaving_home_ = std::move(runtime_.leaving_home);
            scratch_.household_wealth_quintile_ =
                std::move(runtime_.household_wealth_quintile);
            scratch_.household_mortality_multiplier_ =
                std::move(runtime_.household_mortality_multiplier);
            scratch_.household_fertility_multiplier_ =
                std::move(runtime_.household_fertility_multiplier);
        } else {
            scratch_.persons_ = runtime_.persons;
            scratch_.membership_ = runtime_.membership;
            scratch_.beneficial_ownership_ = runtime_.beneficial_ownership;
            scratch_.employment_ = runtime_.employment;
            scratch_.relationships_ = runtime_.relationships;
            scratch_.firm_target_ema_ = runtime_.firm_target_ema;
            scratch_.estates_ = runtime_.estates;
            scratch_.leaving_home_ = runtime_.leaving_home;
            scratch_.household_wealth_quintile_ =
                runtime_.household_wealth_quintile;
            scratch_.household_mortality_multiplier_ =
                runtime_.household_mortality_multiplier;
            scratch_.household_fertility_multiplier_ =
                runtime_.household_fertility_multiplier;
        }
        scratch_.stratification_snapshot_day_ =
            runtime_.stratification_snapshot_day;
        scratch_.mortality_quintile_multiplier_ =
            runtime_.mortality_quintile_multiplier;
        scratch_.fertility_quintile_multiplier_ =
            runtime_.fertility_quintile_multiplier;
        scratch_.demographic_signal_year_ = runtime_.demographic_signal_year;
        scratch_.demographic_signal_years_completed_ =
            runtime_.demographic_signal_years_completed;
        scratch_.demographic_signal_ewma_ = runtime_.demographic_signal_ewma;
        scratch_.demographic_signal_baseline_ =
            runtime_.demographic_signal_baseline;
        scratch_.demographic_signal_x_ = runtime_.demographic_signal_x;
        scratch_.demographic_signal_fertility_multiplier_ =
            runtime_.rules.fertility_income_elasticity > 0.0
                ? runtime_.demographic_signal_fertility_multiplier
                : 1.0;
        scratch_.demographic_signal_mortality_multiplier_ =
            runtime_.rules.mortality_income_elasticity > 0.0
                ? runtime_.demographic_signal_mortality_multiplier
                : 1.0;
        scratch_.demographic_signal_last_real_wage_ =
            runtime_.demographic_signal_last_real_wage;
        scratch_.demographic_signal_wage_sum_ =
            runtime_.demographic_signal_wage_sum;
        scratch_.demographic_signal_labor_sum_ =
            runtime_.demographic_signal_labor_sum;
        scratch_.demographic_signal_price_sum_ =
            runtime_.demographic_signal_price_sum;
        scratch_.demographic_signal_days_ = runtime_.demographic_signal_days;
        scratch_.labor_accounts_ = runtime_.labor_accounts;
        scratch_.pending_leaving_home_.clear();
        scratch_.opening_alive_.assign(scratch_.persons_.alive_ids().begin(),
                                       scratch_.persons_.alive_ids().end());
        std::sort(scratch_.opening_alive_.begin(), scratch_.opening_alive_.end());
        const auto person_capacity =
            static_cast<std::size_t>(scratch_.persons_.next_id());
        scratch_.guardian_heads_.assign(person_capacity, 0U);
        scratch_.guardian_next_.assign(person_capacity, 0U);
        for (const auto person_id : scratch_.opening_alive_) {
            const auto *person = scratch_.persons_.get(person_id);
            if (person == nullptr || !scratch_.persons_.alive(person->guardian)) {
                continue;
            }
            const auto person_index = static_cast<std::size_t>(person_id.value());
            const auto guardian_index =
                static_cast<std::size_t>(person->guardian.value());
            scratch_.guardian_next_[person_index] =
                scratch_.guardian_heads_[guardian_index];
            scratch_.guardian_heads_[guardian_index] =
                static_cast<std::uint32_t>(person_id.value());
        }
        scratch_.retired_households_.clear();
        scratch_.external_leave_home_multiplier_ = 1.0;
        scratch_.external_fertility_multiplier_ = 1.0;
        scratch_.external_mortality_multiplier_ = 1.0;
        scratch_.next_event_id_ = runtime_.next_event_id;
        scratch_.population_rng_counter_ = runtime_.population_rng_counter;
        scratch_.working_metrics_ = M7Metrics{};
        const auto day = static_cast<std::int64_t>(runtime_.start_calendar_day) +
                         static_cast<std::int64_t>(tick.value()) + 1;
        if (day < std::numeric_limits<std::int32_t>::min() ||
            day > std::numeric_limits<std::int32_t>::max()) {
            return Status(ErrorCode::out_of_range,
                          "M7 calendar day exceeds storage range");
        }
        const auto calendar_day = static_cast<std::int32_t>(day);
        if (extension_ != nullptr) {
            const auto status = extension_->prepare_tick(
                state, real_runtime, real, monetary_runtime, monetary,
                financial_runtime, financial, runtime_, scratch_, tick, rng);
            if (!status.ok()) {
                return status;
            }
        }
        const auto household_identity_count = real.household_dense_index_.size();
        const bool refresh_stratification =
            scratch_.household_wealth_quintile_.empty() ||
            calendar_day < scratch_.stratification_snapshot_day_ ||
            calendar_day - scratch_.stratification_snapshot_day_ >= 365;
        if (refresh_stratification) {
            const auto status = refresh_wealth_stratification(
                state, runtime_.rules, scratch_.persons_, real, monetary, financial,
                calendar_day, scratch_);
            if (!status.ok()) {
                return status;
            }
        } else if (scratch_.household_wealth_quintile_.size() <
                   household_identity_count) {
            // Households formed between annual snapshots are deliberately neutral
            // until the next rank refresh. This preserves the historical contract
            // and avoids an O(H log H) sort after every daily household event.
            scratch_.household_wealth_quintile_.resize(
                household_identity_count, kUnrankedWealthQuintile);
            scratch_.household_mortality_multiplier_.resize(
                household_identity_count, 1.0);
            scratch_.household_fertility_multiplier_.resize(
                household_identity_count, 1.0);
        }
        scratch_.working_metrics_.wealth_rank_mortality_multiplier_stddev =
            quintile_multiplier_stddev(
                scratch_.mortality_quintile_multiplier_);
        scratch_.working_metrics_.wealth_rank_fertility_multiplier_stddev =
            quintile_multiplier_stddev(
                scratch_.fertility_quintile_multiplier_);
        if (real_runtime.rules.consumption_strata) {
            std::fill(real.household_need_units_.begin(),
                      real.household_need_units_.end(), 0.0);
        }
        auto effective_policy = runtime_.policy;
        if (!government_enabled(real_runtime)) {
            effective_policy.inheritance_tax_rate = 0.0;
            effective_policy.pension_replacement = 0.0;
        }
        for (const auto person_id : scratch_.opening_alive_) {
            const auto *person = scratch_.persons_.get(person_id);
            if (person == nullptr || !person->alive) {
                continue;
            }
            bool dies =
                options_.force_death.has_value() && *options_.force_death == person_id;
            const double age = completed_age(*person, calendar_day);
            if (!dies && runtime_.rules.mortality) {
                if (age >=
                    static_cast<double>(runtime_.rules.vital_rates.maximum_age)) {
                    dies = true;
                } else {
                    const auto survival = algorithms::survival_probability(
                        runtime_.rules.vital_rates, age, kDailyYear);
                    if (!survival.ok()) {
                        return survival.status();
                    }
                    const double base_mortality = 1.0 - *survival.get_if();
                    const double rank_multiplier = household_rank_multiplier(
                        person->household,
                        std::span<const double>(
                            scratch_.household_mortality_multiplier_));
                    const double adjusted_survival = std::clamp(
                        1.0 - scratch_.external_mortality_multiplier_ *
                                  scratch_
                                      .demographic_signal_mortality_multiplier_ *
                                  rank_multiplier * base_mortality,
                        0.0, 1.0);
                    dies = unit_draw(state.seed, person_id.value(), calendar_day,
                                     kMortalityStream) > adjusted_survival;
                }
            }
            if (dies) {
                const auto wealth_quintile = household_wealth_quintile(
                    person->household,
                    std::span<const std::uint8_t>(
                        scratch_.household_wealth_quintile_));
                if (wealth_quintile == 0U) {
                    ++scratch_.working_metrics_.bottom_wealth_quintile_deaths;
                } else if (wealth_quintile == kWealthQuintiles - 1U) {
                    ++scratch_.working_metrics_.top_wealth_quintile_deaths;
                }
                const auto status =
                    settle_death(state, real, monetary, financial, scratch_.persons_,
                                 scratch_.membership_, scratch_.beneficial_ownership_,
                                 scratch_.employment_, scratch_.relationships_,
                                 scratch_.labor_accounts_, scratch_.estates_,
                                 scratch_.retired_households_, scratch_.next_event_id_,
                                 person_id, calendar_day, effective_policy,
                                 runtime_.rules, scratch_.working_metrics_,
                                 scratch_.guardian_heads_, scratch_.guardian_next_,
                                 scratch_.deceased_lots_, scratch_.estate_securities_);
                if (!status.ok()) {
                    return status;
                }
                if (scratch_.membership_.members(person->household).empty()) {
                    scratch_.retired_households_.push_back(person->household);
                }
            } else if (real_runtime.rules.consumption_strata) {
                const auto household_identity =
                    static_cast<std::size_t>(person->household.value());
                if (household_identity >= real.household_dense_index_.size()) {
                    return Status(ErrorCode::invariant_violation,
                                  "M7 household need projection is stale");
                }
                const auto household_index =
                    real.household_dense_index_[household_identity];
                if (household_index >= real.household_need_units_.size()) {
                    return Status(ErrorCode::invariant_violation,
                                  "M7 household need projection is stale");
                }
                real.household_need_units_[household_index] +=
                    age < 18.0 ? 0.65 : (age >= 65.0 ? 0.90 : 1.0);
            }
        }
        if (options_.force_death.has_value() &&
            scratch_.persons_.alive(*options_.force_death)) {
            return Status(ErrorCode::contract_violation,
                          "forced death target was not settled");
        }
        return apply_lifecycle_consumption(
            state, runtime_.rules, scratch_.persons_, calendar_day, real,
            monetary, financial, scratch_);
    }

    Status run_labor(const core::RootState &state, M4Runtime &real_runtime,
                     M4TickScratch &real, M5Runtime &monetary,
                     M5TickScratch &monetary_scratch, M6Runtime &financial_runtime,
                     M6TickScratch &financial_scratch, Tick tick, PhiloxRng &rng,
                     bool &handled) override {
        if (extension_ != nullptr) {
            const auto status = extension_->before_labor(
                state, real_runtime, real, monetary, monetary_scratch,
                financial_runtime, financial_scratch, runtime_, scratch_, tick, rng);
            if (!status.ok()) {
                return status;
            }
        }
        handled = runtime_.rules.persistent_labor;
        if (!handled) {
            if (extension_ != nullptr) {
                return extension_->after_labor(state, real_runtime, real, monetary,
                                               monetary_scratch, financial_runtime,
                                               financial_scratch, runtime_, scratch_,
                                               tick, rng);
            }
            return Status::success();
        }
        const auto calendar_day = static_cast<std::int32_t>(
            static_cast<std::int64_t>(runtime_.start_calendar_day) +
            static_cast<std::int64_t>(tick.value()) + 1);
        scratch_.household_work_index_.assign(
            static_cast<std::size_t>(state.households.allocator_state().next_id),
            std::numeric_limits<std::size_t>::max());
        for (std::size_t index = 0; index < real.household_ids_.size(); ++index) {
            scratch_.household_work_index_[static_cast<std::size_t>(
                real.household_ids_[index].value())] = index;
            real.household_work_[index].labor_sold = 0.0;
            real.household_work_[index].labor_capacity = 0.0;
        }
        if (scratch_.firm_target_ema_.size() < state.firms.allocator_state().next_id) {
            scratch_.firm_target_ema_.resize(
                static_cast<std::size_t>(state.firms.allocator_state().next_id), 0.0);
        }
        for (const auto &job : scratch_.employment_.records()) {
            if (!job.active || std::binary_search(real.firm_ids_.begin(),
                                                  real.firm_ids_.end(), job.firm)) {
                continue;
            }
            const auto separation =
                separate_job(scratch_.employment_, job.id, calendar_day,
                             core::SeparationKind::firm_exit, scratch_.labor_accounts_);
            if (!separation.ok()) {
                return separation;
            }
        }

        if (runtime_.rules.family_transfers) {
            for (std::size_t recipient_index = 0;
                 recipient_index < real.household_ids_.size(); ++recipient_index) {
                const auto recipient = real.household_ids_[recipient_index];
                const auto *recipient_component = state.households.get(recipient);
                const auto recipient_account_index = static_cast<std::size_t>(
                    recipient_component->primary_account.value());
                const double recipient_need = std::max(
                    real.household_work_[recipient_index].consumption_budget,
                    recipient_component->income_propensity *
                        std::max(
                            0.0,
                            real.household_work_[recipient_index].income_expected));
                double gap = std::max(0.0, recipient_need -
                                               real.balances_[recipient_account_index]);
                if (gap <= kLaborTolerance) {
                    continue;
                }
                scratch_.kin_households_.clear();
                for (const auto person_id : scratch_.membership_.members(recipient)) {
                    const auto *person = scratch_.persons_.get(person_id);
                    for (const auto kin : std::array{
                             person->mother,
                             person->father,
                         }) {
                        if (scratch_.persons_.alive(kin)) {
                            scratch_.kin_households_.push_back(
                                scratch_.persons_.get(kin)->household);
                        }
                    }
                    for (const auto child :
                         scratch_.relationships_.children(person_id)) {
                        if (scratch_.persons_.alive(child)) {
                            scratch_.kin_households_.push_back(
                                scratch_.persons_.get(child)->household);
                        }
                    }
                }
                std::sort(scratch_.kin_households_.begin(),
                          scratch_.kin_households_.end());
                scratch_.kin_households_.erase(
                    std::unique(scratch_.kin_households_.begin(),
                                scratch_.kin_households_.end()),
                    scratch_.kin_households_.end());
                bool received = false;
                for (const auto donor : scratch_.kin_households_) {
                    if (donor == recipient || gap <= kLaborTolerance ||
                        donor.value() >= scratch_.household_work_index_.size()) {
                        continue;
                    }
                    const auto donor_index =
                        scratch_.household_work_index_[static_cast<std::size_t>(
                            donor.value())];
                    if (donor_index >= real.household_work_.size()) {
                        continue;
                    }
                    const auto *donor_component = state.households.get(donor);
                    const auto donor_account_index = static_cast<std::size_t>(
                        donor_component->primary_account.value());
                    const double donor_need = std::max(
                        real.household_work_[donor_index].consumption_budget,
                        donor_component->income_propensity *
                            std::max(
                                0.0,
                                real.household_work_[donor_index].income_expected));
                    const double surplus = std::max(
                        0.0, real.balances_[donor_account_index] -
                                 runtime_.rules.family_transfer_buffer * donor_need);
                    const double amount = std::min(gap, surplus);
                    if (amount <= kLaborTolerance) {
                        continue;
                    }
                    const auto transfer_status =
                        stage_m4_transfer(state, real, donor_component->primary_account,
                                          recipient_component->primary_account, amount);
                    if (!transfer_status.ok()) {
                        return transfer_status;
                    }
                    gap -= amount;
                    received = true;
                    scratch_.working_metrics_.family_transfer_total += amount;
                }
                if (received) {
                    scratch_.working_metrics_.family_transfer_recipients += 1.0;
                }
                if (gap > kLaborTolerance) {
                    scratch_.working_metrics_.family_exposed_households += 1.0;
                }
            }
        }

        const double churn_probability =
            runtime_.rules.annual_churn >= 1.0
                ? 1.0
                : 1.0 - std::pow(1.0 - runtime_.rules.annual_churn, kDailyYear);
        for (const auto person_id : scratch_.persons_.alive_ids()) {
            auto *person = scratch_.persons_.get(person_id);
            const double age = completed_age(*person, calendar_day);
            const bool working_age =
                age >= static_cast<double>(runtime_.rules.working_age) &&
                age < static_cast<double>(runtime_.rules.retirement_age);
            const auto *primary_job =
                scratch_.employment_.get(scratch_.employment_.primary_job(person_id));
            const auto *secondary_job =
                scratch_.employment_.get(scratch_.employment_.secondary_job(person_id));
            const bool attached =
                scratch_.employment_.active_hours(person_id) > kLaborTolerance ||
                (primary_job != nullptr && primary_job->active &&
                 primary_job->suspended) ||
                (secondary_job != nullptr && secondary_job->active &&
                 secondary_job->suspended);
            person->participating =
                working_age &&
                (attached ||
                 structurally_participates(runtime_.rules, state.seed, person_id, age));
            person->searching = person->participating;
            // M4 settles taxes and unemployment benefits from the household
            // labor projection.  Its capacity must therefore be the active
            // labor force, not every working-age resident.  Counting structural
            // non-participants here made them appear unemployed to the fiscal
            // system even though M7 correctly classified them as out of the
            // labor force.
            if (person->participating) {
                const auto household_index =
                    scratch_.household_work_index_[static_cast<std::size_t>(
                        person->household.value())];
                if (household_index >= real.household_work_.size()) {
                    return Status(ErrorCode::invariant_violation,
                                  "person labor household projection is stale");
                }
                real.household_work_[household_index].labor_capacity += 1.0;
            }
            if (!working_age) {
                const auto status = separate_person(
                    scratch_.employment_, person_id, calendar_day,
                    core::SeparationKind::retirement, scratch_.labor_accounts_);
                if (!status.ok()) {
                    return status;
                }
                continue;
            }
            const auto primary = scratch_.employment_.primary_job(person_id);
            if (scratch_.employment_.get(primary) != nullptr &&
                unit_draw(state.seed, person_id.value(), calendar_day, kChurnStream) <
                    churn_probability) {
                const auto status = separate_person(
                    scratch_.employment_, person_id, calendar_day,
                    core::SeparationKind::churn, scratch_.labor_accounts_);
                if (!status.ok()) {
                    return status;
                }
                scratch_.working_metrics_.separations += 1.0;
            }
        }

        double mean_posted_wage = 0.0;
        for (const auto &work : real.firm_work_) {
            mean_posted_wage += work.posted_wage;
        }
        mean_posted_wage /=
            static_cast<double>(std::max<std::size_t>(1, real.firm_work_.size()));
        if (runtime_.rules.relationship_wages) {
            for (const auto &job : scratch_.employment_.records()) {
                if (!job.active || job.suspended || calendar_day <= job.hire_day ||
                    (calendar_day - job.hire_day) % 365 != 0) {
                    continue;
                }
                const auto found =
                    std::find(real.firm_ids_.begin(), real.firm_ids_.end(), job.firm);
                if (found == real.firm_ids_.end()) {
                    continue;
                }
                const auto index = static_cast<std::size_t>(
                    std::distance(real.firm_ids_.begin(), found));
                const double reviewed = std::max({
                    job.wage,
                    real.firm_work_[index].posted_wage,
                    monetary.policy.minimum_wage,
                });
                const auto status = scratch_.employment_.set_wage(job.id, reviewed);
                if (!status.ok()) {
                    return status;
                }
            }
        }
        if (runtime_.rules.participation_margin) {
            double outside_option =
                monetary.policy.unemployment_benefit_replacement * mean_posted_wage;
            if (monetary.policy.job_guarantee &&
                monetary.policy.job_guarantee_wage_ratio > 0.0) {
                outside_option = std::max(
                    outside_option, std::max(monetary.policy.minimum_wage,
                                             monetary.policy.job_guarantee_wage_ratio *
                                                 mean_posted_wage));
            }
            const double reservation =
                runtime_.rules.reservation_markup * outside_option;
            for (const auto person_id : scratch_.persons_.alive_ids()) {
                auto *person = scratch_.persons_.get(person_id);
                if (!person->participating) {
                    person->searching = false;
                    continue;
                }
                const auto household_index =
                    scratch_.household_work_index_[static_cast<std::size_t>(
                        person->household.value())];
                const auto withdraw = [&]() {
                    person->participating = false;
                    person->searching = false;
                    if (household_index < real.household_work_.size()) {
                        real.household_work_[household_index].labor_capacity = std::max(
                            0.0,
                            real.household_work_[household_index].labor_capacity - 1.0);
                    }
                };
                const auto *primary = scratch_.employment_.get(
                    scratch_.employment_.primary_job(person_id));
                if (primary != nullptr && primary->active && !primary->suspended &&
                    primary->wage * person->efficiency < reservation &&
                    unit_draw(state.seed, person_id.value(), calendar_day,
                              kWelfareStream) < runtime_.rules.welfare_quit_hazard) {
                    const auto status = separate_person(
                        scratch_.employment_, person_id, calendar_day,
                        core::SeparationKind::welfare_quit, scratch_.labor_accounts_);
                    if (!status.ok()) {
                        return status;
                    }
                    scratch_.working_metrics_.separations += 1.0;
                    withdraw();
                    continue;
                }
                const double active_hours =
                    scratch_.employment_.active_hours(person_id);
                person->searching =
                    active_hours > kLaborTolerance ||
                    mean_posted_wage * person->efficiency >= reservation;
                if (active_hours <= kLaborTolerance && !person->searching) {
                    const auto *secondary = scratch_.employment_.get(
                        scratch_.employment_.secondary_job(person_id));
                    const bool retained_contract =
                        (primary != nullptr && primary->active) ||
                        (secondary != nullptr && secondary->active);
                    if (retained_contract) {
                        const auto status = separate_person(
                            scratch_.employment_, person_id, calendar_day,
                            core::SeparationKind::welfare_quit,
                            scratch_.labor_accounts_);
                        if (!status.ok()) {
                            return status;
                        }
                        scratch_.working_metrics_.separations += 1.0;
                    }
                    withdraw();
                }
            }
        }

        for (const auto &job : scratch_.employment_.records()) {
            if (!job.active || !job.suspended ||
                calendar_day - job.suspension_day <
                    static_cast<std::int32_t>(runtime_.rules.suspension_timeout_days)) {
                continue;
            }
            const auto status = separate_job(scratch_.employment_, job.id, calendar_day,
                                             core::SeparationKind::cash_layoff,
                                             scratch_.labor_accounts_);
            if (!status.ok()) {
                return status;
            }
        }

        for (std::size_t firm_index = 0; firm_index < real.firm_ids_.size();
             ++firm_index) {
            const auto firm_id = real.firm_ids_[firm_index];
            const auto *firm = state.firms.get(firm_id);
            auto &work = real.firm_work_[firm_index];
            const double target = std::max(0.0, work.labor_demand_effective);
            auto &target_ema =
                scratch_.firm_target_ema_[static_cast<std::size_t>(firm_id.value())];
            target_ema = target_ema <= 0.0
                             ? target
                             : (1.0 - runtime_.rules.target_smoothing) * target_ema +
                                   runtime_.rules.target_smoothing * target;
            const double firing_target = std::max(target, target_ema);

            scratch_.roster_buffer_.assign(scratch_.employment_.roster(firm_id).begin(),
                                           scratch_.employment_.roster(firm_id).end());
            std::sort(scratch_.roster_buffer_.begin(), scratch_.roster_buffer_.end(),
                      [&](JobId left, JobId right) {
                          const auto *left_job = scratch_.employment_.get(left);
                          const auto *right_job = scratch_.employment_.get(right);
                          if (left_job->hire_day != right_job->hire_day) {
                              return left_job->hire_day > right_job->hire_day;
                          }
                          return left > right;
                      });
            const auto opening_labor =
                firm_labor_totals(scratch_.employment_, scratch_.persons_, firm_id);
            double active_labor = opening_labor.effective_labor;
            double payroll = opening_labor.payroll;
            // Hiring responds to the live target, while layoffs close only a
            // fraction of a persistent shortfall. The one-effective-worker
            // floor prevents small firms from repeatedly firing and rehiring
            // around a fractional target.
            const double layoff_band =
                std::max(1.0, firing_target * runtime_.rules.layoff_band);
            const double layoff_gap =
                std::max(0.0, active_labor - firing_target - layoff_band);
            double planned_reduction = runtime_.rules.firing_adjustment * layoff_gap;
            if (!runtime_.rules.fractional_hours) {
                const double whole = std::floor(planned_reduction);
                const double fractional = planned_reduction - whole;
                planned_reduction =
                    whole + (unit_draw(state.seed, firm_id.value(), calendar_day,
                                       kLayoffStream) < fractional
                                 ? 1.0
                                 : 0.0);
            }
            for (const auto job_id : scratch_.roster_buffer_) {
                if (planned_reduction <= kLaborTolerance) {
                    break;
                }
                const auto *job = scratch_.employment_.get(job_id);
                if (job == nullptr || !job->active || job->suspended) {
                    continue;
                }
                const auto *person = scratch_.persons_.get(job->person);
                if (person == nullptr || !person->alive ||
                    person->efficiency <= kLaborTolerance) {
                    return Status(ErrorCode::invariant_violation,
                                  "layoff job references invalid worker efficiency");
                }
                const double job_labor = job->hours * person->efficiency;
                if (runtime_.rules.fractional_hours &&
                    job_labor - planned_reduction > kLaborTolerance) {
                    const double old_hours = job->hours;
                    const double hours_reduction =
                        planned_reduction / person->efficiency;
                    const auto status = set_job_hours(scratch_.employment_, job_id,
                                                      old_hours - hours_reduction,
                                                      scratch_.labor_accounts_);
                    if (!status.ok()) {
                        return status;
                    }
                    active_labor -= planned_reduction;
                    payroll -= planned_reduction * job->wage;
                    planned_reduction = 0.0;
                    break;
                }
                const auto status = separate_job(
                    scratch_.employment_, job_id, calendar_day,
                    core::SeparationKind::demand_layoff, scratch_.labor_accounts_);
                if (!status.ok()) {
                    return status;
                }
                active_labor -= job_labor;
                payroll -= job_labor * job->wage;
                planned_reduction = std::max(0.0, planned_reduction - job_labor);
                scratch_.working_metrics_.separations += 1.0;
            }

            const auto firm_account_index =
                static_cast<std::size_t>(firm->primary_account.value());
            const double budget = std::max(0.0, real.balances_[firm_account_index]);
            for (const auto job_id : scratch_.employment_.roster(firm_id)) {
                auto *job = scratch_.employment_.get(job_id);
                if (job == nullptr || !job->active || !job->suspended) {
                    continue;
                }
                const auto *person = scratch_.persons_.get(job->person);
                if (person == nullptr || !person->alive) {
                    return Status(ErrorCode::invariant_violation,
                                  "recall job references an absent person");
                }
                if (!person->participating) {
                    continue;
                }
                const double job_labor = job->hours * person->efficiency;
                const double job_cost = job_labor * job->wage;
                if (active_labor + job_labor > target + kLaborTolerance ||
                    payroll + job_cost > budget + kLaborTolerance) {
                    continue;
                }
                const auto status =
                    recall_job(scratch_.employment_, job_id, scratch_.labor_accounts_);
                if (!status.ok()) {
                    return status;
                }
                active_labor += job_labor;
                payroll += job_cost;
            }

            // Restore an incumbent's reduced primary hours before opening another
            // vacancy. Otherwise a temporary demand reduction permanently fragments
            // jobs into small contracts and recovery creates unnecessary new hires.
            for (const auto job_id : scratch_.employment_.roster(firm_id)) {
                if (active_labor >= target - kLaborTolerance ||
                    payroll >= budget - kLaborTolerance) {
                    break;
                }
                const auto *job = scratch_.employment_.get(job_id);
                if (job == nullptr || !job->active || job->suspended ||
                    job->secondary) {
                    continue;
                }
                const auto *person = scratch_.persons_.get(job->person);
                if (person == nullptr || !person->alive ||
                    person->efficiency <= kLaborTolerance) {
                    return Status(
                        ErrorCode::invariant_violation,
                        "hours restoration references invalid worker efficiency");
                }
                const double person_hours =
                    scratch_.employment_.active_hours(job->person);
                const double hourly_cost = job->wage * person->efficiency;
                const double expansion = std::min({
                    std::max(0.0, 1.0 - person_hours),
                    (target - active_labor) / person->efficiency,
                    hourly_cost > kLaborTolerance ? (budget - payroll) / hourly_cost
                                                  : 0.0,
                });
                if (expansion <= kLaborTolerance) {
                    continue;
                }
                const auto status =
                    set_job_hours(scratch_.employment_, job_id, job->hours + expansion,
                                  scratch_.labor_accounts_);
                if (!status.ok()) {
                    return status;
                }
                active_labor += expansion * person->efficiency;
                payroll += expansion * hourly_cost;
            }
        }

        scratch_.labor_candidates_.clear();
        scratch_.second_job_candidates_.clear();
        scratch_.ladder_candidates_.clear();
        for (const auto person_id : scratch_.persons_.alive_ids()) {
            const auto *person = scratch_.persons_.get(person_id);
            if (!person->participating || !person->searching) {
                continue;
            }
            const auto *primary =
                scratch_.employment_.get(scratch_.employment_.primary_job(person_id));
            const auto *secondary =
                scratch_.employment_.get(scratch_.employment_.secondary_job(person_id));
            const double active_hours = scratch_.employment_.active_hours(person_id);
            // A zero-hour suspended contract preserves a recall option, but it
            // must not lock its worker out of the rest of the labor market for
            // the entire suspension timeout.  Treat that worker as an ordinary
            // job seeker; a successful outside match closes the stale recall
            // option immediately before the new contract is opened.
            if ((primary == nullptr || (primary->active && primary->suspended)) &&
                secondary == nullptr) {
                scratch_.labor_candidates_.push_back(person_id);
            }
            if (runtime_.rules.second_jobs && primary != nullptr && primary->active &&
                !primary->suspended && secondary == nullptr &&
                active_hours < 1.0 - kLaborTolerance) {
                scratch_.second_job_candidates_.push_back(person_id);
            }
            if (runtime_.rules.job_ladder && primary != nullptr && primary->active &&
                !primary->suspended && secondary == nullptr) {
                scratch_.ladder_candidates_.push_back(person_id);
            }
        }
        std::sort(scratch_.labor_candidates_.begin(), scratch_.labor_candidates_.end());
        std::sort(scratch_.ladder_candidates_.begin(),
                  scratch_.ladder_candidates_.end());
        real.firm_order_.resize(real.firm_ids_.size());
        std::iota(real.firm_order_.begin(), real.firm_order_.end(), std::size_t{0});
        const auto search_order_status = rng.shuffle(std::span(real.firm_order_));
        if (!search_order_status.ok()) {
            return search_order_status;
        }
        std::size_t candidate_cursor = 0;
        std::size_t second_job_cursor = 0;
        for (const auto firm_index : real.firm_order_) {
            const auto firm_id = real.firm_ids_[firm_index];
            const auto *firm = state.firms.get(firm_id);
            auto &work = real.firm_work_[firm_index];
            const auto opening_labor =
                firm_labor_totals(scratch_.employment_, scratch_.persons_, firm_id);
            double active_labor = opening_labor.effective_labor;
            double payroll = opening_labor.payroll;
            const auto firm_account_index =
                static_cast<std::size_t>(firm->primary_account.value());
            const double payroll_budget =
                std::max(0.0, real.balances_[firm_account_index]);
            double need = std::max(0.0, work.labor_demand_effective - active_labor);
            const std::size_t second_job_eligible_end =
                scratch_.second_job_candidates_.size();
            while (need > kLaborTolerance &&
                   candidate_cursor < scratch_.labor_candidates_.size()) {
                const auto person_id = scratch_.labor_candidates_[candidate_cursor++];
                if (runtime_.rules.frictional_search &&
                    unit_draw(state.seed, person_id.value(), calendar_day,
                              firm_id.value()) >= runtime_.rules.search_intensity) {
                    continue;
                }
                const double residual_hours =
                    std::max(0.0, 1.0 - scratch_.employment_.active_hours(person_id));
                const auto *person = scratch_.persons_.get(person_id);
                if (person == nullptr || !person->alive ||
                    person->efficiency <= kLaborTolerance) {
                    return Status(ErrorCode::invariant_violation,
                                  "hiring candidate has invalid worker efficiency");
                }
                const double hourly_cost = work.posted_wage * person->efficiency;
                const double affordable_hours =
                    hourly_cost > kLaborTolerance
                        ? std::max(0.0, payroll_budget - payroll) / hourly_cost
                        : 0.0;
                const double hours =
                    runtime_.rules.fractional_hours
                        ? std::min({residual_hours, need / person->efficiency,
                                    affordable_hours})
                        : (affordable_hours + kLaborTolerance >= 1.0 ? 1.0 : 0.0);
                if (hours <= kLaborTolerance) {
                    continue;
                }
                const auto existing_primary_id =
                    scratch_.employment_.primary_job(person_id);
                const auto *existing_primary =
                    scratch_.employment_.get(existing_primary_id);
                if (existing_primary != nullptr && existing_primary->active &&
                    existing_primary->suspended) {
                    // A suspended contract preserves a valuable recall option.  A
                    // worker accepts an outside match only when its posted wage
                    // clears the configured fraction of the old contractual wage.
                    if (firm_id == existing_primary->firm ||
                        work.posted_wage + kLaborTolerance <
                            runtime_.rules.suspension_quit_discount *
                                existing_primary->wage) {
                        continue;
                    }
                    const auto separated = separate_job(
                        scratch_.employment_, existing_primary_id, calendar_day,
                        core::SeparationKind::cash_layoff, scratch_.labor_accounts_);
                    if (!separated.ok()) {
                        return separated;
                    }
                    scratch_.labor_accounts_.suspension_poaches_total += 1.0;
                    scratch_.working_metrics_.separations += 1.0;
                }
                const auto hired =
                    hire_job(scratch_.employment_, person_id, firm_id, calendar_day,
                             work.posted_wage, hours, false, scratch_.labor_accounts_);
                if (!hired.ok()) {
                    return hired.status();
                }
                const double hired_labor = hours * person->efficiency;
                need = std::max(0.0, need - hired_labor);
                active_labor += hired_labor;
                payroll += hours * hourly_cost;
                scratch_.working_metrics_.hires += 1.0;
                if (runtime_.rules.second_jobs && hours < 1.0 - kLaborTolerance) {
                    scratch_.second_job_candidates_.push_back(person_id);
                }
            }

            while (runtime_.rules.second_jobs && need > kLaborTolerance &&
                   second_job_cursor < second_job_eligible_end) {
                const auto person_id =
                    scratch_.second_job_candidates_[second_job_cursor++];
                const auto *primary = scratch_.employment_.get(
                    scratch_.employment_.primary_job(person_id));
                if (primary == nullptr || !primary->active || primary->suspended ||
                    scratch_.employment_.secondary_job(person_id).valid()) {
                    continue;
                }
                if (runtime_.rules.frictional_search &&
                    unit_draw(state.seed, person_id.value(), calendar_day,
                              firm_id.value() ^ kSecondJobStream) >=
                        runtime_.rules.search_intensity) {
                    continue;
                }
                if (primary->firm == firm_id) {
                    scratch_.second_job_candidates_.push_back(person_id);
                    continue;
                }
                const double residual_hours =
                    std::max(0.0, 1.0 - scratch_.employment_.active_hours(person_id));
                const auto *person = scratch_.persons_.get(person_id);
                if (person == nullptr || !person->alive ||
                    person->efficiency <= kLaborTolerance) {
                    return Status(ErrorCode::invariant_violation,
                                  "second-job candidate has invalid worker efficiency");
                }
                const double hourly_cost = work.posted_wage * person->efficiency;
                const double affordable_hours =
                    hourly_cost > kLaborTolerance
                        ? std::max(0.0, payroll_budget - payroll) / hourly_cost
                        : 0.0;
                const double hours = std::min(
                    {residual_hours, need / person->efficiency, affordable_hours});
                if (hours <= kLaborTolerance) {
                    continue;
                }
                const auto hired =
                    hire_job(scratch_.employment_, person_id, firm_id, calendar_day,
                             work.posted_wage, hours, true, scratch_.labor_accounts_);
                if (!hired.ok()) {
                    return hired.status();
                }
                const double hired_labor = hours * person->efficiency;
                need = std::max(0.0, need - hired_labor);
                active_labor += hired_labor;
                payroll += hours * hourly_cost;
            }
        }

        if (runtime_.rules.job_ladder) {
            scratch_.ladder_firms_.clear();
            for (std::size_t firm_index = 0; firm_index < real.firm_ids_.size();
                 ++firm_index) {
                const auto firm_id = real.firm_ids_[firm_index];
                if (real.firm_work_[firm_index].labor_demand_effective -
                        firm_labor_totals(scratch_.employment_, scratch_.persons_,
                                          firm_id)
                            .effective_labor >
                    kLaborTolerance) {
                    scratch_.ladder_firms_.push_back(firm_id);
                }
            }
            for (const auto person_id : scratch_.ladder_candidates_) {
                if (scratch_.ladder_firms_.empty() ||
                    unit_draw(state.seed, person_id.value(), calendar_day,
                              kLadderStream) >=
                        runtime_.rules.ladder_search_intensity) {
                    continue;
                }
                const auto draw = unit_draw(state.seed, person_id.value(), calendar_day,
                                            kLadderFirmStream);
                const auto firm_index = std::min(
                    scratch_.ladder_firms_.size() - 1U,
                    static_cast<std::size_t>(
                        draw * static_cast<double>(scratch_.ladder_firms_.size())));
                const auto destination = scratch_.ladder_firms_[firm_index];
                const auto found = std::lower_bound(real.firm_ids_.begin(),
                                                    real.firm_ids_.end(), destination);
                if (found == real.firm_ids_.end() || *found != destination) {
                    return Status(ErrorCode::invariant_violation,
                                  "job ladder firm index is stale");
                }
                const auto destination_index = static_cast<std::size_t>(
                    std::distance(real.firm_ids_.begin(), found));
                const auto primary_id = scratch_.employment_.primary_job(person_id);
                const auto *primary = scratch_.employment_.get(primary_id);
                if (primary == nullptr || !primary->active || primary->suspended ||
                    primary->firm == destination ||
                    scratch_.employment_.secondary_job(person_id).valid()) {
                    continue;
                }
                const auto &destination_work = real.firm_work_[destination_index];
                const auto destination_labor = firm_labor_totals(
                    scratch_.employment_, scratch_.persons_, destination);
                const double need =
                    std::max(0.0, destination_work.labor_demand_effective -
                                      destination_labor.effective_labor);
                const auto *person = scratch_.persons_.get(person_id);
                if (person == nullptr || !person->alive) {
                    return Status(ErrorCode::invariant_violation,
                                  "job ladder candidate is absent");
                }
                const double effective_labor = primary->hours * person->efficiency;
                const auto *destination_firm = state.firms.get(destination);
                if (destination_firm == nullptr) {
                    return Status(ErrorCode::invariant_violation,
                                  "job ladder destination is absent");
                }
                const auto destination_account =
                    static_cast<std::size_t>(destination_firm->primary_account.value());
                const double destination_budget =
                    std::max(0.0, real.balances_[destination_account]);
                const double new_payroll =
                    primary->hours * destination_work.posted_wage * person->efficiency;
                if (effective_labor > need + kLaborTolerance ||
                    destination_labor.payroll + new_payroll >
                        destination_budget + kLaborTolerance ||
                    destination_work.posted_wage <
                        primary->wage * (1.0 + runtime_.rules.ladder_premium)) {
                    continue;
                }
                const double hours = primary->hours;
                const auto departure = separate_job(
                    scratch_.employment_, primary_id, calendar_day,
                    core::SeparationKind::job_to_job, scratch_.labor_accounts_);
                if (!departure.ok()) {
                    return departure;
                }
                const auto hired =
                    hire_job(scratch_.employment_, person_id, destination, calendar_day,
                             destination_work.posted_wage, hours, false,
                             scratch_.labor_accounts_);
                if (!hired.ok()) {
                    return hired.status();
                }
                scratch_.labor_accounts_.hires_total -= 1.0;
            }
        }

        for (std::size_t firm_index = 0; firm_index < real.firm_ids_.size();
             ++firm_index) {
            const auto firm_id = real.firm_ids_[firm_index];
            const auto *firm = state.firms.get(firm_id);
            if (firm == nullptr) {
                return Status(ErrorCode::invariant_violation,
                              "payroll firm reference is absent");
            }
            const auto account_index =
                static_cast<std::size_t>(firm->primary_account.value());
            if (account_index >= real.balances_.size()) {
                return Status(ErrorCode::invariant_violation,
                              "payroll account projection is stale");
            }
            const double budget = std::max(0.0, real.balances_[account_index]);
            double payroll = 0.0;
            for (const auto job_id : scratch_.employment_.roster(firm_id)) {
                const auto *job = scratch_.employment_.get(job_id);
                if (job == nullptr || !job->active || job->suspended) {
                    continue;
                }
                const auto *person = scratch_.persons_.get(job->person);
                if (person == nullptr || !person->alive) {
                    return Status(ErrorCode::invariant_violation,
                                  "payroll job references an absent person");
                }
                payroll += job->hours * job->wage * person->efficiency;
            }
            if (payroll <= budget + kLaborTolerance) {
                continue;
            }
            scratch_.roster_buffer_.assign(scratch_.employment_.roster(firm_id).begin(),
                                           scratch_.employment_.roster(firm_id).end());
            std::sort(scratch_.roster_buffer_.begin(), scratch_.roster_buffer_.end(),
                      [&](JobId left, JobId right) {
                          const auto *left_job = scratch_.employment_.get(left);
                          const auto *right_job = scratch_.employment_.get(right);
                          if (left_job->hire_day != right_job->hire_day) {
                              return left_job->hire_day > right_job->hire_day;
                          }
                          return left > right;
                      });
            for (const auto job_id : scratch_.roster_buffer_) {
                if (payroll <= budget + kLaborTolerance) {
                    break;
                }
                const auto *job = scratch_.employment_.get(job_id);
                if (job == nullptr || !job->active || job->suspended) {
                    continue;
                }
                const auto *person = scratch_.persons_.get(job->person);
                if (person == nullptr || !person->alive) {
                    return Status(ErrorCode::invariant_violation,
                                  "payroll job references an absent person");
                }
                const double hourly_cost = job->wage * person->efficiency;
                const double job_cost = job->hours * hourly_cost;
                const double excess = std::max(0.0, payroll - budget);
                if (runtime_.rules.fractional_hours && hourly_cost > kLaborTolerance &&
                    job_cost > excess + kLaborTolerance) {
                    const double new_hours =
                        std::max(0.0, job->hours - excess / hourly_cost);
                    if (new_hours > kLaborTolerance) {
                        const auto status =
                            set_job_hours(scratch_.employment_, job_id, new_hours,
                                          scratch_.labor_accounts_);
                        if (!status.ok()) {
                            return status;
                        }
                        payroll -= job_cost - new_hours * hourly_cost;
                        continue;
                    }
                }
                Status status;
                if (runtime_.rules.suspensions && !job->secondary) {
                    status = suspend_job(scratch_.employment_, job_id, calendar_day,
                                         scratch_.labor_accounts_);
                } else {
                    status = separate_job(scratch_.employment_, job_id, calendar_day,
                                          core::SeparationKind::cash_layoff,
                                          scratch_.labor_accounts_);
                }
                if (!status.ok()) {
                    return status;
                }
                payroll -= job_cost;
            }
            if (payroll > budget + kLaborTolerance) {
                return Status(ErrorCode::invariant_violation,
                              "payroll budget enforcement failed");
            }
        }

        for (std::size_t firm_index = 0; firm_index < real.firm_ids_.size();
             ++firm_index) {
            const auto firm_id = real.firm_ids_[firm_index];
            const auto *firm = state.firms.get(firm_id);
            auto &work = real.firm_work_[firm_index];
            for (const auto job_id : scratch_.employment_.roster(firm_id)) {
                const auto *job = scratch_.employment_.get(job_id);
                if (job == nullptr || !job->active || job->suspended) {
                    continue;
                }
                const auto *person = scratch_.persons_.get(job->person);
                const auto *household = state.households.get(person->household);
                if (household == nullptr) {
                    return Status(ErrorCode::invariant_violation,
                                  "job references an absent household");
                }
                const double pay = job->hours * job->wage * person->efficiency;
                const auto transfer_status =
                    stage_m4_transfer(state, real, firm->primary_account,
                                      household->primary_account, pay);
                if (!transfer_status.ok()) {
                    return Status(ErrorCode::insufficient_funds,
                                  "M7 payroll transfer exceeds available money");
                }
                const auto household_index =
                    scratch_.household_work_index_[static_cast<std::size_t>(
                        person->household.value())];
                if (household_index >= real.household_work_.size()) {
                    return Status(ErrorCode::invariant_violation,
                                  "household labor projection is stale");
                }
                auto &household_work = real.household_work_[household_index];
                household_work.income_realized += pay;
                household_work.labor_sold += job->hours;
                work.hired += job->hours * person->efficiency;
                work.wage_bill += pay;
            }
        }
        if (extension_ != nullptr) {
            return extension_->after_labor(
                state, real_runtime, real, monetary, monetary_scratch,
                financial_runtime, financial_scratch, runtime_, scratch_, tick, rng);
        }
        return Status::success();
    }

    Status prepare_household_net_wealth(
        const core::RootState &state, M4Runtime &real_runtime, M4TickScratch &real,
        M5Runtime &monetary, M5TickScratch &monetary_scratch,
        M6Runtime &financial_runtime, M6TickScratch &financial, Tick tick,
        PhiloxRng &rng, std::span<double> net_wealth) override {
        if (extension_ == nullptr) {
            return Status::success();
        }
        return extension_->prepare_household_net_wealth(
            state, real_runtime, real, monetary, monetary_scratch, financial_runtime,
            financial, runtime_, scratch_, tick, rng, net_wealth);
    }

    Status close_day(const core::RootState &state, M4Runtime &real_runtime,
                     M4TickScratch &real, M5Runtime &monetary,
                     M5TickScratch &monetary_scratch, M6Runtime &financial_runtime,
                     M6TickScratch &financial, Tick tick, PhiloxRng &rng) override {
        const auto day = static_cast<std::int64_t>(runtime_.start_calendar_day) +
                         static_cast<std::int64_t>(tick.value()) + 1;
        if (day < std::numeric_limits<std::int32_t>::min() ||
            day > std::numeric_limits<std::int32_t>::max()) {
            return Status(ErrorCode::out_of_range,
                          "M7 calendar day exceeds storage range");
        }
        const auto calendar_day = static_cast<std::int32_t>(day);

        if (runtime_.rules.persistent_labor) {
            for (const auto &exit : financial.firm_exits_) {
                scratch_.roster_buffer_.assign(
                    scratch_.employment_.roster(exit.firm).begin(),
                    scratch_.employment_.roster(exit.firm).end());
                for (const auto job_id : scratch_.roster_buffer_) {
                    const auto status = separate_job(
                        scratch_.employment_, job_id, calendar_day,
                        core::SeparationKind::firm_exit, scratch_.labor_accounts_);
                    if (!status.ok()) {
                        return status;
                    }
                    scratch_.working_metrics_.separations += 1.0;
                }
            }
        }

        if (runtime_.rules.relationships && runtime_.rules.divorce) {
            scratch_.divorce_candidates_.clear();
            for (const auto &union_record : scratch_.relationships_.unions()) {
                if (!union_record.active) {
                    continue;
                }
                const double annual_divorce = annual_divorce_hazard(
                    scratch_.persons_, scratch_.relationships_, union_record,
                    runtime_.rules, calendar_day);
                const double daily_divorce =
                    annual_divorce >= 1.0
                        ? 1.0
                        : 1.0 - std::pow(1.0 - annual_divorce, kDailyYear);
                if (unit_draw(state.seed, union_record.event.value(), calendar_day,
                              kDivorceStream) < daily_divorce) {
                    scratch_.divorce_candidates_.push_back(union_record.first);
                }
            }
            for (const auto person_id : scratch_.divorce_candidates_) {
                const auto event = scratch_.relationships_.active_union(person_id);
                const auto found =
                    std::find_if(scratch_.relationships_.unions().begin(),
                                 scratch_.relationships_.unions().end(),
                                 [event](const core::UnionRecord &record) {
                                     return record.event == event;
                                 });
                if (found == scratch_.relationships_.unions().end()) {
                    return Status(ErrorCode::invariant_violation,
                                  "divorce union is absent");
                }
                const auto second = found->second;
                const auto second_origin = found->second_origin_household;
                const auto status = scratch_.relationships_.divorce(
                    scratch_.persons_, person_id, calendar_day);
                if (!status.ok()) {
                    return status;
                }
                if (runtime_.rules.household_lifecycle &&
                    state.households.get(second_origin) != nullptr) {
                    auto move_status = scratch_.membership_.move(second, second_origin);
                    if (!move_status.ok()) {
                        return move_status;
                    }
                    scratch_.persons_.get(second)->household = second_origin;
                }
                ++scratch_.working_metrics_.divorces;
            }
        }

        if (runtime_.rules.relationships && runtime_.rules.marriage &&
            calendar_day %
                    static_cast<std::int32_t>(runtime_.rules.marriage_interval_days) ==
                0) {
            const auto matches = core::exact_marriage_matches(
                scratch_.persons_, scratch_.membership_, runtime_.rules.marriage_rules,
                calendar_day);
            if (!matches.ok()) {
                return matches.status();
            }
            const double interval_years =
                static_cast<double>(runtime_.rules.marriage_interval_days) /
                kDaysPerYear;
            for (const auto &match : *matches.get_if()) {
                const auto *first = scratch_.persons_.get(match.first);
                const auto *second = scratch_.persons_.get(match.second);
                if (first == nullptr || second == nullptr) {
                    return Status(ErrorCode::invariant_violation,
                                  "marriage match references an absent person");
                }
                const double first_rate = annual_marriage_entry_rate(
                    *first, runtime_.rules, calendar_day);
                const double second_rate = annual_marriage_entry_rate(
                    *second, runtime_.rules, calendar_day);
                const double annual_pair_rate =
                    std::sqrt(first_rate * second_rate);
                const double entry_probability =
                    annual_pair_rate >= 1.0
                        ? 1.0
                        : 1.0 - std::pow(1.0 - annual_pair_rate,
                                         interval_years);
                const double signed_gap = completed_age(*second, calendar_day) -
                                          completed_age(*first, calendar_day);
                const double gap_z =
                    (signed_gap -
                     runtime_.rules.marriage_rules.preferred_age_gap) /
                    runtime_.rules.marriage_age_gap_stddev;
                const double gap_density = std::exp(-0.5 * gap_z * gap_z);
                const double compatibility = std::clamp(
                    (runtime_.rules.marriage_acceptance_base -
                     runtime_.rules.marriage_acceptance_age_gap_penalty *
                         std::abs(signed_gap)) *
                        gap_density,
                    0.0, 1.0);
                const double acceptance = entry_probability * compatibility;
                const auto pair_identity =
                    splitmix64(match.first.value()) ^ splitmix64(match.second.value());
                if (unit_draw(state.seed, pair_identity, calendar_day,
                              kMarriageStream) >= acceptance) {
                    continue;
                }
                const bool remarriage = first->marriage_count > 0U ||
                                        second->marriage_count > 0U;
                const bool widowed_remarriage = first->last_widowed_day >= 0 ||
                                                second->last_widowed_day >= 0;
                const auto event = EventId(scratch_.next_event_id_++);
                const auto status = scratch_.relationships_.marry(
                    scratch_.persons_, event, match.first, match.second, calendar_day);
                if (!status.ok()) {
                    return status;
                }
                if (runtime_.rules.household_lifecycle) {
                    const auto destination =
                        scratch_.membership_.household_of(match.first);
                    auto move_status =
                        scratch_.membership_.move(match.second, destination);
                    if (!move_status.ok()) {
                        return move_status;
                    }
                    scratch_.persons_.get(match.second)->household = destination;
                }
                ++scratch_.working_metrics_.marriages;
                scratch_.working_metrics_.remarriages += remarriage ? 1U : 0U;
                scratch_.working_metrics_.widowed_remarriages +=
                    widowed_remarriage ? 1U : 0U;
            }
        }

        if ((runtime_.rules.household_lifecycle && runtime_.rules.leaving_home) ||
            options_.force_leave_home.has_value()) {
            auto next_household = state.households.allocator_state().next_id;
            for (std::uint64_t identity = 1; identity < scratch_.persons_.next_id();
                 ++identity) {
                const auto person_id = PersonId(identity);
                const auto *person = scratch_.persons_.get(person_id);
                const bool forced = options_.force_leave_home.has_value() &&
                                    *options_.force_leave_home == person_id;
                if (person == nullptr || !person->alive || person->partner.valid()) {
                    if (forced) {
                        return Status(ErrorCode::invalid_argument,
                                      "forced leaving-home target is ineligible");
                    }
                    continue;
                }
                const double age = completed_age(*person, calendar_day);
                if (age < static_cast<double>(runtime_.rules.leave_home_min_age)) {
                    if (forced) {
                        return Status(ErrorCode::invalid_argument,
                                      "forced leaving-home target is too young");
                    }
                    continue;
                }
                bool lives_with_parent = false;
                for (const auto parent : std::array{
                         person->mother,
                         person->father,
                     }) {
                    const auto *parent_record = scratch_.persons_.get(parent);
                    lives_with_parent =
                        lives_with_parent ||
                        (parent_record != nullptr && parent_record->alive &&
                         parent_record->household == person->household);
                }
                if (!lives_with_parent ||
                    scratch_.membership_.members(person->household).size() <= 1U) {
                    if (forced) {
                        return Status(
                            ErrorCode::invalid_argument,
                            "forced leaving-home target has no co-resident parent");
                    }
                    continue;
                }
                const double annual_rate =
                    age <= static_cast<double>(runtime_.rules.leave_home_peak_end_age)
                        ? runtime_.rules.annual_leave_rate_peak
                        : runtime_.rules.annual_leave_rate_late;
                const double probability =
                    std::clamp(annual_rate * scratch_.external_leave_home_multiplier_ /
                                   kDaysPerYear,
                               0.0, 1.0);
                if (!forced && unit_draw(state.seed, person_id.value(), calendar_day,
                                         kLeavingHomeStream) >= probability) {
                    continue;
                }
                const LeavingHomeRecord event{
                    EventId(scratch_.next_event_id_++), person_id,    person->household,
                    HouseholdId(next_household++),      calendar_day,
                };
                scratch_.leaving_home_.push_back(event);
                scratch_.pending_leaving_home_.push_back(event);
                ++scratch_.working_metrics_.leaving_home_events;
            }
            if (options_.force_leave_home.has_value() &&
                std::none_of(scratch_.pending_leaving_home_.begin(),
                             scratch_.pending_leaving_home_.end(),
                             [&](const LeavingHomeRecord &event) {
                                 return event.person == *options_.force_leave_home;
                             })) {
                return Status(ErrorCode::contract_violation,
                              "forced leaving-home target was not scheduled");
            }
        }

        if (runtime_.rules.fertility || options_.force_birth.has_value()) {
            scratch_.fertility_candidates_.clear();
            for (const auto person_id : scratch_.persons_.alive_ids()) {
                const auto *person = scratch_.persons_.get(person_id);
                const double age = completed_age(*person, calendar_day);
                const bool forced = options_.force_birth.has_value() &&
                                    *options_.force_birth == person_id;
                if (person->sex != core::PersonSex::female || age < 15.0 ||
                    age > 49.0) {
                    if (forced) {
                        return Status(ErrorCode::invalid_argument,
                                      "forced birth target is ineligible");
                    }
                    continue;
                }
                const auto annual_rate =
                    algorithms::fertility_rate(runtime_.rules.vital_rates, age);
                if (!annual_rate.ok()) {
                    return annual_rate.status();
                }
                const double probability =
                    runtime_.rules.fertility
                        ? 1.0 - std::exp(-*annual_rate.get_if() *
                                         scratch_.external_fertility_multiplier_ *
                                         scratch_
                                             .demographic_signal_fertility_multiplier_ *
                                         household_rank_multiplier(
                                             person->household,
                                             std::span<const double>(
                                                 scratch_
                                                     .household_fertility_multiplier_)) *
                                         kDailyYear)
                        : 0.0;
                if (forced || unit_draw(state.seed, person_id.value(), calendar_day,
                                        kFertilityStream) < probability) {
                    scratch_.fertility_candidates_.push_back(person_id);
                }
            }
            if (options_.force_birth.has_value() &&
                !scratch_.persons_.alive(*options_.force_birth)) {
                return Status(ErrorCode::contract_violation,
                              "forced birth target is not alive");
            }
            const auto female_share =
                algorithms::female_birth_share(runtime_.rules.vital_rates);
            if (!female_share.ok()) {
                return female_share.status();
            }
            for (const auto mother_id : scratch_.fertility_candidates_) {
                const auto *mother = scratch_.persons_.get(mother_id);
                const auto mother_household = mother->household;
                const auto father = scratch_.persons_.alive(mother->partner)
                                        ? mother->partner
                                        : PersonId{};
                core::PersonRecord baby;
                baby.sex = unit_draw(state.seed, mother_id.value(), calendar_day,
                                     kSexStream) < *female_share.get_if()
                               ? core::PersonSex::female
                               : core::PersonSex::male;
                baby.birth_day = calendar_day;
                baby.mother = mother_id;
                baby.father = father;
                baby.guardian = mother_id;
                baby.household = mother_household;
                const auto created = scratch_.persons_.create(baby);
                if (!created.ok()) {
                    return created.status();
                }
                scratch_.persons_.get(*created.get_if())->efficiency =
                    person_efficiency_draw(runtime_.rules, state.seed,
                                           *created.get_if(), calendar_day);
                const auto status =
                    scratch_.membership_.add(*created.get_if(), baby.household);
                if (!status.ok()) {
                    return status;
                }
                const auto lineage = scratch_.relationships_.register_birth(
                    scratch_.persons_, *created.get_if());
                if (!lineage.ok()) {
                    return lineage;
                }
                ++scratch_.working_metrics_.births;
                const auto wealth_quintile = household_wealth_quintile(
                    mother_household,
                    std::span<const std::uint8_t>(
                        scratch_.household_wealth_quintile_));
                if (wealth_quintile == 0U) {
                    ++scratch_.working_metrics_.bottom_wealth_quintile_births;
                } else if (wealth_quintile == kWealthQuintiles - 1U) {
                    ++scratch_.working_metrics_.top_wealth_quintile_births;
                }
            }
        }
        for (const auto household : scratch_.retired_households_) {
            const auto found =
                std::find_if(scratch_.estates_.rbegin(), scratch_.estates_.rend(),
                             [household, calendar_day](const EstateRecord &estate) {
                                 return estate.household == household &&
                                        estate.settled &&
                                        estate.settled_day == calendar_day;
                             });
            const auto destination = found == scratch_.estates_.rend()
                                         ? HouseholdId{}
                                         : found->destination_household;
            const auto residual_status =
                transfer_household_residual(state, real, monetary_scratch, financial,
                                            scratch_.beneficial_ownership_, household,
                                            destination, scratch_.estate_securities_);
            if (!residual_status.ok()) {
                return residual_status;
            }
        }
        real.supplemental_tax_receipts_ +=
            scratch_.working_metrics_.inheritance_tax_paid;
        if (government_enabled(real_runtime) &&
            runtime_.policy.pension_replacement > kLaborTolerance) {
            const double wage_reference =
                std::max(scratch_.working_metrics_.mean_hourly_wage,
                         runtime_.last_metrics.mean_hourly_wage);
            const double pension = runtime_.policy.pension_replacement * wage_reference;
            if (pension > kLaborTolerance) {
                for (const auto person_id : scratch_.persons_.alive_ids()) {
                    const auto *person = scratch_.persons_.get(person_id);
                    if (person == nullptr ||
                        completed_age(*person, calendar_day) <
                            static_cast<double>(runtime_.rules.retirement_age)) {
                        continue;
                    }
                    const auto *household = state.households.get(person->household);
                    if (household == nullptr) {
                        return Status(ErrorCode::invariant_violation,
                                      "pension recipient household is absent");
                    }
                    const auto status = stage_m4_transfer(
                        state, real, state.institutions.treasury_account,
                        household->primary_account, pension);
                    if (!status.ok()) {
                        return status;
                    }
                    scratch_.working_metrics_.pension_paid += pension;
                    real.supplemental_transfer_payments_ += pension;
                }
            }
        }
        if (extension_ != nullptr) {
            const auto extension_status = extension_->close_day(
                state, real_runtime, real, monetary, monetary_scratch,
                financial_runtime, financial, runtime_, scratch_, tick, rng);
            if (!extension_status.ok()) {
                return extension_status;
            }
        }
        if (runtime_.rules.beneficial_ownership) {
            const auto ownership_status = synchronize_beneficial_claims(
                state, real, monetary_scratch.loans_, financial.securities_,
                scratch_.membership_, scratch_.persons_, scratch_.beneficial_ownership_,
                scratch_.beneficial_assets_);
            if (!ownership_status.ok()) {
                return ownership_status;
            }
        }
        ++scratch_.population_rng_counter_;
        const auto signal_year = calendar_year_from_ordinal(calendar_day);
        if (scratch_.demographic_signal_year_ == 0) {
            scratch_.demographic_signal_year_ = signal_year;
        } else if (signal_year != scratch_.demographic_signal_year_) {
            finalize_demographic_signal_year(runtime_.rules, scratch_);
            scratch_.demographic_signal_year_ = signal_year;
        }
        double wage_sum = 0.0;
        double price_sum = 0.0;
        std::size_t priced_firms = 0U;
        for (const auto &work : real.firm_work_) {
            if (work.posted_price > kLaborTolerance) {
                price_sum += work.posted_price;
                ++priced_firms;
            }
        }
        // Use employment-adjusted contractual labor income, not cash payroll
        // conditional on having been hired.  The cash quotient can rise in a
        // deep contraction when low-paying or cash-constrained jobs disappear,
        // causing the demographic feedback to misread mass job loss as an
        // improvement in living standards.  Working-age people without active
        // hours remain in the denominator with zero labor income.
        double working_age_population = 0.0;
        for (const auto person_id : scratch_.persons_.alive_ids()) {
            const auto *person = scratch_.persons_.get(person_id);
            const double age = completed_age(*person, calendar_day);
            const bool working_age =
                age >= static_cast<double>(runtime_.rules.working_age) &&
                age < static_cast<double>(runtime_.rules.retirement_age);
            if (!working_age) {
                continue;
            }
            working_age_population += 1.0;
            for (const auto job_id : std::array{
                     scratch_.employment_.primary_job(person_id),
                     scratch_.employment_.secondary_job(person_id)}) {
                const auto *job = scratch_.employment_.get(job_id);
                if (job != nullptr && job->active && !job->suspended) {
                    wage_sum += std::max(
                        0.0, job->wage * job->hours * person->efficiency);
                }
            }
        }
        scratch_.demographic_signal_wage_sum_ += wage_sum;
        scratch_.demographic_signal_labor_sum_ += working_age_population;
        scratch_.demographic_signal_price_sum_ +=
            priced_firms > 0U ? price_sum / static_cast<double>(priced_firms)
                              : std::max(kLaborTolerance,
                                         real_runtime.last_metrics.price_index);
        ++scratch_.demographic_signal_days_;
        scratch_.working_metrics_.demographic_real_wage_signal =
            scratch_.demographic_signal_x_;
        scratch_.working_metrics_.demographic_fertility_multiplier =
            scratch_.demographic_signal_fertility_multiplier_;
        scratch_.working_metrics_.demographic_mortality_multiplier =
            scratch_.demographic_signal_mortality_multiplier_;
        measure_population(state, runtime_.rules, scratch_.persons_,
                           scratch_.membership_, scratch_.relationships_, calendar_day,
                           scratch_.working_metrics_);
        if (runtime_.rules.persistent_labor) {
            measure_labor(state, runtime_.rules, monetary.policy, scratch_.persons_,
                          scratch_.employment_, real, calendar_day,
                          scratch_.labor_accounts_, scratch_.working_metrics_);
            const auto flow_delta = [](double closing, double opening) {
                return std::max(0.0, closing - opening);
            };
            const auto &opening = runtime_.labor_accounts;
            const auto &closing = scratch_.labor_accounts_;
            scratch_.working_metrics_.churn_separations = flow_delta(
                closing.churn_separations_total, opening.churn_separations_total);
            const double layoff_separations = flow_delta(
                closing.layoff_separations_total, opening.layoff_separations_total);
            scratch_.working_metrics_.cash_layoff_separations =
                flow_delta(closing.cash_layoffs_total, opening.cash_layoffs_total);
            scratch_.working_metrics_.demand_layoff_separations =
                std::max(0.0, layoff_separations -
                                  scratch_.working_metrics_.cash_layoff_separations);
            scratch_.working_metrics_.firm_exit_separations =
                flow_delta(closing.firm_exit_separations_total,
                           opening.firm_exit_separations_total);
            scratch_.working_metrics_.death_separations = flow_delta(
                closing.death_separations_total, opening.death_separations_total);
            scratch_.working_metrics_.retirement_separations =
                flow_delta(closing.retirement_separations_total,
                           opening.retirement_separations_total);
            scratch_.working_metrics_.welfare_quits =
                flow_delta(closing.welfare_quits_total, opening.welfare_quits_total);
            scratch_.working_metrics_.suspensions_flow =
                flow_delta(closing.suspensions_total, opening.suspensions_total);
            scratch_.working_metrics_.suspension_poaches = flow_delta(
                closing.suspension_poaches_total,
                opening.suspension_poaches_total);
            scratch_.working_metrics_.recalls =
                flow_delta(closing.recalls_total, opening.recalls_total);
            scratch_.working_metrics_.job_to_job_moves = flow_delta(
                closing.job_to_job_moves_total, opening.job_to_job_moves_total);
            const auto job_records = scratch_.employment_.records().size();
            const auto active_jobs = scratch_.employment_.active_count();
            const auto inactive_jobs =
                job_records > 0U && job_records - 1U > active_jobs
                    ? job_records - 1U - active_jobs
                    : 0U;
            const auto compaction_threshold =
                std::max<std::size_t>(4096U, active_jobs / 8U);
            if (inactive_jobs > compaction_threshold) {
                const auto compacted = scratch_.employment_.compact_inactive();
                if (!compacted.ok()) {
                    return compacted;
                }
            }
        }
        scratch_.working_metrics_.beneficial_projection_error =
            beneficial_projection_error(scratch_.beneficial_ownership_);
        return Status::success();
    }

    Status after_financial_lifecycle(const core::RootState &state,
                                     M4Runtime &real_runtime, M4TickScratch &real,
                                     M5Runtime &monetary_runtime,
                                     M5TickScratch &monetary,
                                     M6Runtime &financial_runtime,
                                     M6TickScratch &financial, Tick tick,
                                     PhiloxRng &rng) override {
        if (extension_ == nullptr) {
            return Status::success();
        }
        return extension_->after_financial_lifecycle(
            state, real_runtime, real, monetary_runtime, monetary, financial_runtime,
            financial, runtime_, scratch_, tick, rng);
    }

    Status validate(const core::RootState &state, const M4Runtime &real_runtime,
                    const M4TickScratch &real, const M5Runtime &monetary_runtime,
                    const M5TickScratch &monetary, const M6Runtime &financial_runtime,
                    const M6TickScratch &financial, Tick tick) const override {
        auto status = scratch_.persons_.validate();
        if (status.ok()) {
            status = scratch_.membership_.validate(scratch_.persons_, state);
        }
        if (status.ok() && runtime_.rules.beneficial_ownership) {
            status = scratch_.beneficial_ownership_.validate_fast(
                scratch_.persons_, state.accounting_tolerance);
        }
        if (status.ok() && runtime_.rules.persistent_labor) {
            status = scratch_.employment_.validate(scratch_.persons_, state,
                                                   state.accounting_tolerance);
        }
        if (status.ok() && runtime_.rules.persistent_labor) {
            status = core::validate_labor_accounts(scratch_.labor_accounts_,
                                                   state.accounting_tolerance);
        }
        if (status.ok() && runtime_.rules.relationships) {
            status = scratch_.relationships_.validate(scratch_.persons_);
        }
        if (status.ok() && (!std::isfinite(scratch_.external_leave_home_multiplier_) ||
                            scratch_.external_leave_home_multiplier_ <= 0.0 ||
                            !std::isfinite(scratch_.external_fertility_multiplier_) ||
                            scratch_.external_fertility_multiplier_ <= 0.0 ||
                            !std::isfinite(scratch_.external_mortality_multiplier_) ||
                            scratch_.external_mortality_multiplier_ <= 0.0)) {
            status = Status(ErrorCode::invariant_violation,
                            "M7 external demographic multiplier is invalid");
        }
        if (!status.ok()) {
            return status;
        }
        if (extension_ != nullptr) {
            status = extension_->validate(state, real_runtime, real, monetary_runtime,
                                          monetary, financial_runtime, financial,
                                          runtime_, scratch_, tick);
            if (!status.ok()) {
                return status;
            }
        }
        if (options_.fault_before_population_commit) {
            return Status(ErrorCode::internal_error, "injected M7 pre-commit fault");
        }
        return Status::success();
    }

    void commit(core::RootState &state, M4Runtime &real_runtime, M4TickScratch &real,
                M5Runtime &monetary_runtime, M5TickScratch &monetary,
                M6Runtime &financial_runtime, M6TickScratch &financial, Tick tick,
                const M6Metrics &metrics) noexcept override {
        if (memory_efficient_staging_) {
            runtime_.persons = std::move(scratch_.persons_);
            runtime_.membership = std::move(scratch_.membership_);
            runtime_.beneficial_ownership = std::move(scratch_.beneficial_ownership_);
            runtime_.employment = std::move(scratch_.employment_);
            runtime_.relationships = std::move(scratch_.relationships_);
            runtime_.firm_target_ema = std::move(scratch_.firm_target_ema_);
            runtime_.estates = std::move(scratch_.estates_);
            runtime_.leaving_home = std::move(scratch_.leaving_home_);
            runtime_.household_wealth_quintile =
                std::move(scratch_.household_wealth_quintile_);
            runtime_.household_mortality_multiplier =
                std::move(scratch_.household_mortality_multiplier_);
            runtime_.household_fertility_multiplier =
                std::move(scratch_.household_fertility_multiplier_);
        } else {
            std::swap(runtime_.persons, scratch_.persons_);
            std::swap(runtime_.membership, scratch_.membership_);
            std::swap(runtime_.beneficial_ownership, scratch_.beneficial_ownership_);
            std::swap(runtime_.employment, scratch_.employment_);
            std::swap(runtime_.relationships, scratch_.relationships_);
            std::swap(runtime_.firm_target_ema, scratch_.firm_target_ema_);
            std::swap(runtime_.estates, scratch_.estates_);
            std::swap(runtime_.leaving_home, scratch_.leaving_home_);
            std::swap(runtime_.household_wealth_quintile,
                      scratch_.household_wealth_quintile_);
            std::swap(runtime_.household_mortality_multiplier,
                      scratch_.household_mortality_multiplier_);
            std::swap(runtime_.household_fertility_multiplier,
                      scratch_.household_fertility_multiplier_);
        }
        runtime_.stratification_snapshot_day =
            scratch_.stratification_snapshot_day_;
        runtime_.mortality_quintile_multiplier =
            scratch_.mortality_quintile_multiplier_;
        runtime_.fertility_quintile_multiplier =
            scratch_.fertility_quintile_multiplier_;
        runtime_.labor_accounts = scratch_.labor_accounts_;
        runtime_.next_event_id = scratch_.next_event_id_;
        runtime_.population_rng_counter = scratch_.population_rng_counter_;
        const auto calendar_day =
            runtime_.start_calendar_day + static_cast<std::int32_t>(tick.value()) + 1;
        for (const auto household : scratch_.retired_households_) {
            const auto *component = state.households.get(household);
            if (component == nullptr) {
                continue;
            }
            const auto estate =
                std::find_if(runtime_.estates.rbegin(), runtime_.estates.rend(),
                             [household, calendar_day](const EstateRecord &record) {
                                 return record.household == household &&
                                        record.settled &&
                                        record.settled_day == calendar_day;
                             });
            const auto destination =
                estate != runtime_.estates.rend() &&
                        estate->destination_household.valid()
                    ? core::OwnerId::household(estate->destination_household)
                    : core::OwnerId::institutional(core::OwnerKind::treasury);
            const auto ownership_status = state.ownership.rekey_owner(
                core::OwnerId::household(household), destination);
            if (!ownership_status.ok()) {
                std::terminate();
            }
            const auto *account = state.postings.get(component->primary_account);
            if (account == nullptr ||
                std::abs(account->balance.value()) > state.accounting_tolerance) {
                std::terminate();
            }
            const auto close_status =
                state.postings.close_account(component->primary_account);
            if (!close_status.ok()) {
                std::terminate();
            }
            const auto removed = state.households.remove(household);
            if (!removed.ok()) {
                std::terminate();
            }
            const auto index = static_cast<std::size_t>(household.value());
            if (index < financial_runtime.watchlist_rows.size()) {
                financial_runtime.watchlist_rows[index] = M6WatchlistRow{};
            }
        }
        for (const auto &event : scratch_.pending_leaving_home_) {
            auto *person = runtime_.persons.get(event.person);
            const auto *origin = state.households.get(event.origin);
            if (person == nullptr || !person->alive || origin == nullptr ||
                person->household != event.origin ||
                state.households.allocator_state().next_id !=
                    event.destination.value()) {
                std::terminate();
            }
            const auto *origin_account = state.postings.get(origin->primary_account);
            if (origin_account == nullptr) {
                std::terminate();
            }
            const auto origin_account_id = origin->primary_account;
            const auto origin_settlement_node = origin_account->key.settlement_node;
            const double origin_balance = origin_account->balance.value();
            core::HouseholdComponent component;
            component.income_propensity = origin->income_propensity;
            component.wealth_propensity = origin->wealth_propensity;
            component.income_adjustment = origin->income_adjustment;
            const auto created = state.households.create(component);
            if (!created.ok() || created.get_if()->id != event.destination) {
                std::terminate();
            }
            const auto financial_household_slots = static_cast<std::size_t>(
                state.households.allocator_state().next_id);
            if (financial_runtime.household_equity_value_ema.size() <
                financial_household_slots) {
                financial_runtime.household_equity_value_ema.resize(
                    financial_household_slots, 0.0);
            }
            const auto account = state.postings.create_account(
                {
                    core::AccountKind::deposit,
                    state.economy,
                    core::OwnerId::household(event.destination),
                    state.currency,
                    origin_settlement_node,
                },
                Money(0.0));
            if (!account.ok()) {
                std::terminate();
            }
            state.households.get(event.destination)->primary_account =
                *account.get_if();

            const core::BeneficialAssetKey origin_cash{
                core::BeneficialAssetKind::household_cash,
                event.origin,
                event.origin.value(),
            };
            double cash_share = 0.0;
            std::vector<BeneficialLotId> person_cash_lots;
            for (const auto lot_id :
                 runtime_.beneficial_ownership.lots_for_person(event.person)) {
                const auto *lot = runtime_.beneficial_ownership.get(lot_id);
                if (lot != nullptr && lot->is_active() && lot->asset == origin_cash) {
                    person_cash_lots.push_back(lot_id);
                    cash_share += lot->share;
                }
            }
            const auto family_owner = first_alive_member(
                runtime_.membership, runtime_.persons, event.origin, event.person);
            if (!person_cash_lots.empty() && !family_owner.valid()) {
                std::terminate();
            }
            for (const auto lot_id : person_cash_lots) {
                const auto *lot = runtime_.beneficial_ownership.get(lot_id);
                const auto transfer_status = runtime_.beneficial_ownership.transfer(
                    lot_id, family_owner, lot->share);
                if (!transfer_status.ok()) {
                    std::terminate();
                }
            }
            const core::BeneficialAssetKey destination_cash{
                core::BeneficialAssetKind::household_cash,
                event.destination,
                event.destination.value(),
            };
            const auto beneficial = runtime_.beneficial_ownership.create_lot(
                destination_cash, event.person, 1.0);
            if (!beneficial.ok()) {
                std::terminate();
            }
            const double cash = std::max(0.0, origin_balance * cash_share);
            if (cash > kLaborTolerance) {
                core::SettlementTransaction transaction(state);
                const auto transfer_status = transaction.transfer(
                    origin_account_id, *account.get_if(), Money(cash));
                if (!transfer_status.ok()) {
                    std::terminate();
                }
                if (!transaction.commit_locally_validated().ok()) {
                    std::terminate();
                }
            }
            const auto move_status =
                runtime_.membership.move(event.person, event.destination);
            if (!move_status.ok()) {
                std::terminate();
            }
            person->household = event.destination;

            const auto origin_index = static_cast<std::size_t>(event.origin.value());
            if (financial_runtime.watchlist_rows.size() <= event.destination.value()) {
                financial_runtime.watchlist_rows.resize(
                    static_cast<std::size_t>(event.destination.value() + 1U));
            }
            auto &destination_row =
                financial_runtime.watchlist_rows[static_cast<std::size_t>(
                    event.destination.value())];
            destination_row.household = event.destination;
            const auto destination_offset = financial_runtime.watchlist_equities.size();
            if (destination_offset > std::numeric_limits<std::uint32_t>::max()) {
                std::terminate();
            }
            destination_row.offset = static_cast<std::uint32_t>(destination_offset);
            if (origin_index < financial_runtime.watchlist_rows.size()) {
                const auto origin_row = financial_runtime.watchlist_rows[origin_index];
                destination_row.count = origin_row.count;
                const auto source_offset = static_cast<std::size_t>(origin_row.offset);
                const auto source_count = static_cast<std::size_t>(origin_row.count);
                if (source_offset > financial_runtime.watchlist_equities.size() ||
                    source_count >
                        financial_runtime.watchlist_equities.size() - source_offset) {
                    std::terminate();
                }
                const std::vector<EquityId> inherited_watchlist(
                    financial_runtime.watchlist_equities.begin() +
                        static_cast<std::ptrdiff_t>(source_offset),
                    financial_runtime.watchlist_equities.begin() +
                        static_cast<std::ptrdiff_t>(source_offset + source_count));
                financial_runtime.watchlist_equities.insert(
                    financial_runtime.watchlist_equities.end(),
                    inherited_watchlist.begin(), inherited_watchlist.end());
            }
        }
        scratch_.working_metrics_.economy = metrics;
        runtime_.last_metrics = scratch_.working_metrics_;
        runtime_.demographic_signal_year = scratch_.demographic_signal_year_;
        runtime_.demographic_signal_years_completed =
            scratch_.demographic_signal_years_completed_;
        runtime_.demographic_signal_ewma = scratch_.demographic_signal_ewma_;
        runtime_.demographic_signal_baseline =
            scratch_.demographic_signal_baseline_;
        runtime_.demographic_signal_x = scratch_.demographic_signal_x_;
        runtime_.demographic_signal_fertility_multiplier =
            scratch_.demographic_signal_fertility_multiplier_;
        runtime_.demographic_signal_mortality_multiplier =
            scratch_.demographic_signal_mortality_multiplier_;
        runtime_.demographic_signal_last_real_wage =
            scratch_.demographic_signal_last_real_wage_;
        runtime_.demographic_signal_wage_sum =
            scratch_.demographic_signal_wage_sum_;
        runtime_.demographic_signal_labor_sum =
            scratch_.demographic_signal_labor_sum_;
        runtime_.demographic_signal_price_sum =
            scratch_.demographic_signal_price_sum_;
        runtime_.demographic_signal_days = scratch_.demographic_signal_days_;
        runtime_.current_calendar_day =
            runtime_.start_calendar_day + static_cast<std::int32_t>(tick.value()) + 1;
        if (extension_ != nullptr) {
            extension_->commit(state, real_runtime, real, monetary_runtime, monetary,
                               financial_runtime, financial, runtime_, scratch_, tick,
                               runtime_.last_metrics);
        }
        committed_ = true;
    }

  private:
    M7Runtime &runtime_;
    M7TickScratch &scratch_;
    const M7AdvanceOptions &options_;
    M7TickExtension *extension_{nullptr};
    bool memory_efficient_staging_{false};
    bool committed_{false};
};

constexpr std::uint64_t kNoGenesisPerson =
    std::numeric_limits<std::uint64_t>::max();

struct GenesisPersonPlan final {
    core::PersonSex sex{core::PersonSex::female};
    std::uint32_t age{0};
    std::int32_t birth_day{0};
    std::uint64_t household_index{kNoGenesisPerson};
    std::uint64_t partner_index{kNoGenesisPerson};
    std::uint64_t mother_index{kNoGenesisPerson};
    std::uint64_t father_index{kNoGenesisPerson};
    std::uint64_t guardian_index{kNoGenesisPerson};
};

struct GenesisRelationshipPlan final {
    std::vector<GenesisPersonPlan> people;
    std::uint64_t household_count{0};
};

using GenesisAgeBuckets = std::vector<std::vector<std::uint64_t>>;

[[nodiscard]] std::uint64_t pop_genesis_partner(
    GenesisAgeBuckets &male_by_age, const std::vector<GenesisPersonPlan> &people,
    double female_age, double target_age, std::uint32_t maximum_gap) {
    std::uint64_t selected{kNoGenesisPerson};
    double selected_distance = std::numeric_limits<double>::infinity();
    std::uint32_t selected_age = 0U;
    const auto minimum_age = static_cast<std::int32_t>(std::max(
        0.0, female_age - static_cast<double>(maximum_gap)));
    const auto maximum_age = static_cast<std::int32_t>(
        female_age + static_cast<double>(maximum_gap));
    for (auto age = minimum_age; age <= maximum_age; ++age) {
        if (age < 0 || static_cast<std::size_t>(age) >= male_by_age.size()) {
            continue;
        }
        auto &bucket = male_by_age[static_cast<std::size_t>(age)];
        while (!bucket.empty() &&
               people[static_cast<std::size_t>(bucket.back())].partner_index !=
                   kNoGenesisPerson) {
            bucket.pop_back();
        }
        if (bucket.empty()) {
            continue;
        }
        const double distance = std::abs(static_cast<double>(age) - target_age);
        if (distance < selected_distance ||
            (distance == selected_distance &&
             static_cast<std::uint32_t>(age) < selected_age)) {
            selected = bucket.back();
            selected_distance = distance;
            selected_age = static_cast<std::uint32_t>(age);
        }
    }
    if (selected != kNoGenesisPerson) {
        male_by_age[selected_age].pop_back();
    }
    return selected;
}

void match_genesis_partners(GenesisRelationshipPlan &plan,
                            const M7Rules &rules, std::uint64_t seed,
                            std::int32_t day) {
    auto &people = plan.people;
    std::vector<std::uint64_t> females;
    GenesisAgeBuckets male_by_age(1U);
    for (std::uint64_t index = 0; index < people.size(); ++index) {
        const auto &person = people[static_cast<std::size_t>(index)];
        if (person.age < rules.working_age) {
            continue;
        }
        if (male_by_age.size() <= person.age) {
            male_by_age.resize(static_cast<std::size_t>(person.age) + 1U);
        }
        if (person.sex == core::PersonSex::female) {
            females.push_back(index);
        } else {
            male_by_age[person.age].push_back(index);
        }
    }
    const auto random_order = [seed, day](std::uint64_t left,
                                          std::uint64_t right) {
        const auto left_key = splitmix64(
            seed ^ splitmix64(left + 1U) ^
            splitmix64(static_cast<std::uint64_t>(day)) ^
            kGenesisPartnerOrderStream);
        const auto right_key = splitmix64(
            seed ^ splitmix64(right + 1U) ^
            splitmix64(static_cast<std::uint64_t>(day)) ^
            kGenesisPartnerOrderStream);
        return left_key < right_key || (left_key == right_key && left < right);
    };
    std::sort(females.begin(), females.end(), random_order);
    for (auto &bucket : male_by_age) {
        std::sort(bucket.begin(), bucket.end(), random_order);
    }

    std::array<std::uint64_t, 6> female_counts{};
    for (const auto index : females) {
        ++female_counts[union_age_band(
            static_cast<double>(people[static_cast<std::size_t>(index)].age))];
    }
    std::array<std::uint64_t, 6> targets{};
    if (rules.genesis_union_target_profile.enabled) {
        for (std::size_t band = 0; band < targets.size(); ++band) {
            targets[band] = static_cast<std::uint64_t>(std::llround(
                rules.genesis_union_target_profile.shares[band] *
                static_cast<double>(female_counts[band])));
        }
    } else {
        const auto adults = static_cast<std::uint64_t>(std::count_if(
            people.begin(), people.end(), [&rules](const GenesisPersonPlan &person) {
                return person.age >= rules.working_age;
            }));
        targets.fill(std::numeric_limits<std::uint64_t>::max());
        targets[0] = static_cast<std::uint64_t>(std::llround(
            rules.genesis_target_partnered_adult_share *
            static_cast<double>(adults) / 2.0));
    }
    std::array<std::uint64_t, 6> matched{};
    std::uint64_t flat_matched = 0U;
    for (const auto female_index : females) {
        auto &female = people[static_cast<std::size_t>(female_index)];
        const auto band = union_age_band(static_cast<double>(female.age));
        const bool reached = rules.genesis_union_target_profile.enabled
                                 ? matched[band] >= targets[band]
                                 : flat_matched >= targets[0];
        if (reached) {
            continue;
        }
        const double target_age =
            static_cast<double>(female.age) +
            rules.genesis_spouse_age_gap_stddev *
                normal_draw(seed, female_index + 1U, day,
                            kGenesisSpouseGapStream);
        const auto male_index = pop_genesis_partner(
            male_by_age, people, static_cast<double>(female.age), target_age,
            rules.genesis_spouse_maximum_age_gap);
        if (male_index == kNoGenesisPerson) {
            continue;
        }
        female.partner_index = male_index;
        people[static_cast<std::size_t>(male_index)].partner_index = female_index;
        ++matched[band];
        ++flat_matched;
    }
}

[[nodiscard]] std::uint64_t next_parent_candidate(
    const GenesisAgeBuckets &buckets, std::vector<std::size_t> &cursors,
    std::uint32_t age, const std::vector<std::uint32_t> &remaining_capacity,
    const std::vector<std::uint32_t> &household_children,
    std::uint32_t household_limit,
    const std::vector<GenesisPersonPlan> &people,
    bool require_partner,
    const std::vector<std::uint32_t> *partner_capacity = nullptr) {
    if (static_cast<std::size_t>(age) >= buckets.size()) {
        return kNoGenesisPerson;
    }
    const auto &bucket = buckets[age];
    auto &cursor = cursors[age];
    while (cursor < bucket.size()) {
        const auto candidate = bucket[cursor];
        const auto &person = people[static_cast<std::size_t>(candidate)];
        const bool partner_ok =
            !require_partner ||
            (person.partner_index != kNoGenesisPerson &&
             (partner_capacity == nullptr ||
              (*partner_capacity)[static_cast<std::size_t>(
                  person.partner_index)] > 0U));
        const bool household_ok =
            person.household_index != kNoGenesisPerson &&
            household_children[static_cast<std::size_t>(
                person.household_index)] < household_limit;
        if (remaining_capacity[static_cast<std::size_t>(candidate)] > 0U &&
            partner_ok && household_ok) {
            return candidate;
        }
        ++cursor;
    }
    return kNoGenesisPerson;
}

template <typename Candidate>
[[nodiscard]] bool for_ordered_parent_gaps(std::uint32_t minimum_gap,
                                           std::uint32_t maximum_gap,
                                           double target_gap,
                                           Candidate &&candidate) {
    const auto rounded = static_cast<std::int32_t>(std::llround(std::clamp(
        target_gap, static_cast<double>(minimum_gap),
        static_cast<double>(maximum_gap))));
    const auto span = maximum_gap - minimum_gap;
    for (std::uint32_t offset = 0U; offset <= span; ++offset) {
        const auto lower = rounded - static_cast<std::int32_t>(offset);
        if (lower >= static_cast<std::int32_t>(minimum_gap) &&
            candidate(static_cast<std::uint32_t>(lower))) {
            return true;
        }
        const auto upper = rounded + static_cast<std::int32_t>(offset);
        if (offset > 0U && upper <= static_cast<std::int32_t>(maximum_gap) &&
            candidate(static_cast<std::uint32_t>(upper))) {
            return true;
        }
    }
    return false;
}

void assign_genesis_adult_households(GenesisRelationshipPlan &plan,
                                     const M7Rules &rules,
                                     std::vector<std::uint64_t> &adults,
                                     std::vector<std::uint64_t> &minors) {
    adults.reserve(plan.people.size());
    minors.reserve(plan.people.size() / 4U);
    for (std::uint64_t index = 0; index < plan.people.size(); ++index) {
        (plan.people[static_cast<std::size_t>(index)].age >= rules.working_age
             ? adults
             : minors)
            .push_back(index);
    }
    for (const auto adult : adults) {
        auto &person = plan.people[static_cast<std::size_t>(adult)];
        if (person.household_index != kNoGenesisPerson) {
            continue;
        }
        const auto household = plan.household_count++;
        person.household_index = household;
        if (person.partner_index != kNoGenesisPerson) {
            plan.people[static_cast<std::size_t>(person.partner_index)]
                .household_index = household;
        }
    }
}

void assign_genesis_children(GenesisRelationshipPlan &plan,
                             const M7SimulationSpec &spec,
                             const std::vector<std::uint64_t> &adults,
                             std::vector<std::uint64_t> minors,
                             std::uint64_t seed) {
    std::uint32_t maximum_age = 0U;
    for (const auto &person : plan.people) {
        maximum_age = std::max(maximum_age, person.age);
    }
    GenesisAgeBuckets women(maximum_age + 1U);
    GenesisAgeBuckets men(maximum_age + 1U);
    GenesisAgeBuckets partnered_women(maximum_age + 1U);
    GenesisAgeBuckets unpartnered_women(maximum_age + 1U);
    GenesisAgeBuckets unpartnered_men(maximum_age + 1U);
    for (const auto adult : adults) {
        const auto &person = plan.people[static_cast<std::size_t>(adult)];
        auto &all = person.sex == core::PersonSex::female ? women : men;
        all[person.age].push_back(adult);
        if (person.sex == core::PersonSex::female &&
            person.partner_index != kNoGenesisPerson) {
            partnered_women[person.age].push_back(adult);
        } else if (person.partner_index == kNoGenesisPerson) {
            auto &single = person.sex == core::PersonSex::female
                               ? unpartnered_women
                               : unpartnered_men;
            single[person.age].push_back(adult);
        }
    }
    std::vector<std::size_t> women_cursor(maximum_age + 1U, 0U);
    std::vector<std::size_t> men_cursor(maximum_age + 1U, 0U);
    std::vector<std::size_t> partnered_women_cursor(maximum_age + 1U, 0U);
    std::vector<std::size_t> single_women_cursor(maximum_age + 1U, 0U);
    std::vector<std::size_t> single_men_cursor(maximum_age + 1U, 0U);
    std::vector<std::uint32_t> capacity(
        plan.people.size(), spec.rules.genesis_maximum_children_per_parent);
    std::vector<std::uint32_t> household_children(plan.household_count, 0U);
    std::vector<std::uint32_t> household_size(plan.household_count, 0U);
    for (const auto adult : adults) {
        ++household_size[static_cast<std::size_t>(
            plan.people[static_cast<std::size_t>(adult)].household_index)];
    }
    using HouseholdLoad = std::pair<std::uint32_t, std::uint64_t>;
    std::priority_queue<HouseholdLoad, std::vector<HouseholdLoad>,
                        std::greater<HouseholdLoad>>
        guardian_households;
    for (std::uint64_t household = 0; household < plan.household_count;
         ++household) {
        guardian_households.emplace(household_size[household], household);
    }
    std::sort(minors.begin(), minors.end(), [&plan](std::uint64_t left,
                                                    std::uint64_t right) {
        const auto left_age = plan.people[static_cast<std::size_t>(left)].age;
        const auto right_age = plan.people[static_cast<std::size_t>(right)].age;
        return left_age > right_age || (left_age == right_age && left < right);
    });
    for (const auto child_index : minors) {
        auto &child = plan.people[static_cast<std::size_t>(child_index)];
        const double target_gap =
            spec.rules.genesis_ideal_parent_age_gap +
            spec.rules.genesis_parent_age_gap_stddev *
                normal_draw(seed, child_index + 1U,
                            spec.population.start_calendar_day,
                            kGenesisParentGapStream);
        const bool prefer_two =
            unit_draw(seed, child_index + 1U,
                      spec.population.start_calendar_day,
                      kGenesisTwoParentStream) <
            spec.rules.genesis_two_parent_assignment_share;
        const auto assign_two = [&]() {
            return for_ordered_parent_gaps(
                spec.rules.genesis_parent_minimum_age_gap,
                spec.rules.genesis_parent_maximum_age_gap, target_gap,
                [&](std::uint32_t gap) {
                    const auto mother = next_parent_candidate(
                        partnered_women, partnered_women_cursor,
                        child.age + gap, capacity, household_children,
                        spec.rules.genesis_maximum_children_per_household,
                        plan.people, true, &capacity);
                    if (mother == kNoGenesisPerson) {
                        return false;
                    }
                    const auto father =
                        plan.people[static_cast<std::size_t>(mother)]
                            .partner_index;
                    child.mother_index = mother;
                    child.father_index = father;
                    child.guardian_index = mother;
                    child.household_index =
                        plan.people[static_cast<std::size_t>(mother)]
                            .household_index;
                    --capacity[static_cast<std::size_t>(mother)];
                    --capacity[static_cast<std::size_t>(father)];
                    ++household_children[static_cast<std::size_t>(
                        child.household_index)];
                    return true;
                });
        };
        const auto assign_single = [&](GenesisAgeBuckets &buckets,
                                       std::vector<std::size_t> &cursors,
                                       core::PersonSex sex) {
            return for_ordered_parent_gaps(
                spec.rules.genesis_parent_minimum_age_gap,
                spec.rules.genesis_parent_maximum_age_gap, target_gap,
                [&](std::uint32_t gap) {
                    const auto parent = next_parent_candidate(
                        buckets, cursors, child.age + gap, capacity,
                        household_children,
                        spec.rules.genesis_maximum_children_per_household,
                        plan.people, false);
                    if (parent == kNoGenesisPerson) {
                        return false;
                    }
                    (sex == core::PersonSex::female ? child.mother_index
                                                    : child.father_index) = parent;
                    child.guardian_index = parent;
                    child.household_index =
                        plan.people[static_cast<std::size_t>(parent)]
                            .household_index;
                    --capacity[static_cast<std::size_t>(parent)];
                    ++household_children[static_cast<std::size_t>(
                        child.household_index)];
                    return true;
                });
        };
        bool assigned = false;
        if (prefer_two) {
            assigned = assign_two() ||
                       assign_single(unpartnered_women, single_women_cursor,
                                     core::PersonSex::female) ||
                       assign_single(unpartnered_men, single_men_cursor,
                                     core::PersonSex::male);
        } else {
            assigned = assign_single(unpartnered_women, single_women_cursor,
                                     core::PersonSex::female) ||
                       assign_single(unpartnered_men, single_men_cursor,
                                     core::PersonSex::male) ||
                       assign_two();
        }
        assigned = assigned ||
                   assign_single(women, women_cursor,
                                 core::PersonSex::female) ||
                   assign_single(men, men_cursor, core::PersonSex::male);
        if (!assigned) {
            while (!guardian_households.empty()) {
                const auto [size, household] = guardian_households.top();
                if (size == household_size[household]) {
                    break;
                }
                guardian_households.pop();
            }
            const auto household = guardian_households.top().second;
            guardian_households.pop();
            child.household_index = household;
            for (const auto adult : adults) {
                if (plan.people[static_cast<std::size_t>(adult)]
                        .household_index == household) {
                    child.guardian_index = adult;
                    break;
                }
            }
            ++household_children[household];
        }
        ++household_size[static_cast<std::size_t>(child.household_index)];
        guardian_households.emplace(
            household_size[static_cast<std::size_t>(child.household_index)],
            child.household_index);
    }
}

[[nodiscard]] std::uint64_t next_lineage_parent(
    const GenesisAgeBuckets &buckets, std::vector<std::size_t> &cursors,
    std::uint32_t age, const std::vector<std::uint32_t> &remaining_capacity,
    const std::vector<GenesisPersonPlan> &people, bool require_partner,
    std::uint64_t excluded) {
    if (static_cast<std::size_t>(age) >= buckets.size()) {
        return kNoGenesisPerson;
    }
    const auto &bucket = buckets[age];
    auto &cursor = cursors[age];
    while (cursor < bucket.size()) {
        const auto candidate = bucket[cursor];
        const auto &person = people[static_cast<std::size_t>(candidate)];
        const bool family_role_ok =
            candidate != excluded && person.partner_index != excluded;
        const bool partner_ok =
            !require_partner ||
            (person.partner_index != kNoGenesisPerson &&
             remaining_capacity[static_cast<std::size_t>(
                 person.partner_index)] > 0U);
        if (remaining_capacity[static_cast<std::size_t>(candidate)] > 0U &&
            family_role_ok && partner_ok) {
            return candidate;
        }
        ++cursor;
    }
    return kNoGenesisPerson;
}

void assign_genesis_adult_lineage(GenesisRelationshipPlan &plan,
                                  const M7SimulationSpec &spec,
                                  std::vector<std::uint64_t> adults,
                                  std::uint64_t seed) {
    std::uint32_t maximum_age = 0U;
    for (const auto &person : plan.people) {
        maximum_age = std::max(maximum_age, person.age);
    }
    GenesisAgeBuckets women(maximum_age + 1U);
    GenesisAgeBuckets men(maximum_age + 1U);
    GenesisAgeBuckets partnered_women(maximum_age + 1U);
    for (const auto adult : adults) {
        const auto &person = plan.people[static_cast<std::size_t>(adult)];
        (person.sex == core::PersonSex::female ? women : men)[person.age]
            .push_back(adult);
        if (person.sex == core::PersonSex::female &&
            person.partner_index != kNoGenesisPerson) {
            partnered_women[person.age].push_back(adult);
        }
    }
    std::vector<std::size_t> women_cursor(maximum_age + 1U, 0U);
    std::vector<std::size_t> men_cursor(maximum_age + 1U, 0U);
    std::vector<std::size_t> partnered_cursor(maximum_age + 1U, 0U);
    std::vector<std::uint32_t> capacity(
        plan.people.size(), spec.rules.genesis_maximum_children_per_parent);
    for (const auto &person : plan.people) {
        if (person.mother_index != kNoGenesisPerson) {
            auto &remaining =
                capacity[static_cast<std::size_t>(person.mother_index)];
            remaining -= remaining > 0U ? 1U : 0U;
        }
        if (person.father_index != kNoGenesisPerson) {
            auto &remaining =
                capacity[static_cast<std::size_t>(person.father_index)];
            remaining -= remaining > 0U ? 1U : 0U;
        }
    }
    std::sort(adults.begin(), adults.end(), [&plan](std::uint64_t left,
                                                    std::uint64_t right) {
        const auto left_age = plan.people[static_cast<std::size_t>(left)].age;
        const auto right_age = plan.people[static_cast<std::size_t>(right)].age;
        return left_age > right_age || (left_age == right_age && left < right);
    });
    for (const auto child_index : adults) {
        auto &child = plan.people[static_cast<std::size_t>(child_index)];
        if (child.age + spec.rules.genesis_parent_minimum_age_gap > maximum_age) {
            continue;
        }
        const double target_gap =
            spec.rules.genesis_ideal_parent_age_gap +
            spec.rules.genesis_parent_age_gap_stddev *
                normal_draw(seed, child_index + 1U,
                            spec.population.start_calendar_day,
                            kGenesisParentGapStream ^ 0x9e3779b97f4a7c15ULL);
        const bool prefer_two =
            unit_draw(seed, child_index + 1U,
                      spec.population.start_calendar_day,
                      kGenesisTwoParentStream ^ 0x517cc1b727220a95ULL) <
            spec.rules.genesis_two_parent_assignment_share;
        const auto assign_two = [&]() {
            return for_ordered_parent_gaps(
                spec.rules.genesis_parent_minimum_age_gap,
                spec.rules.genesis_parent_maximum_age_gap, target_gap,
                [&](std::uint32_t gap) {
                    const auto mother = next_lineage_parent(
                        partnered_women, partnered_cursor, child.age + gap,
                        capacity, plan.people, true, child_index);
                    if (mother == kNoGenesisPerson) {
                        return false;
                    }
                    const auto father =
                        plan.people[static_cast<std::size_t>(mother)]
                            .partner_index;
                    child.mother_index = mother;
                    child.father_index = father;
                    --capacity[static_cast<std::size_t>(mother)];
                    --capacity[static_cast<std::size_t>(father)];
                    return true;
                });
        };
        const auto assign_single = [&](GenesisAgeBuckets &buckets,
                                       std::vector<std::size_t> &cursors,
                                       core::PersonSex sex) {
            return for_ordered_parent_gaps(
                spec.rules.genesis_parent_minimum_age_gap,
                spec.rules.genesis_parent_maximum_age_gap, target_gap,
                [&](std::uint32_t gap) {
                    const auto parent = next_lineage_parent(
                        buckets, cursors, child.age + gap, capacity,
                        plan.people, false, child_index);
                    if (parent == kNoGenesisPerson) {
                        return false;
                    }
                    (sex == core::PersonSex::female ? child.mother_index
                                                    : child.father_index) = parent;
                    --capacity[static_cast<std::size_t>(parent)];
                    return true;
                });
        };
        if (prefer_two && assign_two()) {
            continue;
        }
        if (assign_single(women, women_cursor, core::PersonSex::female) ||
            assign_single(men, men_cursor, core::PersonSex::male)) {
            continue;
        }
        if (!prefer_two) {
            static_cast<void>(assign_two());
        }
    }
}

[[nodiscard]] Result<GenesisRelationshipPlan> build_genesis_relationship_plan(
    const M7SimulationSpec &spec, const std::vector<double> &age_weights,
    double female_share) {
    GenesisRelationshipPlan plan;
    plan.people.reserve(spec.population.initial_persons);
    const auto seed = spec.financial_economy.monetary_economy.real_economy.seed;
    for (std::uint64_t index = 0; index < spec.population.initial_persons;
         ++index) {
        const auto identity = index + 1U;
        const auto age = sample_age(
            age_weights,
            unit_draw(seed, identity, spec.population.start_calendar_day,
                      kAgeStream));
        const auto offset = static_cast<std::int32_t>(
            unit_draw(seed, identity, spec.population.start_calendar_day,
                      kOffsetStream) *
            kDaysPerYear);
        GenesisPersonPlan person;
        person.age = age;
        person.sex = unit_draw(seed, identity,
                               spec.population.start_calendar_day, kSexStream) <
                             female_share
                         ? core::PersonSex::female
                         : core::PersonSex::male;
        person.birth_day = spec.population.start_calendar_day -
                           static_cast<std::int32_t>(age * 365U) - offset;
        plan.people.push_back(person);
    }

    if (!spec.rules.relationships) {
        plan.household_count = static_cast<std::uint64_t>(std::ceil(
            static_cast<double>(spec.population.initial_persons) /
            spec.population.target_household_size));
        for (std::size_t index = 0; index < plan.people.size(); ++index) {
            plan.people[index].household_index =
                static_cast<std::uint64_t>(index) % plan.household_count;
        }
        return plan;
    }

    if (spec.rules.marriage) {
        match_genesis_partners(plan, spec.rules, seed,
                               spec.population.start_calendar_day);
    }
    std::vector<std::uint64_t> adults;
    std::vector<std::uint64_t> minors;
    assign_genesis_adult_households(plan, spec.rules, adults, minors);
    if (!minors.empty() && adults.empty()) {
        plan.household_count = static_cast<std::uint64_t>(std::ceil(
            static_cast<double>(spec.population.initial_persons) /
            spec.population.target_household_size));
        for (std::size_t index = 0; index < plan.people.size(); ++index) {
            plan.people[index].household_index =
                static_cast<std::uint64_t>(index) % plan.household_count;
        }
        return plan;
    }
    if (plan.household_count == 0U) {
        return Status(ErrorCode::invalid_argument,
                      "M7 genesis relationship plan has no households");
    }
    assign_genesis_children(plan, spec, adults, std::move(minors), seed);
    assign_genesis_adult_lineage(plan, spec, adults, seed);
    return plan;
}

} // namespace

void M7TickScratch::reserve(const M7Runtime &runtime) {
    opening_alive_.reserve(runtime.persons.alive_count());
    guardian_heads_.reserve(static_cast<std::size_t>(runtime.persons.next_id()));
    guardian_next_.reserve(static_cast<std::size_t>(runtime.persons.next_id()));
    deceased_lots_.reserve(8);
    estate_securities_.reserve(16);
    estates_.reserve(runtime.estates.size() + 8U);
    leaving_home_.reserve(runtime.leaving_home.size() + 8U);
    pending_leaving_home_.reserve(8);
    labor_candidates_.reserve(runtime.persons.alive_count());
    second_job_candidates_.reserve(runtime.persons.alive_count());
    ladder_candidates_.reserve(runtime.persons.alive_count());
    ladder_firms_.reserve(runtime.firm_target_ema.size());
    divorce_candidates_.reserve(runtime.relationships.unions().size());
    fertility_candidates_.reserve(runtime.persons.alive_count() / 4U);
    household_wealth_quintile_.reserve(runtime.household_wealth_quintile.size());
    household_mortality_multiplier_.reserve(
        runtime.household_mortality_multiplier.size());
    household_fertility_multiplier_.reserve(
        runtime.household_fertility_multiplier.size());
    const auto household_count = runtime.membership.household_capacity();
    lifecycle_need_units_.reserve(household_count);
    lifecycle_income_capacity_.reserve(household_count);
    lifecycle_inverse_life_days_.reserve(household_count);
    lifecycle_net_wealth_.reserve(household_count);
    kin_households_.reserve(16);
    retired_households_.reserve(4);
    firm_target_ema_.reserve(runtime.firm_target_ema.size());
}

std::uint64_t M7TickScratch::capacity_signature() const noexcept {
    return static_cast<std::uint64_t>(opening_alive_.capacity()) ^
           (static_cast<std::uint64_t>(guardian_heads_.capacity()) << 2U) ^
           (static_cast<std::uint64_t>(guardian_next_.capacity()) << 6U) ^
           (static_cast<std::uint64_t>(deceased_lots_.capacity()) << 16U) ^
           (static_cast<std::uint64_t>(estates_.capacity()) << 32U) ^
           (static_cast<std::uint64_t>(labor_candidates_.capacity()) << 8U) ^
           (static_cast<std::uint64_t>(second_job_candidates_.capacity()) << 12U) ^
           (static_cast<std::uint64_t>(ladder_candidates_.capacity()) << 20U) ^
           (static_cast<std::uint64_t>(ladder_firms_.capacity()) << 60U) ^
           (static_cast<std::uint64_t>(roster_buffer_.capacity()) << 24U) ^
           (static_cast<std::uint64_t>(divorce_candidates_.capacity()) << 40U) ^
           (static_cast<std::uint64_t>(fertility_candidates_.capacity()) << 52U) ^
           (static_cast<std::uint64_t>(household_wealth_quintile_.capacity()) << 10U) ^
           (static_cast<std::uint64_t>(household_mortality_multiplier_.capacity())
            << 14U) ^
           (static_cast<std::uint64_t>(household_fertility_multiplier_.capacity())
            << 18U) ^
           (static_cast<std::uint64_t>(lifecycle_need_units_.capacity()) << 22U) ^
           (static_cast<std::uint64_t>(lifecycle_income_capacity_.capacity())
            << 26U) ^
           (static_cast<std::uint64_t>(lifecycle_inverse_life_days_.capacity())
            << 30U) ^
           (static_cast<std::uint64_t>(lifecycle_net_wealth_.capacity()) << 34U) ^
           (static_cast<std::uint64_t>(beneficial_assets_.capacity()) << 48U) ^
           (static_cast<std::uint64_t>(estate_securities_.capacity()) << 56U) ^
           (static_cast<std::uint64_t>(kin_households_.capacity()) << 4U) ^
           (static_cast<std::uint64_t>(retired_households_.capacity()) << 28U) ^
           (static_cast<std::uint64_t>(leaving_home_.capacity()) << 36U) ^
           (static_cast<std::uint64_t>(pending_leaving_home_.capacity()) << 44U);
}

Status validate_m7_policy(const M7PolicyState &policy) noexcept {
    if (!finite(policy.inheritance_tax_rate) || !finite(policy.pension_replacement) ||
        policy.inheritance_tax_rate < 0.0 || policy.inheritance_tax_rate > 1.0 ||
        policy.pension_replacement < 0.0 || policy.pension_replacement > 1.5) {
        return Status(ErrorCode::invalid_argument, "M7 policy is invalid");
    }
    return Status::success();
}

Status validate_m7_rules(const M7Rules &rules) noexcept {
    const std::array labor_values{
        rules.annual_churn,
        rules.firing_adjustment,
        rules.layoff_band,
        rules.target_smoothing,
        rules.suspension_quit_discount,
        rules.search_intensity,
        rules.ladder_search_intensity,
        rules.ladder_premium,
        rules.efficiency_sigma,
        rules.genesis_employment_rate,
        rules.young_participation_rate,
        rules.prime_participation_rate,
        rules.older_participation_rate,
        rules.reservation_markup,
        rules.welfare_quit_hazard,
        rules.family_transfer_buffer,
        rules.annual_marriage_rate,
        rules.annual_divorce_rate,
        rules.annual_leave_rate_peak,
        rules.annual_leave_rate_late,
        rules.efficiency_sigma,
        rules.mortality_rank_gradient,
        rules.fertility_rank_gradient,
        rules.stratification_multiplier_minimum,
        rules.stratification_multiplier_maximum,
        rules.lifecycle_income_propensity,
        rules.lifecycle_wealth_draw_propensity,
        rules.demographic_signal_halflife_years,
        rules.fertility_income_elasticity,
        rules.fertility_multiplier_minimum,
        rules.fertility_multiplier_maximum,
        rules.mortality_income_elasticity,
        rules.mortality_multiplier_minimum,
        rules.mortality_multiplier_maximum,
        rules.genesis_ideal_parent_age_gap,
        rules.genesis_parent_age_gap_stddev,
        rules.genesis_spouse_age_gap_stddev,
        rules.genesis_target_partnered_adult_share,
        rules.genesis_two_parent_assignment_share,
        rules.marriage_peak_age,
        rules.marriage_age_width,
        rules.marriage_age_gap_stddev,
        rules.marriage_acceptance_base,
        rules.marriage_acceptance_age_gap_penalty,
        rules.remarriage_rate_multiplier,
        rules.widowed_remarriage_multiplier,
        rules.divorce_peak_duration_years,
        rules.divorce_duration_width,
        rules.divorce_peak_multiplier,
        rules.divorce_child_multiplier,
        rules.divorce_age_gap_multiplier_per_10y,
    };
    const auto valid_union_profile = [](const M7UnionTargetProfile &profile) {
        return std::all_of(profile.shares.begin(), profile.shares.end(),
                           [](double share) {
                               return finite(share) && share >= 0.0 &&
                                      share <= 1.0;
                           });
    };
    if (rules.working_age < 1U || rules.retirement_age <= rules.working_age ||
        rules.retirement_age > rules.vital_rates.maximum_age ||
        (rules.estates && !rules.beneficial_ownership) ||
        !std::all_of(labor_values.begin(), labor_values.end(),
                     [](double value) { return finite(value); }) ||
        rules.annual_churn < 0.0 || rules.annual_churn > 1.0 ||
        rules.firing_adjustment < 0.0 || rules.firing_adjustment > 1.0 ||
        rules.layoff_band < 0.0 || rules.target_smoothing < 0.0 ||
        rules.target_smoothing > 1.0 || rules.suspension_timeout_days == 0 ||
        rules.suspension_quit_discount <= 0.0 ||
        rules.suspension_quit_discount > 1.5 ||
        rules.search_intensity < 0.0 || rules.search_intensity > 1.0 ||
        rules.ladder_search_intensity < 0.0 || rules.ladder_search_intensity > 1.0 ||
        rules.ladder_premium < 0.0 || rules.efficiency_sigma < 0.0 ||
        rules.efficiency_sigma > 2.0 ||
        rules.genesis_employment_rate < 0.0 || rules.genesis_employment_rate > 1.0 ||
        rules.young_participation_rate < 0.0 || rules.young_participation_rate > 1.0 ||
        rules.prime_participation_rate < 0.0 || rules.prime_participation_rate > 1.0 ||
        rules.older_participation_rate < 0.0 || rules.older_participation_rate > 1.0 ||
        rules.reservation_markup < 0.0 || rules.welfare_quit_hazard < 0.0 ||
        rules.welfare_quit_hazard > 1.0 || rules.family_transfer_buffer < 1.0 ||
        (rules.family_transfers && !rules.relationships) ||
        rules.marriage_interval_days == 0 || rules.annual_marriage_rate < 0.0 ||
        rules.annual_marriage_rate > 1.0 || rules.annual_divorce_rate < 0.0 ||
        rules.annual_divorce_rate > 1.0 ||
        rules.leave_home_peak_end_age < rules.leave_home_min_age ||
        rules.annual_leave_rate_peak < 0.0 || rules.annual_leave_rate_peak > 1.0 ||
        rules.annual_leave_rate_late < 0.0 || rules.annual_leave_rate_late > 1.0 ||
        rules.mortality_rank_gradient < 0.0 ||
        rules.stratification_multiplier_minimum <= 0.0 ||
        rules.stratification_multiplier_minimum > 1.0 ||
        rules.stratification_multiplier_maximum < 1.0 ||
        rules.lifecycle_income_propensity < 0.0 ||
        rules.lifecycle_wealth_draw_propensity < 0.0 ||
        rules.demographic_feedback_burnin_years == 0U ||
        rules.demographic_signal_halflife_years <= 0.0 ||
        rules.fertility_income_elasticity < 0.0 ||
        rules.fertility_multiplier_minimum <= 0.0 ||
        rules.fertility_multiplier_minimum > 1.0 ||
        rules.fertility_multiplier_maximum < 1.0 ||
        rules.mortality_income_elasticity < 0.0 ||
        rules.mortality_multiplier_minimum <= 0.0 ||
        rules.mortality_multiplier_minimum > 1.0 ||
        rules.mortality_multiplier_maximum < 1.0 ||
        !valid_union_profile(rules.genesis_union_target_profile) ||
        !valid_union_profile(rules.social_union_target_profile) ||
        rules.genesis_parent_minimum_age_gap == 0U ||
        rules.genesis_parent_maximum_age_gap <
            rules.genesis_parent_minimum_age_gap ||
        rules.genesis_ideal_parent_age_gap <
            static_cast<double>(rules.genesis_parent_minimum_age_gap) ||
        rules.genesis_ideal_parent_age_gap >
            static_cast<double>(rules.genesis_parent_maximum_age_gap) ||
        rules.genesis_parent_age_gap_stddev <= 0.0 ||
        rules.genesis_spouse_age_gap_stddev <= 0.0 ||
        rules.genesis_target_partnered_adult_share < 0.0 ||
        rules.genesis_target_partnered_adult_share > 1.0 ||
        rules.genesis_two_parent_assignment_share < 0.0 ||
        rules.genesis_two_parent_assignment_share > 1.0 ||
        rules.genesis_maximum_children_per_parent == 0U ||
        rules.genesis_maximum_children_per_household == 0U ||
        rules.marriage_age_width <= 0.0 ||
        rules.marriage_age_gap_stddev <= 0.0 ||
        rules.marriage_acceptance_base < 0.0 ||
        rules.marriage_acceptance_base > 1.0 ||
        rules.marriage_acceptance_age_gap_penalty < 0.0 ||
        rules.remarriage_rate_multiplier < 0.0 ||
        rules.widowed_remarriage_multiplier < 0.0 ||
        rules.divorce_peak_duration_years < 0.0 ||
        rules.divorce_duration_width <= 0.0 ||
        rules.divorce_peak_multiplier < 0.0 ||
        rules.divorce_child_multiplier < 0.0 ||
        rules.divorce_age_gap_multiplier_per_10y <= 0.0 ||
        rules.guardian_maximum_household_size == 0U ||
        (rules.second_jobs && !rules.fractional_hours) ||
        (rules.job_ladder && !rules.relationship_wages) ||
        rules.marriage_rules.minimum_age == 0 ||
        rules.marriage_rules.maximum_age < rules.marriage_rules.minimum_age ||
        rules.marriage_rules.maximum_age_gap >
            rules.marriage_rules.maximum_age - rules.marriage_rules.minimum_age ||
        !finite(rules.marriage_rules.preferred_age_gap) ||
        !finite(rules.marriage_rules.age_gap_penalty) ||
        !finite(rules.marriage_rules.assortativity) ||
        rules.marriage_rules.age_gap_penalty < 0.0 ||
        rules.marriage_rules.assortativity < 0.0 ||
        ((rules.marriage || rules.divorce || rules.household_lifecycle) &&
         !rules.relationships)) {
        return Status(ErrorCode::invalid_argument, "M7 rules are invalid");
    }
    return validate_vital_rates(rules.vital_rates);
}

Status validate_m7_population_spec(const M7PopulationSpec &population) noexcept {
    if (population.initial_persons == 0 || !finite(population.target_household_size) ||
        population.target_household_size < 1.0 ||
        population.target_household_size >
            static_cast<double>(population.initial_persons)) {
        return Status(ErrorCode::invalid_argument,
                      "M7 population specification is invalid");
    }
    if (population.fixed_genesis_vital_rates) {
        return validate_vital_rates(population.genesis_vital_rates);
    }
    return Status::success();
}

Status validate_m7_spec(const M7SimulationSpec &spec) noexcept {
    auto status = validate_m7_policy(spec.policy);
    if (!status.ok()) {
        return status;
    }
    status = validate_m7_rules(spec.rules);
    if (!status.ok()) {
        return status;
    }
    status = validate_m7_population_spec(spec.population);
    if (!status.ok()) {
        return status;
    }
    auto financial = spec.financial_economy;
    const auto derived_households = static_cast<std::uint64_t>(
        std::ceil(static_cast<double>(spec.population.initial_persons) /
                  spec.population.target_household_size));
    financial.monetary_economy.real_economy.households = derived_households;
    return validate_m6_spec(financial);
}

namespace {

Status validate_m7_state_impl(const core::RootState &state,
                              const M4Runtime &real_economy_runtime,
                              const M5Runtime &monetary_runtime,
                              const M6Runtime &financial_runtime,
                              const M7Runtime &runtime, Tick tick,
                              bool full_index_validation) noexcept {
    auto status = validate_m7_policy(runtime.policy);
    if (!status.ok()) {
        return status;
    }
    status = validate_m7_rules(runtime.rules);
    if (!status.ok()) {
        return status;
    }
    status = full_index_validation
                 ? validate_m6_state(state, real_economy_runtime, monetary_runtime,
                                     financial_runtime, tick)
                 : validate_m6_state_fast(state, real_economy_runtime, monetary_runtime,
                                          financial_runtime, tick);
    if (!status.ok()) {
        return status;
    }
    status = runtime.persons.validate();
    if (!status.ok()) {
        return status;
    }
    status = runtime.membership.validate(runtime.persons, state);
    if (!status.ok()) {
        return status;
    }
    if (runtime.rules.beneficial_ownership) {
        status = full_index_validation
                     ? runtime.beneficial_ownership.validate(runtime.persons,
                                                             state.accounting_tolerance)
                     : runtime.beneficial_ownership.validate_fast(
                           runtime.persons, state.accounting_tolerance);
        if (!status.ok()) {
            return status;
        }
    }
    if (runtime.rules.persistent_labor) {
        status = runtime.employment.validate(runtime.persons, state,
                                             state.accounting_tolerance);
        if (!status.ok()) {
            return status;
        }
        status = core::validate_labor_accounts(runtime.labor_accounts,
                                               state.accounting_tolerance);
        if (!status.ok()) {
            return status;
        }
    }
    if (runtime.rules.relationships) {
        status = runtime.relationships.validate(runtime.persons);
        if (!status.ok()) {
            return status;
        }
    }
    const std::array signal_values{
        runtime.demographic_signal_ewma,
        runtime.demographic_signal_baseline,
        runtime.demographic_signal_x,
        runtime.demographic_signal_fertility_multiplier,
        runtime.demographic_signal_mortality_multiplier,
        runtime.demographic_signal_last_real_wage,
        runtime.demographic_signal_wage_sum,
        runtime.demographic_signal_labor_sum,
        runtime.demographic_signal_price_sum,
    };
    if (!std::all_of(signal_values.begin(), signal_values.end(), finite) ||
        runtime.demographic_signal_ewma < 0.0 ||
        runtime.demographic_signal_baseline < 0.0 ||
        runtime.demographic_signal_x <= 0.0 ||
        runtime.demographic_signal_fertility_multiplier <= 0.0 ||
        runtime.demographic_signal_mortality_multiplier <= 0.0 ||
        runtime.demographic_signal_last_real_wage < 0.0 ||
        runtime.demographic_signal_wage_sum < 0.0 ||
        runtime.demographic_signal_labor_sum < 0.0 ||
        runtime.demographic_signal_price_sum < 0.0) {
        return Status(ErrorCode::invariant_violation,
                      "M7 demographic signal state is invalid");
    }
    for (const auto &lot : state.ownership.records()) {
        if (lot.active && lot.owner.kind() == core::OwnerKind::household &&
            state.households.get(HouseholdId(lot.owner.value())) == nullptr) {
            return Status(ErrorCode::invariant_violation,
                          "ownership lot references an absent household");
        }
    }
    const auto expected_day = static_cast<std::int64_t>(runtime.start_calendar_day) +
                              static_cast<std::int64_t>(tick.value());
    if (expected_day != runtime.current_calendar_day) {
        return Status(ErrorCode::invariant_violation,
                      "M7 calendar and tick are inconsistent");
    }
    return Status::success();
}

} // namespace

Status validate_m7_state(const core::RootState &state,
                         const M4Runtime &real_economy_runtime,
                         const M5Runtime &monetary_runtime,
                         const M6Runtime &financial_runtime, const M7Runtime &runtime,
                         Tick tick) noexcept {
    return validate_m7_state_impl(state, real_economy_runtime, monetary_runtime,
                                  financial_runtime, runtime, tick, true);
}

Result<M7Initialization> build_m7_genesis(const M7SimulationSpec &spec) {
    const auto status = validate_m7_spec(spec);
    if (!status.ok()) {
        return status;
    }
    const auto &genesis_vital_rates = spec.population.fixed_genesis_vital_rates
                                          ? spec.population.genesis_vital_rates
                                          : spec.rules.vital_rates;
    const auto age_weights = stable_age_weights(genesis_vital_rates);
    if (age_weights.empty()) {
        return Status(ErrorCode::invalid_argument,
                      "M7 stable age distribution is invalid");
    }
    const auto female_share = algorithms::female_birth_share(genesis_vital_rates);
    if (!female_share.ok()) {
        return female_share.status();
    }
    auto relationship_plan_result = build_genesis_relationship_plan(
        spec, age_weights, *female_share.get_if());
    if (!relationship_plan_result.ok()) {
        return relationship_plan_result.status();
    }
    auto relationship_plan = std::move(relationship_plan_result).take();

    auto financial_spec = spec.financial_economy;
    auto &real = financial_spec.monetary_economy.real_economy;
    real.households = relationship_plan.household_count;
    auto genesis = build_m6_genesis(financial_spec);
    if (!genesis.ok()) {
        return genesis.status();
    }
    auto financial = std::move(genesis).take();

    M7Runtime runtime;
    runtime.policy = spec.policy;
    runtime.rules = spec.rules;
    runtime.start_calendar_day = spec.population.start_calendar_day;
    runtime.current_calendar_day = spec.population.start_calendar_day;
    runtime.firm_target_ema.resize(
        static_cast<std::size_t>(financial.root.firms.allocator_state().next_id), 0.0);
    std::vector<HouseholdId> households;
    households.reserve(financial.root.households.alive_count());
    financial.root.households.for_each_alive(
        [&](HouseholdId id, const core::HouseholdComponent &) {
            households.push_back(id);
        });
    std::sort(households.begin(), households.end());
    std::vector<PersonId> person_ids;
    person_ids.reserve(relationship_plan.people.size());
    for (const auto &planned : relationship_plan.people) {
        core::PersonRecord person;
        person.sex = planned.sex;
        person.birth_day = planned.birth_day;
        const auto created = runtime.persons.create(person);
        if (!created.ok()) {
            return created.status();
        }
        const auto person_id = *created.get_if();
        person_ids.push_back(person_id);
        auto *stored = runtime.persons.get(person_id);
        stored->efficiency = person_efficiency_draw(spec.rules, financial.root.seed,
                                                    person_id, stored->birth_day);
        const bool working_age =
            planned.age >= spec.rules.working_age &&
            planned.age < spec.rules.retirement_age;
        stored->participating = working_age && structurally_participates(
                                                   spec.rules, financial.root.seed,
                                                   person_id,
                                                   static_cast<double>(planned.age));
        stored->searching = stored->participating;
    }
    for (std::size_t index = 0; index < person_ids.size(); ++index) {
        const auto person_id = person_ids[index];
        const auto household_index = relationship_plan.people[index].household_index;
        if (household_index >= households.size()) {
            return Status(ErrorCode::invariant_violation,
                          "M7 genesis household plan is out of range");
        }
        const auto household = households[static_cast<std::size_t>(household_index)];
        runtime.persons.get(person_id)->household = household;
        const auto membership = runtime.membership.add(person_id, household);
        if (!membership.ok()) {
            return membership;
        }
    }
    for (const auto household_id : households) {
        double opening_income = 0.0;
        for (const auto person_id : runtime.membership.members(household_id)) {
            const auto *person = runtime.persons.get(person_id);
            const double age =
                completed_age(*person, spec.population.start_calendar_day);
            if (person->participating) {
                opening_income += real.rules.initial_wage;
            } else if (age >= static_cast<double>(spec.rules.retirement_age) &&
                       government_enabled(financial.real_economy_runtime) &&
                       spec.policy.pension_replacement > 0.0) {
                opening_income +=
                    spec.policy.pension_replacement * real.rules.initial_wage;
            }
        }
        auto *household = financial.root.households.get(household_id);
        if (household == nullptr) {
            return Status(ErrorCode::invariant_violation,
                          "M7 genesis household projection is absent");
        }
        household->income_expected = opening_income;
        household->income_realized = opening_income;
    }

    if (runtime.rules.relationships) {
        if (runtime.rules.marriage) {
            for (std::size_t index = 0; index < relationship_plan.people.size();
                 ++index) {
                const auto partner_index =
                    relationship_plan.people[index].partner_index;
                if (partner_index == kNoGenesisPerson || index >= partner_index) {
                    continue;
                }
                const auto younger_age = std::min(
                    relationship_plan.people[index].age,
                    relationship_plan.people[static_cast<std::size_t>(partner_index)]
                        .age);
                const auto maximum_years = younger_age > runtime.rules.working_age
                                               ? std::min<std::uint32_t>(
                                                     15U, younger_age -
                                                              runtime.rules.working_age)
                                               : 0U;
                const auto years = maximum_years == 0U
                                       ? 0U
                                       : 1U + static_cast<std::uint32_t>(
                                                  unit_draw(
                                                      financial.root.seed,
                                                      index + 1U,
                                                      spec.population
                                                          .start_calendar_day,
                                                      kMarriageStream) *
                                                  static_cast<double>(
                                                      maximum_years));
                const auto union_day =
                    spec.population.start_calendar_day -
                    static_cast<std::int32_t>(years * 365U);
                const auto union_status = runtime.relationships.marry(
                    runtime.persons, EventId(runtime.next_event_id++),
                    person_ids[index],
                    person_ids[static_cast<std::size_t>(partner_index)], union_day);
                if (!union_status.ok()) {
                    return union_status;
                }
            }
        }
        for (std::size_t index = 0; index < relationship_plan.people.size();
             ++index) {
            const auto &planned = relationship_plan.people[index];
            auto *child = runtime.persons.get(person_ids[index]);
            child->mother = planned.mother_index == kNoGenesisPerson
                                ? PersonId{}
                                : person_ids[static_cast<std::size_t>(
                                      planned.mother_index)];
            child->father = planned.father_index == kNoGenesisPerson
                                ? PersonId{}
                                : person_ids[static_cast<std::size_t>(
                                      planned.father_index)];
            child->guardian =
                planned.age >= runtime.rules.working_age ||
                        planned.guardian_index == kNoGenesisPerson
                    ? PersonId{}
                    : person_ids[static_cast<std::size_t>(
                          planned.guardian_index)];
            if (child->mother.valid() || child->father.valid()) {
                const auto lineage = runtime.relationships.register_birth(
                    runtime.persons, person_ids[index]);
                if (!lineage.ok()) {
                    return lineage;
                }
            }
        }
    }

    if (runtime.rules.beneficial_ownership) {
        for (const auto household : households) {
            const auto members = runtime.membership.members(household);
            if (members.empty()) {
                return Status(ErrorCode::invariant_violation,
                              "M7 genesis created an empty household");
            }
            const double share = 1.0 / static_cast<double>(members.size());
            const core::BeneficialAssetKey cash{
                core::BeneficialAssetKind::household_cash,
                household,
                household.value(),
            };
            for (const auto person : members) {
                const auto lot =
                    runtime.beneficial_ownership.create_lot(cash, person, share);
                if (!lot.ok()) {
                    return lot.status();
                }
            }
        }
        std::vector<HouseholdId> security_households;
        security_households.reserve(financial.root.households.alive_count());
        for (const auto &lot : financial.runtime.securities.lots()) {
            if (!lot.active() || lot.holder.kind() != core::OwnerKind::household) {
                continue;
            }
            security_households.push_back(HouseholdId(lot.holder.value()));
        }
        std::sort(security_households.begin(), security_households.end());
        security_households.erase(
            std::unique(security_households.begin(), security_households.end()),
            security_households.end());
        for (const auto household : security_households) {
            const auto claim_status = create_equal_claims(
                {
                    core::BeneficialAssetKind::security_position,
                    household,
                    0U,
                },
                runtime.membership, runtime.persons, runtime.beneficial_ownership);
            if (!claim_status.ok()) {
                return claim_status;
            }
        }
        for (const auto &loan : financial.root.loans.records()) {
            if (!loan.active || loan.borrower.kind() != core::OwnerKind::household) {
                continue;
            }
            const auto claim_status = create_equal_claims(
                {
                    core::BeneficialAssetKind::household_debt,
                    HouseholdId(loan.borrower.value()),
                    loan.id.value(),
                },
                runtime.membership, runtime.persons, runtime.beneficial_ownership);
            if (!claim_status.ok()) {
                return claim_status;
            }
        }
    }
    measure_population(financial.root, runtime.rules, runtime.persons,
                       runtime.membership, runtime.relationships,
                       runtime.current_calendar_day, runtime.last_metrics);
    runtime.last_metrics.beneficial_projection_error =
        beneficial_projection_error(runtime.beneficial_ownership);
    const auto state_status = validate_m7_state(
        financial.root, financial.real_economy_runtime, financial.monetary_runtime,
        financial.runtime, runtime, Tick(0));
    if (!state_status.ok()) {
        return state_status;
    }
    return M7Initialization{
        std::move(financial.root),
        std::move(financial.real_economy_runtime),
        std::move(financial.monetary_runtime),
        std::move(financial.runtime),
        std::move(runtime),
    };
}

namespace {

Result<M7AdvanceResult>
advance_m7_ticks_impl(core::RootState &state, M4Runtime &real_economy_runtime,
                      M4TickScratch &real_economy_scratch, M5Runtime &monetary_runtime,
                      M5TickScratch &monetary_scratch, M6Runtime &financial_runtime,
                      M6TickScratch &financial_scratch, M7Runtime &runtime,
                      M7TickScratch &scratch, Tick &tick, std::uint64_t count,
                      M7TickExtension *nested_extension,
                      const M7AdvanceOptions &options) {
    if (options.base.base.base.validate_preconditions) {
        const auto status =
            validate_m7_state_impl(state, real_economy_runtime, monetary_runtime,
                                   financial_runtime, runtime, tick, false);
        if (!status.ok()) {
            return Status(ErrorCode::invariant_violation,
                          "M7 cannot advance an invalid state");
        }
    }
    M7Extension extension(runtime, scratch, options, nested_extension);
    auto result = advance_m6_ticks_extended(
        state, real_economy_runtime, real_economy_scratch, monetary_runtime,
        monetary_scratch, financial_runtime, financial_scratch, tick, count, extension,
        options.base);
    if (!result.ok()) {
        return result.status();
    }
    const auto &base = *result.get_if();
    return M7AdvanceResult{
        base.first_tick,
        base.next_tick,
        base.advanced_ticks,
        runtime.last_metrics,
        scratch.capacity_signature(),
        base.transfer_count,
        base.trade_count,
    };
}

} // namespace

Result<M7AdvanceResult>
advance_m7_ticks(core::RootState &state, M4Runtime &real_economy_runtime,
                 M4TickScratch &real_economy_scratch, M5Runtime &monetary_runtime,
                 M5TickScratch &monetary_scratch, M6Runtime &financial_runtime,
                 M6TickScratch &financial_scratch, M7Runtime &runtime,
                 M7TickScratch &scratch, Tick &tick, std::uint64_t count,
                 const M7AdvanceOptions &options) {
    return advance_m7_ticks_impl(state, real_economy_runtime, real_economy_scratch,
                                 monetary_runtime, monetary_scratch, financial_runtime,
                                 financial_scratch, runtime, scratch, tick, count,
                                 nullptr, options);
}

Result<M7AdvanceResult>
advance_m7_ticks_extended(core::RootState &state, M4Runtime &real_economy_runtime,
                          M4TickScratch &real_economy_scratch,
                          M5Runtime &monetary_runtime, M5TickScratch &monetary_scratch,
                          M6Runtime &financial_runtime,
                          M6TickScratch &financial_scratch, M7Runtime &runtime,
                          M7TickScratch &scratch, Tick &tick, std::uint64_t count,
                          M7TickExtension &extension, const M7AdvanceOptions &options) {
    return advance_m7_ticks_impl(state, real_economy_runtime, real_economy_scratch,
                                 monetary_runtime, monetary_scratch, financial_runtime,
                                 financial_scratch, runtime, scratch, tick, count,
                                 &extension, options);
}

} // namespace macro_sim::simulation
