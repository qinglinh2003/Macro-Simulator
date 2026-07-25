#ifndef MACRO_SIM_IDS_HPP
#define MACRO_SIM_IDS_HPP

#include <compare>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <limits>
#include <type_traits>

namespace macro_sim {

template <typename Tag, typename Rep = std::uint64_t> class StrongId final {
    static_assert(std::is_integral_v<Rep>);
    static_assert(std::is_unsigned_v<Rep>);

  public:
    using rep_type = Rep;

    constexpr StrongId() noexcept = default;
    explicit constexpr StrongId(Rep value) noexcept : value_(value) {}

    [[nodiscard]] static constexpr StrongId invalid() noexcept {
        return StrongId(std::numeric_limits<Rep>::max());
    }

    [[nodiscard]] constexpr bool valid() const noexcept {
        return value_ != invalid().value_;
    }

    [[nodiscard]] explicit constexpr operator Rep() const noexcept { return value_; }

    [[nodiscard]] constexpr Rep value() const noexcept { return value_; }

    constexpr auto operator<=>(const StrongId &) const noexcept = default;

  private:
    Rep value_{std::numeric_limits<Rep>::max()};
};

struct AccountIdTag;
struct BankIdTag;
struct BeneficialLotIdTag;
struct BondIdTag;
struct CentralBankOperationIdTag;
struct CurrencyIdTag;
struct EconomyIdTag;
struct EntityIdTag;
struct EquityIdTag;
struct EventIdTag;
struct FirmIdTag;
struct HouseholdIdTag;
struct InstitutionIdTag;
struct InterbankContractIdTag;
struct JobIdTag;
struct LoanIdTag;
struct PersonIdTag;
struct OwnershipLotIdTag;
struct SecurityLotIdTag;
struct SessionIdTag;
struct SettlementNodeIdTag;

using AccountId = StrongId<AccountIdTag>;
using BankId = StrongId<BankIdTag>;
using BeneficialLotId = StrongId<BeneficialLotIdTag>;
using BondId = StrongId<BondIdTag>;
using CentralBankOperationId = StrongId<CentralBankOperationIdTag>;
using CurrencyId = StrongId<CurrencyIdTag, std::uint32_t>;
using EconomyId = StrongId<EconomyIdTag>;
using EntityId = StrongId<EntityIdTag>;
using EquityId = StrongId<EquityIdTag>;
using EventId = StrongId<EventIdTag>;
using FirmId = StrongId<FirmIdTag>;
using HouseholdId = StrongId<HouseholdIdTag>;
using InstitutionId = StrongId<InstitutionIdTag>;
using InterbankContractId = StrongId<InterbankContractIdTag>;
using JobId = StrongId<JobIdTag>;
using LoanId = StrongId<LoanIdTag>;
using PersonId = StrongId<PersonIdTag>;
using OwnershipLotId = StrongId<OwnershipLotIdTag>;
using SecurityLotId = StrongId<SecurityLotIdTag>;
using SessionId = StrongId<SessionIdTag>;
using SettlementNodeId = StrongId<SettlementNodeIdTag>;

template <typename Id> struct StrongIdHash final {
    [[nodiscard]] std::size_t operator()(Id value) const noexcept {
        return std::hash<typename Id::rep_type>{}(value.value());
    }
};

static_assert(!std::is_convertible_v<EntityId, HouseholdId>);
static_assert(!std::is_convertible_v<HouseholdId, EntityId>);
static_assert(!std::is_convertible_v<SessionId, std::uint64_t>);

} // namespace macro_sim

#endif
