#ifndef MACRO_SIM_CORE_SECURITIES_HPP
#define MACRO_SIM_CORE_SECURITIES_HPP

#include <array>
#include <compare>
#include <cstddef>
#include <cstdint>
#include <iterator>
#include <span>
#include <type_traits>
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
    static constexpr std::uint32_t kMaximumPackedValue = (1U << 31U) - 1U;
    static constexpr std::uint32_t kKindShift = 31U;
    static constexpr std::uint32_t kKindMask = 1U << kKindShift;
    std::uint32_t packed{0};

    constexpr SecurityId() noexcept = default;

    template <typename Source>
        requires std::is_integral_v<Source>
    constexpr SecurityId(SecurityKind security_kind, Source security_value) noexcept
        : packed(
              (static_cast<std::uint32_t>(security_kind) << kKindShift) |
              (std::in_range<std::uint32_t>(security_value) &&
                       static_cast<std::uint32_t>(security_value) <=
                           kMaximumPackedValue
                   ? static_cast<std::uint32_t>(security_value)
                   : 0U)
          ) {}

    [[nodiscard]] static constexpr SecurityId bond(BondId id) noexcept {
        return {SecurityKind::bond, id.value()};
    }

    [[nodiscard]] static constexpr SecurityId equity(EquityId id) noexcept {
        return {SecurityKind::equity, id.value()};
    }

    [[nodiscard]] static constexpr std::uint32_t max_packed_value() noexcept {
        return kMaximumPackedValue;
    }

    [[nodiscard]] constexpr SecurityKind kind() const noexcept {
        return static_cast<SecurityKind>((packed & kKindMask) >> kKindShift);
    }

    [[nodiscard]] constexpr std::uint32_t value() const noexcept {
        return packed & kMaximumPackedValue;
    }

    [[nodiscard]] constexpr bool valid() const noexcept {
        return kind() <= SecurityKind::equity && value() != 0;
    }

    constexpr bool operator==(const SecurityId &) const noexcept = default;

    [[nodiscard]] constexpr std::strong_ordering
    operator<=>(const SecurityId &other) const noexcept {
        if (const auto kind_order = kind() <=> other.kind(); kind_order != 0) {
            return kind_order;
        }
        return value() <=> other.value();
    }
};

static_assert(sizeof(SecurityId) == sizeof(std::uint32_t));

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
    double units{0.0};
    Money cost_basis{};
    SecurityId security{};
    OwnerId holder{};

    SecurityLot() = default;
    SecurityLot(SecurityLotId lot_id, SecurityId security_id, OwnerId owner,
                double held_units, Money basis, bool is_active = true) noexcept
        : units(is_active ? held_units : 0.0),
          cost_basis(is_active ? basis : Money(0.0)),
          security(security_id), holder(owner) {
        static_cast<void>(lot_id);
    }

    [[nodiscard]] bool active() const noexcept { return units > 0.0; }

    bool operator==(const SecurityLot &) const = default;
};

static_assert(sizeof(SecurityLot) == 24U);

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

struct SecurityBookMemoryUsage final {
    std::uint64_t contracts{0};
    std::uint64_t lots{0};
    std::uint64_t query_indexes{0};
    std::uint64_t pair_index{0};
    std::uint64_t scratch{0};

    [[nodiscard]] constexpr std::uint64_t total() const noexcept {
        return contracts + lots + query_indexes + pair_index + scratch;
    }
};

class SecurityBook final {
  public:
    class LotRange final {
      public:
        class Iterator final {
          public:
            using iterator_category = std::forward_iterator_tag;
            using value_type = SecurityLotId;
            using difference_type = std::ptrdiff_t;
            using reference = SecurityLotId;
            using pointer = void;

            Iterator() noexcept = default;
            [[nodiscard]] SecurityLotId operator*() const noexcept;
            Iterator &operator++() noexcept;
            Iterator operator++(int) noexcept;
            bool operator==(const Iterator &) const noexcept = default;

          private:
            friend class LotRange;
            Iterator(const std::vector<SecurityLot> *lots,
                     const std::vector<std::uint32_t> *next,
                     std::uint32_t current) noexcept;
            void advance_to_active() noexcept;

            const std::vector<SecurityLot> *lots_{nullptr};
            const std::vector<std::uint32_t> *next_{nullptr};
            std::uint32_t current_{0U};
        };

        LotRange() noexcept = default;
        [[nodiscard]] Iterator begin() const noexcept;
        [[nodiscard]] Iterator end() const noexcept;
        [[nodiscard]] std::size_t size() const noexcept;
        [[nodiscard]] bool empty() const noexcept;

      private:
        friend class SecurityBook;
        LotRange(const std::vector<SecurityLot> *lots,
                 const std::vector<std::uint32_t> *next,
                 std::uint32_t head) noexcept;

        const std::vector<SecurityLot> *lots_{nullptr};
        const std::vector<std::uint32_t> *next_{nullptr};
        std::uint32_t head_{0U};
    };

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
    [[nodiscard]] bool inactive_lot_compaction_due() const noexcept;
    [[nodiscard]] std::size_t active_lot_count() const noexcept;
    [[nodiscard]] std::size_t inactive_lot_count() const noexcept;
    [[nodiscard]] Status reserve_position_capacity(std::size_t expected_lots,
                                                   std::size_t expected_active_pairs);
    [[nodiscard]] Status reserve_additional_lots(std::size_t additional);
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
    [[nodiscard]] LotRange lots_for_holder(OwnerId holder) const noexcept;
    [[nodiscard]] LotRange
    lots_for_security(SecurityId security) const noexcept;
    [[nodiscard]] std::span<const SecurityId>
    securities_for_issuer(OwnerId issuer) const noexcept;
    [[nodiscard]] std::span<const BondId>
    bonds_maturing_at(Tick maturity) const noexcept;
    [[nodiscard]] LotRange bank_lots(BankId bank) const noexcept;

    [[nodiscard]] double units_held(SecurityId security, OwnerId holder) const noexcept;
    [[nodiscard]] double total_units(SecurityId security) const noexcept;
    [[nodiscard]] Money total_bond_face() const noexcept;
    [[nodiscard]] std::uint64_t version() const noexcept;
    [[nodiscard]] SecurityBookMemoryUsage memory_usage() const noexcept;
    [[nodiscard]] Status validate_records(double tolerance) const;
    [[nodiscard]] Status validate(double tolerance) const;
    [[nodiscard]] Status validate_indexes() const;

    void replace_records(std::vector<BondContract> bonds,
                         std::vector<EquityContract> equities,
                         std::vector<SecurityLot> lots, std::uint64_t version);

  private:
    struct LotChain final {
        std::uint32_t head{0U};
        std::uint32_t tail{0U};

        bool operator==(const LotChain &) const = default;
    };

    [[nodiscard]] Result<SecurityLotId> create_lot(SecurityId security, OwnerId holder,
                                                   double units, Money cost_basis);
    [[nodiscard]] SecurityLot *find_active_lot(SecurityId security,
                                               OwnerId holder) noexcept;
    [[nodiscard]] const SecurityLot *find_active_lot(SecurityId security,
                                                     OwnerId holder) const noexcept;
    [[nodiscard]] SecurityLotId
    id_for_lot(const SecurityLot &lot) const noexcept;
    [[nodiscard]] std::size_t
    find_pair_slot(SecurityId security, OwnerId holder) const noexcept;
    [[nodiscard]] static std::size_t pair_hash(SecurityId security,
                                               OwnerId holder) noexcept;
    void append_pair_lot(SecurityLotId lot);
    void append_query_lot(SecurityLotId lot);
    void append_pending_query_lots();
    void unlink_query_lot(SecurityLotId lot);
    void deactivate_lot(SecurityLot &lot);
    void record_household_position_change(SecurityId security, OwnerId holder);
    void rebuild_pair_index();
    void rebuild_query_indexes();
    [[nodiscard]] Status validate_security(SecurityId security) const noexcept;
    [[nodiscard]] Status mutation_complete(bool contract_indexes_dirty = false);
    [[nodiscard]] Status rebuild_indexes();
    [[nodiscard]] Status rebuild_contract_indexes();
    void bump_version() noexcept;

    std::vector<BondContract> bonds_;
    std::vector<EquityContract> equities_;
    std::vector<SecurityLot> lots_;
    std::uint64_t version_{0};

    std::array<std::vector<LotChain>, 8U> holder_chains_;
    std::array<std::vector<LotChain>, 2U> contract_chains_;
    std::vector<std::uint32_t> holder_next_;
    std::vector<std::uint32_t> contract_next_;
    std::size_t indexed_lot_count_{0U};
    std::vector<IssuerSecurityIndexEntry> issuer_index_;
    std::vector<SecurityId> issuer_securities_;
    std::vector<MaturityIndexEntry> maturity_index_;
    std::vector<BondId> maturity_bonds_;
    std::vector<std::uint32_t> pair_slots_;
    std::size_t pair_count_{0};
    bool duplicate_active_pairs_{false};
    std::size_t active_lot_count_{0};
    std::size_t inactive_lot_count_{0};
    std::vector<HouseholdSecurityPositionChange> household_position_changes_;
    std::vector<std::pair<OwnerId, SecurityId>> issuer_rows_scratch_;
    std::vector<std::pair<Tick, BondId>> maturity_rows_scratch_;
    bool batch_active_{false};
    bool batch_dirty_{false};
    bool batch_contract_indexes_dirty_{false};
};

} // namespace macro_sim::core

#endif
