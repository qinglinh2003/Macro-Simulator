#include "macro_sim/core/invariants.hpp"

#include <algorithm>
#include <cmath>

namespace macro_sim::core {
namespace {

[[nodiscard]] bool owner_exists(
    const RootState& state,
    OwnerId owner
) noexcept {
    switch (owner.kind) {
        case OwnerKind::household:
            return state.households.get(HouseholdId(owner.value)) != nullptr;
        case OwnerKind::firm:
            return state.firms.get(FirmId(owner.value)) != nullptr;
        case OwnerKind::bank:
            return state.banks.get(BankId(owner.value)) != nullptr;
        case OwnerKind::treasury:
        case OwnerKind::central_bank:
        case OwnerKind::dealer:
        case OwnerKind::rounding_residual:
        case OwnerKind::institution:
            return owner.valid();
    }
    return false;
}

[[nodiscard]] InvariantReport failure(
    InvariantId id,
    double observed = 0.0,
    double expected = 0.0,
    double tolerance = 0.0
) noexcept {
    return {
        Status(ErrorCode::invariant_violation, invariant_id_name(id)),
        id,
        observed,
        expected,
        tolerance,
    };
}

}  // namespace

InvariantReport run_invariants(const RootState& state) noexcept {
    if (!state.postings.validate_finite().ok()
        || !state.reserves.validate_finite().ok()
        || !state.loans.validate_finite().ok()) {
        return failure(InvariantId::finite_state);
    }
    bool finite_components = true;
    state.firms.for_each_alive(
        [&finite_components](FirmId, const FirmComponent& firm) {
            finite_components =
                finite_components
                && std::isfinite(firm.goods_inventory.value())
                && std::isfinite(firm.physical_capital.value())
                && std::isfinite(firm.productivity);
        }
    );
    if (!finite_components) {
        return failure(InvariantId::finite_state);
    }

    const auto nonnegative = state.postings.validate_nonnegative(
        state.accounting_tolerance
    );
    if (!nonnegative.ok()) {
        return failure(InvariantId::nonnegative_balances);
    }

    const double deposits = state.postings.total_deposits().value();
    const double principal = state.loans.total_principal().value();
    const double net_worth = deposits - principal;
    const double expected_net_worth = state.genesis_money.value();
    const double tracked_a5 =
        state.postings.total_roundoff_drift()
        - state.loans.total_roundoff_drift();
    const double a5_unexplained =
        (net_worth - expected_net_worth) - tracked_a5;
    const double a5_tolerance = std::max(
        state.accounting_tolerance,
        1.0e-10
            * std::max(
                {std::abs(expected_net_worth), std::abs(deposits), 1.0}
            )
    );
    if (std::abs(a5_unexplained) > a5_tolerance) {
        return failure(
            InvariantId::deposit_conservation,
            net_worth - tracked_a5,
            expected_net_worth,
            a5_tolerance
        );
    }

    const double reserve_total = state.reserves.total_reserves().value();
    const double reserve_stock = state.reserves.reserve_stock().value();
    const double tracked_reserve =
        state.reserves.total_roundoff_drift()
        - state.reserves.reserve_stock_roundoff_drift();
    const double reserve_unexplained =
        (reserve_total - reserve_stock) - tracked_reserve;
    const double reserve_tolerance = std::max(
        state.accounting_tolerance,
        1.0e-10
            * std::max(
                {std::abs(reserve_stock), std::abs(reserve_total), 1.0}
            )
    );
    if (std::abs(reserve_unexplained) > reserve_tolerance) {
        return failure(
            InvariantId::reserve_conservation,
            reserve_total - tracked_reserve,
            reserve_stock,
            reserve_tolerance
        );
    }

    for (const auto& loan : state.loans.records()) {
        const auto* account = state.postings.get(loan.borrower_account);
        if (!loan.lender.valid() || state.banks.get(loan.lender) == nullptr
            || !owner_exists(state, loan.borrower) || account == nullptr
            || account->key.owner != loan.borrower) {
            return failure(InvariantId::loan_ownership);
        }
    }

    for (const auto& lot : state.ownership.records()) {
        if (!lot.active) {
            continue;
        }
        if (!owner_exists(state, lot.owner)) {
            return failure(InvariantId::ownership_lots);
        }
        if (lot.asset.kind == AssetKind::firm_equity
            && state.firms.get(FirmId(lot.asset.value)) == nullptr) {
            return failure(InvariantId::ownership_lots);
        }
    }
    if (!state.ownership.validate_shares(state.accounting_tolerance).ok()) {
        return failure(InvariantId::ownership_lots);
    }

    return {};
}

}  // namespace macro_sim::core
