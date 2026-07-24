#include <cassert>
#include <cstdint>
#include <utility>
#include <vector>

#include "macro_sim/core/digest.hpp"
#include "macro_sim/core/invariants.hpp"
#include "macro_sim/core/root_state.hpp"
#include "macro_sim/core/transaction.hpp"

namespace {

using macro_sim::AccountId;
using macro_sim::BankId;
using macro_sim::HouseholdId;
using macro_sim::LoanId;
using macro_sim::Money;
using macro_sim::Rate;
using macro_sim::Tick;
using macro_sim::core::GenesisSpec;
using macro_sim::core::LoanTerms;
using macro_sim::core::OwnerId;
using macro_sim::core::RootState;
using macro_sim::core::SettlementTransaction;

[[nodiscard]] RootState make_state() {
    GenesisSpec spec;
    spec.households = 4;
    spec.consumption_firms = 2;
    spec.settlement_banks = 2;
    spec.aggregate_opening_money = Money(400.0);
    auto result = macro_sim::core::build_genesis(spec);
    assert(result.ok());
    return std::move(result).take();
}

[[nodiscard]] AccountId account_for(
    RootState& state,
    HouseholdId id
) {
    const auto* household = state.households.get(id);
    assert(household != nullptr);
    return household->primary_account;
}

[[nodiscard]] double balance(RootState& state, AccountId id) {
    const auto result = state.postings.balance(id);
    assert(result.ok());
    return result.get_if()->value();
}

void add_mixed_commands(SettlementTransaction& transaction, RootState& state) {
    const auto first = account_for(state, HouseholdId(1));
    const auto second = account_for(state, HouseholdId(2));
    assert(transaction.transfer(first, second, Money(12.0)).ok());
    assert(
        transaction.originate_loan(
            BankId(1),
            OwnerId::household(HouseholdId(1)),
            first,
            Money(25.0),
            LoanTerms{Rate(0.05), Tick(0), Tick(365)}
        ).ok()
    );
    assert(transaction.increment_counter(17, 3).ok());
}

void test_same_and_cross_bank_transfers_are_atomic() {
    auto state = make_state();
    const auto first = account_for(state, HouseholdId(1));
    const auto second = account_for(state, HouseholdId(2));
    const auto third = account_for(state, HouseholdId(3));
    const auto first_node = state.postings.get(first)->key.settlement_node;
    const auto second_node = state.postings.get(second)->key.settlement_node;
    const auto third_node = state.postings.get(third)->key.settlement_node;
    assert(first_node != second_node);
    assert(first_node == third_node);

    const auto reserve_before = state.reserves.balance(first_node);
    SettlementTransaction same_bank(state);
    assert(same_bank.transfer(first, third, Money(10.0)).ok());
    const auto same_receipt = same_bank.commit();
    assert(same_receipt.ok());
    assert(balance(state, first) == 90.0);
    assert(balance(state, third) == 110.0);
    assert(state.reserves.balance(first_node).get_if()->value()
           == reserve_before.get_if()->value());

    const auto first_reserve = state.reserves.balance(first_node).get_if()->value();
    const auto second_reserve =
        state.reserves.balance(second_node).get_if()->value();
    SettlementTransaction cross_bank(state);
    assert(cross_bank.transfer(first, second, Money(20.0)).ok());
    const auto cross_receipt = cross_bank.commit();
    assert(cross_receipt.ok());
    assert(balance(state, first) == 70.0);
    assert(balance(state, second) == 120.0);
    assert(
        state.reserves.balance(first_node).get_if()->value()
        == first_reserve - 20.0
    );
    assert(
        state.reserves.balance(second_node).get_if()->value()
        == second_reserve + 20.0
    );
    assert(macro_sim::core::run_invariants(state).ok());
}

void test_origination_and_repayment_preserve_a5() {
    auto state = make_state();
    const auto borrower = account_for(state, HouseholdId(1));
    SettlementTransaction origination(state);
    assert(
        origination.originate_loan(
            BankId(1),
            OwnerId::household(HouseholdId(1)),
            borrower,
            Money(40.0),
            LoanTerms{Rate(0.04), Tick(0), Tick(730)}
        ).ok()
    );
    const auto receipt = origination.commit();
    assert(receipt.ok());
    assert(receipt.get_if()->created_loans.size() == 1);
    assert(receipt.get_if()->created_loans.front() == LoanId(1));
    assert(balance(state, borrower) == 140.0);
    assert(state.loans.total_principal() == Money(40.0));
    assert(macro_sim::core::run_invariants(state).ok());

    SettlementTransaction repayment(state);
    assert(repayment.repay_loan(LoanId(1), borrower, Money(15.0)).ok());
    assert(repayment.commit().ok());
    assert(balance(state, borrower) == 125.0);
    assert(state.loans.total_principal() == Money(25.0));
    assert(macro_sim::core::run_invariants(state).ok());
}

void test_invalid_batch_restores_exact_digest() {
    auto state = make_state();
    const auto before = macro_sim::core::state_digest(state);
    const auto first = account_for(state, HouseholdId(1));
    const auto second = account_for(state, HouseholdId(2));
    SettlementTransaction transaction(state);
    assert(transaction.transfer(first, second, Money(101.0)).ok());
    const auto result = transaction.commit();
    assert(!result.ok());
    assert(result.status().code() == macro_sim::ErrorCode::insufficient_funds);
    assert(macro_sim::core::state_digest(state) == before);
    assert(!state.transaction_active);
}

void test_every_fault_ordinal_restores_exact_digest() {
    auto reference = make_state();
    SettlementTransaction accepted(reference);
    add_mixed_commands(accepted, reference);
    const auto accepted_result = accepted.commit();
    assert(accepted_result.ok());
    const auto fault_count = accepted.next_fault_ordinal();
    assert(fault_count > 5);

    for (std::uint64_t ordinal = 0; ordinal < fault_count; ++ordinal) {
        auto state = make_state();
        const auto before = macro_sim::core::state_digest(state);
        SettlementTransaction transaction(state, ordinal);
        add_mixed_commands(transaction, state);
        const auto result = transaction.commit();
        assert(!result.ok());
        assert(result.status().code() == macro_sim::ErrorCode::internal_error);
        assert(macro_sim::core::state_digest(state) == before);
        assert(state.loans.size() == 0);
        assert(state.named_counters.value(17) == 0);
        assert(!state.transaction_active);
    }
}

void test_nested_transaction_is_rejected_without_releasing_owner() {
    auto state = make_state();
    SettlementTransaction outer(state);
    assert(state.transaction_active);
    {
        SettlementTransaction nested(state);
        const auto result = nested.commit();
        assert(!result.ok());
        assert(
            result.status().code()
            == macro_sim::ErrorCode::invalid_transaction_state
        );
        assert(state.transaction_active);
    }
    assert(outer.commit().ok());
    assert(!state.transaction_active);
}

}  // namespace

int main() {
    test_same_and_cross_bank_transfers_are_atomic();
    test_origination_and_repayment_preserve_a5();
    test_invalid_batch_restores_exact_digest();
    test_every_fault_ordinal_restores_exact_digest();
    test_nested_transaction_is_rejected_without_releasing_owner();
    return 0;
}
