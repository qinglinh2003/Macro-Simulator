#ifndef MACRO_SIM_REPORTING_PROBES_HPP
#define MACRO_SIM_REPORTING_PROBES_HPP

#include <cstddef>
#include <cstdint>
#include <optional>
#include <vector>

#include "macro_sim/error.hpp"
#include "macro_sim/simulation/m9.hpp"

namespace macro_sim::reporting {

inline constexpr std::size_t kMaximumProbePageRows = 1024U;

struct ProbePageInfo final {
    Tick boundary{};
    EconomyId economy{};
    std::uint64_t next_after_id{0};
    std::uint64_t total_rows{0};
    bool has_more{false};
};

struct HouseholdProbeRow final {
    HouseholdId id{};
    AccountId account{};
    double cash{0.0};
    double debt{0.0};
    double income_expected{0.0};
    double income_realized{0.0};
    double consumption_budget{0.0};
    double spent{0.0};
    double labor_sold{0.0};
    std::vector<PersonId> members;
};

struct HouseholdProbePage final {
    ProbePageInfo page{};
    std::vector<HouseholdProbeRow> rows;
};

struct FirmProbeRow final {
    FirmId id{};
    core::FirmSector sector{core::FirmSector::consumption};
    AccountId account{};
    double cash{0.0};
    double debt{0.0};
    double goods_inventory{0.0};
    double physical_capital{0.0};
    double productivity{0.0};
    double total_factor_productivity{0.0};
    double posted_price{0.0};
    double posted_wage{0.0};
    double markup{0.0};
    double demand_expected{0.0};
    double previous_sales{0.0};
    double previous_hires{0.0};
    double book_equity{0.0};
    double earnings{0.0};
    double interest_arrears{0.0};
    double eligible_collateral_value{0.0};
    double borrowing_base_headroom{0.0};
    double residual_income_ema{0.0};
    double tobin_q_ema{0.0};
    std::uint32_t insolvent_days{0};
    std::uint32_t shell_days{0};
    std::uint32_t sector_switch_pressure_days{0};
    bool defaulted{false};
    EquityId equity{};
    double outstanding_shares{0.0};
    double share_price{0.0};
    double last_share_price{0.0};
    double peak_share_price{0.0};
    double fundamental_per_share{0.0};
    double share_trend{0.0};
    bool active{true};
    std::vector<PersonId> employees;
};

struct FirmProbePage final {
    ProbePageInfo page{};
    std::vector<FirmProbeRow> rows;
};

struct BankProbeRow final {
    BankId id{};
    AccountId cash_account{};
    SettlementNodeId reserve_node{};
    double cash{0.0};
    double reserves{0.0};
    double loan_principal{0.0};
    double opening_capital{0.0};
    double closing_capital{0.0};
    double deposit_interest_arrears{0.0};
    double leverage_appetite{0.0};
    double loan_spread{0.0};
    double deposit_spread{0.0};
    EquityId equity{};
    double outstanding_shares{0.0};
    double share_price{0.0};
    double last_share_price{0.0};
    double peak_share_price{0.0};
    double fundamental_per_share{0.0};
    double share_trend{0.0};
    bool alive{true};
    bool resolved{false};
};

struct BankProbePage final {
    ProbePageInfo page{};
    std::vector<BankProbeRow> rows;
};

struct PersonProbeRow final {
    PersonId id{};
    core::PersonSex sex{core::PersonSex::female};
    std::int32_t birth_day{0};
    std::int32_t death_day{-1};
    std::int32_t age_days{0};
    PersonId mother{};
    PersonId father{};
    PersonId partner{};
    PersonId guardian{};
    HouseholdId household{};
    JobId primary_job{};
    JobId secondary_job{};
    double efficiency{0.0};
    double cash{0.0};
    double debt{0.0};
    double firm_equity{0.0};
    double bank_equity{0.0};
    double bonds{0.0};
    double gross_assets{0.0};
    double net_worth{0.0};
    double allocated_income{0.0};
    double allocated_consumption{0.0};
    bool participating{false};
    bool searching{false};
    bool alive{false};
};

struct PersonProbePage final {
    ProbePageInfo page{};
    std::vector<PersonProbeRow> rows;
};

struct JobProbeRow final {
    JobId id{};
    PersonId person{};
    FirmId firm{};
    std::int32_t hire_day{0};
    std::int32_t separation_day{-1};
    double wage{0.0};
    double hours{0.0};
    bool secondary{false};
    bool suspended{false};
    bool active{false};
};

struct JobProbePage final {
    ProbePageInfo page{};
    std::vector<JobProbeRow> rows;
};

struct DwellingProbeRow final {
    DwellingId id{};
    core::OwnerKind owner_kind{core::OwnerKind::institution};
    std::uint32_t owner_id{0};
    HouseholdId occupant_household{};
    LoanId collateral_loan{};
    double floor_area{0.0};
    double quality{0.0};
    double location{0.0};
    std::int32_t age_days{0};
    bool active{false};
};

struct DwellingProbePage final {
    ProbePageInfo page{};
    std::vector<DwellingProbeRow> rows;
};

struct EquityProbeRow final {
    EquityId id{};
    core::EquityIssuerKind issuer_kind{core::EquityIssuerKind::firm};
    core::OwnerId issuer{};
    AccountId issuer_account{};
    CurrencyId currency{};
    double outstanding_shares{0.0};
    double price{0.0};
    double last_price{0.0};
    double peak_price{0.0};
    double fundamental{0.0};
    double trend{0.0};
    double income_signal{0.0};
    bool active{false};
    bool resolved{false};
};

struct EquityProbePage final {
    ProbePageInfo page{};
    std::vector<EquityProbeRow> rows;
};

struct SecurityPositionProbeRow final {
    SecurityLotId id{};
    core::SecurityKind security_kind{core::SecurityKind::bond};
    std::uint32_t security_id{0};
    core::OwnerKind holder_kind{core::OwnerKind::institution};
    std::uint32_t holder_id{0};
    double units{0.0};
    double cost_basis{0.0};
    double market_value{0.0};
};

struct SecurityPositionProbePage final {
    ProbePageInfo page{};
    std::vector<SecurityPositionProbeRow> rows;
};

struct EconomyDiagnosticProbe final {
    Tick boundary{};
    EconomyId economy{};
    std::uint64_t digest{0};
    std::uint64_t households{0};
    std::uint64_t firms{0};
    std::uint64_t banks{0};
    std::uint64_t persons_alive{0};
    std::uint64_t jobs_active{0};
    std::uint64_t dwellings_active{0};
    double account_balance_total{0.0};
    double loan_principal_total{0.0};
    double reserve_total{0.0};
    double goods_inventory_total{0.0};
    double physical_capital_total{0.0};
    double energy_stock_total{0.0};
    double dealer_valuation{0.0};
    std::uint64_t peg_count{0};
    bool pegs_intact{true};
};

enum class ShockBulletinStatus : std::uint8_t {
    upcoming = 0,
    active = 1,
    realizing = 2,
};

struct ShockBulletinProbeRow final {
    std::uint64_t shock_id{0};
    simulation::ShockKind kind{simulation::ShockKind::productivity};
    std::optional<EconomyId> economy{};
    Tick announcement{};
    Tick start{};
    Tick expected_end{};
    std::uint64_t duration{0};
    double magnitude{0.0};
    double intensity{0.0};
    ShockBulletinStatus status{ShockBulletinStatus::upcoming};
    std::optional<simulation::ShockSector> sector{};
};

[[nodiscard]] Result<HouseholdProbePage>
probe_households(const simulation::M9World &world, EconomyId economy,
                 std::uint64_t after_id, std::size_t maximum_rows);
[[nodiscard]] Result<FirmProbePage>
probe_firms(const simulation::M9World &world, EconomyId economy,
            std::uint64_t after_id, std::size_t maximum_rows);
[[nodiscard]] Result<BankProbePage>
probe_banks(const simulation::M9World &world, EconomyId economy,
            std::uint64_t after_id, std::size_t maximum_rows);
[[nodiscard]] Result<PersonProbePage>
probe_persons(const simulation::M9World &world, EconomyId economy,
              std::uint64_t after_id, std::size_t maximum_rows);
[[nodiscard]] Result<JobProbePage>
probe_jobs(const simulation::M9World &world, EconomyId economy,
           std::uint64_t after_id, std::size_t maximum_rows);
[[nodiscard]] Result<DwellingProbePage>
probe_dwellings(const simulation::M9World &world, EconomyId economy,
                std::uint64_t after_id, std::size_t maximum_rows);
[[nodiscard]] Result<EquityProbePage>
probe_equities(const simulation::M9World &world, EconomyId economy,
               std::uint64_t after_id, std::size_t maximum_rows);
[[nodiscard]] Result<SecurityPositionProbePage>
probe_security_positions(const simulation::M9World &world,
                         EconomyId economy, std::uint64_t after_id,
                         std::size_t maximum_rows);
[[nodiscard]] Result<EconomyDiagnosticProbe>
probe_economy_diagnostics(const simulation::M9World &world,
                          EconomyId economy);
[[nodiscard]] Result<std::vector<ShockBulletinProbeRow>>
probe_shock_bulletins(const simulation::M9World &world, EconomyId economy,
                      Tick as_of_boundary);

} // namespace macro_sim::reporting

#endif
