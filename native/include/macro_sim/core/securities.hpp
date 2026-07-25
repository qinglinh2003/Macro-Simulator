#ifndef MACRO_SIM_CORE_SECURITIES_HPP
#define MACRO_SIM_CORE_SECURITIES_HPP

#include <cstddef>
#include <cstdint>
#include <span>
#include <utility>
#include <vector>

#include "macro_sim/core/state_types.hpp"
#include "macro_sim/error.hpp"
#include "macro_sim/ids.hpp"
#include "macro_sim/units.hpp"

namespace macro_sim::core {

enum class SecurityKind : std::uint8_t {
    bond = 0,
    equity = 1,
};

enum class EquityIssuerKind : std::uint8_t {
    firm = 0,
    bank = 1,
};

struct SecurityId final {
    SecurityKind kind{SecurityKind::bond};
    std::uint32_t value{0};

    [[nodiscard]] static constexpr SecurityId bond(BondId id) noexcept {
        return {SecurityKind::bond, id.value()};
    }

    [[nodiscard]] static constexpr SecurityId equity(EquityId id) noexcept {
        return {SecurityKind::equity, id.value()};
    }

    [[nodiscard]] constexpr bool valid() const noexcept { return value != 0; }

    constexpr auto operator<=>(const SecurityId &) const noexcept = default;
};

struct BondContract final {
    BondId id{};
    OwnerId issuer{};
    AccountId issuer_account{};
    CurrencyId currency{};
    Tick issued_tick{};
    Tick maturity_tick{};
    Rate coupon_rate{};
    Money original_face{};
    Money outstanding_face{};
    bool active{true};
    bool settled{false};

    bool operator==(const BondContract &) const = default;
};

struct EquityContract final {
    EquityId id{};
    EquityIssuerKind issuer_kind{EquityIssuerKind::firm};
    OwnerId issuer{};
    AccountId issuer_account{};
    CurrencyId currency{};
    double outstanding_shares{0.0};
    Price price{};
    Price last_price{};
    Price peak_price{};
    Price fundamental{};
    double trend{0.0};
    double income_signal{0.0};
    bool active{true};
    bool resolved{false};

    bool operator==(const EquityContract &) const = default;
};

struct SecurityLot final {
    SecurityLotId id{};
    SecurityId security{};
    OwnerId holder{};
    double units{0.0};
    Money cost_basis{};
    bool active{true};

    bool operator==(const SecurityLot &) const = default;
};

struct HouseholdSecurityPositionChange final {
    SecurityId security{};
    OwnerId holder{};

    constexpr auto
    operator<=>(const HouseholdSecurityPositionChange &) const noexcept = default;
};

struct InitialSecurityHolding final {
    OwnerId holder{};
    double units{0.0};
    Money cost_basis{};
};

struct HolderSecurityIndexEntry final {
    OwnerId holder{};
    std::uint32_t offset{0};
    std::uint32_t count{0};

    bool operator==(const HolderSecurityIndexEntry &) const = default;
};

struct ContractLotIndexEntry final {
    SecurityId security{};
    std::uint32_t offset{0};
    std::uint32_t count{0};

    bool operator==(const ContractLotIndexEntry &) const = default;
};

struct IssuerSecurityIndexEntry final {
    OwnerId issuer{};
    std::uint32_t offset{0};
    std::uint32_t count{0};

    bool operator==(const IssuerSecurityIndexEntry &) const = default;
};

struct MaturityIndexEntry final {
    Tick maturity{};
    std::uint32_t offset{0};
    std::uint32_t count{0};

    bool operator==(const MaturityIndexEntry &) const = default;
};

class SecurityBook final {
  public:
    [[nodiscard]] Result<BondId> issue_bond(BondContract contract, OwnerId holder,
                                            Money cost_basis);
    [[nodiscard]] Result<EquityId>
    create_equity(EquityContract contract,
                  std::span<const InitialSecurityHolding> holdings);
    [[nodiscard]] Status transfer_units(SecurityId security, OwnerId source,
                                        OwnerId destination, double units,
                                        Money destination_cost_basis);
    [[nodiscard]] Status issue_equity_units(EquityId equity, OwnerId destination,
                                            double units, Money cost_basis);
    [[nodiscard]] Status issue_bond_units(BondId bond, OwnerId destination,
                                          double units, Money cost_basis);
    [[nodiscard]] Status retire_units(SecurityId security, OwnerId holder,
                                      double units);
    [[nodiscard]] Status settle_bond(BondId bond);
    [[nodiscard]] Status resolve_equity(EquityId equity);
    [[nodiscard]] Status update_equity_valuation(EquityId equity, Price price,
                                                 Price last_price, Price peak_price,
                                                 Price fundamental, double trend,
                                                 double income_signal);
    [[nodiscard]] Status consolidate();
    [[nodiscard]] Status compact_inactive_lots();
    [[nodiscard]] Status begin_batch() noexcept;
    [[nodiscard]] Status finish_batch();

    [[nodiscard]] BondContract *get(BondId id) noexcept;
    [[nodiscard]] const BondContract *get(BondId id) const noexcept;
    [[nodiscard]] EquityContract *get(EquityId id) noexcept;
    [[nodiscard]] const EquityContract *get(EquityId id) const noexcept;
    [[nodiscard]] SecurityLot *get(SecurityLotId id) noexcept;
    [[nodiscard]] const SecurityLot *get(SecurityLotId id) const noexcept;

    [[nodiscard]] const std::vector<BondContract> &bonds() const noexcept;
    [[nodiscard]] const std::vector<EquityContract> &equities() const noexcept;
    [[nodiscard]] const std::vector<SecurityLot> &lots() const noexcept;
    [[nodiscard]] std::span<const HouseholdSecurityPositionChange>
    household_position_changes() const noexcept;
    void clear_household_position_changes() noexcept;
    [[nodiscard]] std::span<const SecurityLotId>
    lots_for_holder(OwnerId holder) const noexcept;
    [[nodiscard]] std::span<const SecurityLotId>
    lots_for_security(SecurityId security) const noexcept;
    [[nodiscard]] std::span<const SecurityId>
    securities_for_issuer(OwnerId issuer) const noexcept;
    [[nodiscard]] std::span<const BondId>
    bonds_maturing_at(Tick maturity) const noexcept;
    [[nodiscard]] std::span<const SecurityLotId> bank_lots(BankId bank) const noexcept;

    [[nodiscard]] double units_held(SecurityId security, OwnerId holder) const noexcept;
    [[nodiscard]] double total_units(SecurityId security) const noexcept;
    [[nodiscard]] Money total_bond_face() const noexcept;
    [[nodiscard]] std::uint64_t version() const noexcept;
    [[nodiscard]] Status validate_records(double tolerance) const;
    [[nodiscard]] Status validate(double tolerance) const;
    [[nodiscard]] Status validate_indexes() const;

    void replace_records(std::vector<BondContract> bonds,
                         std::vector<EquityContract> equities,
                         std::vector<SecurityLot> lots, std::uint64_t version);

  private:
    struct PairLotSlot final {
        std::uint32_t head{0};
        std::uint32_t tail{0};

        bool operator==(const PairLotSlot &) const = default;
    };

    [[nodiscard]] Result<SecurityLotId> create_lot(SecurityId security, OwnerId holder,
                                                   double units, Money cost_basis);
    [[nodiscard]] SecurityLot *find_active_lot(SecurityId security,
                                               OwnerId holder) noexcept;
    [[nodiscard]] const SecurityLot *find_active_lot(SecurityId security,
                                                     OwnerId holder) const noexcept;
    [[nodiscard]] std::size_t
    find_pair_slot(SecurityId security, OwnerId holder) const noexcept;
    [[nodiscard]] static std::size_t pair_hash(SecurityId security,
                                               OwnerId holder) noexcept;
    void append_pair_lot(SecurityLotId lot);
    void record_household_position_change(SecurityId security, OwnerId holder);
    void rebuild_pair_index();
    [[nodiscard]] Status validate_security(SecurityId security) const noexcept;
    [[nodiscard]] Status mutation_complete(bool indexes_dirty = true);
    [[nodiscard]] Status rebuild_indexes();
    [[nodiscard]] Status rebuild_active_indexes();
    void bump_version() noexcept;

    std::vector<BondContract> bonds_;
    std::vector<EquityContract> equities_;
    std::vector<SecurityLot> lots_;
    std::uint64_t version_{0};

    std::vector<HolderSecurityIndexEntry> holder_index_;
    std::vector<SecurityLotId> holder_lots_;
    std::vector<ContractLotIndexEntry> contract_index_;
    std::vector<SecurityLotId> contract_lots_;
    std::vector<IssuerSecurityIndexEntry> issuer_index_;
    std::vector<SecurityId> issuer_securities_;
    std::vector<MaturityIndexEntry> maturity_index_;
    std::vector<BondId> maturity_bonds_;
    std::vector<HolderSecurityIndexEntry> bank_index_;
    std::vector<SecurityLotId> bank_lots_;
    std::vector<std::uint32_t> pair_next_;
    std::vector<PairLotSlot> pair_slots_;
    std::size_t pair_count_{0};
    std::vector<HouseholdSecurityPositionChange> household_position_changes_;
    std::vector<std::pair<OwnerId, SecurityLotId>> holder_rows_scratch_;
    std::vector<std::pair<SecurityId, SecurityLotId>> contract_rows_scratch_;
    std::vector<std::pair<OwnerId, SecurityId>> issuer_rows_scratch_;
    std::vector<std::pair<Tick, BondId>> maturity_rows_scratch_;
    std::vector<std::uint32_t> holder_counts_scratch_;
    std::vector<std::uint32_t> holder_offsets_scratch_;
    std::vector<std::uint32_t> contract_counts_scratch_;
    std::vector<std::uint32_t> contract_offsets_scratch_;
    bool batch_active_{false};
    bool batch_dirty_{false};
    bool batch_indexes_dirty_{false};
};

} // namespace macro_sim::core

#endif
