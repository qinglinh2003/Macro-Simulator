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

[[nodiscard]] bool account_matches(
    const RootState& state,
    AccountId account_id,
    OwnerId owner,
    AccountKind kind
) noexcept {
    const auto* account = state.postings.get(account_id);
    return account != nullptr && account->open && account->key.owner == owner
        && account->key.kind == kind
        && account->key.economy == state.economy
        && account->key.currency == state.currency
        && state.reserves.contains(account->key.settlement_node);
}

}  // namespace

InvariantReport run_invariants(const RootState& state) noexcept {
    if (!state.economy.valid() || !state.currency.valid()
        || !std::isfinite(state.genesis_money.value())
        || !std::isfinite(state.accounting_tolerance)
        || state.accounting_tolerance < 0.0
        || !std::isfinite(state.reserves.reserve_stock().value())
        || !std::isfinite(state.reserves.reserve_stock_roundoff_drift())) {
        return failure(InvariantId::finite_state);
    }
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

    bool canonical_references = true;
    state.households.for_each_alive(
        [&state, &canonical_references](
            HouseholdId id,
            const HouseholdComponent& household
        ) {
            canonical_references =
                canonical_references
                && account_matches(
                    state,
                    household.primary_account,
                    OwnerId::household(id),
                    AccountKind::deposit
                );
        }
    );
    state.firms.for_each_alive(
        [&state, &canonical_references](
            FirmId id,
            const FirmComponent& firm
        ) {
            canonical_references =
                canonical_references
                && account_matches(
                    state,
                    firm.primary_account,
                    OwnerId::firm(id),
                    AccountKind::deposit
                )
                && firm.goods_inventory.value() >= 0.0
                && firm.physical_capital.value() >= 0.0
                && firm.productivity >= 0.0;
        }
    );
    state.banks.for_each_alive(
        [&state, &canonical_references](
            BankId id,
            const BankComponent& bank
        ) {
            const auto* reserve = state.reserves.get(bank.settlement_node);
            canonical_references =
                canonical_references
                && reserve != nullptr && reserve->bank == id
                && account_matches(
                    state,
                    bank.cash_account,
                    OwnerId::bank(id),
                    AccountKind::bank_cash
                );
        }
    );
    for (const auto& account : state.postings.records()) {
        if (!account.open) {
            continue;
        }
        canonical_references =
            canonical_references && account.id.valid()
            && account.key.economy == state.economy
            && account.key.currency == state.currency
            && owner_exists(state, account.key.owner)
            && state.reserves.contains(account.key.settlement_node);
    }
    for (const auto& reserve : state.reserves.records()) {
        canonical_references =
            canonical_references
            && state.banks.get(reserve.bank) != nullptr;
    }
    canonical_references =
        canonical_references
        && account_matches(
            state,
            state.institutions.central_bank_account,
            OwnerId::institutional(OwnerKind::central_bank),
            AccountKind::central_bank
        )
        && account_matches(
            state,
            state.institutions.dealer_account,
            OwnerId::institutional(OwnerKind::dealer),
            AccountKind::dealer
        )
        && account_matches(
            state,
            state.institutions.rounding_residual_account,
            OwnerId::institutional(OwnerKind::rounding_residual),
            AccountKind::rounding_residual
        );
    if (state.institutions.treasury_account.valid()) {
        canonical_references =
            canonical_references
            && account_matches(
                state,
                state.institutions.treasury_account,
                OwnerId::institutional(OwnerKind::treasury),
                AccountKind::treasury
            );
    }
    if (!canonical_references) {
        return failure(InvariantId::canonical_references);
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
        if (lot.asset.economy != state.economy || lot.asset.value == 0) {
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
