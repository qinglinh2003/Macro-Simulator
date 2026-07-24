#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <new>
#include <string_view>
#include <utility>
#include <vector>

#include "macro_sim/core/invariants.hpp"
#include "macro_sim/core/root_state.hpp"
#include "macro_sim/core/transaction.hpp"

namespace macro_sim::core {

class AccountingBenchmarkAccess final {
public:
    [[nodiscard]] static Status transfer_no_journal(
        PostingBook& postings,
        AccountId source,
        AccountId destination,
        Money amount
    ) noexcept {
        auto* source_account = postings.get(source);
        auto* destination_account = postings.get(destination);
        if (source_account == nullptr || destination_account == nullptr
            || !source_account->open || !destination_account->open
            || !std::isfinite(amount.value())
            || amount.value() < 0.0
            || (!source_account->allow_negative
                && source_account->balance.value() - amount.value()
                    < 0.0)) {
            return Status(
                ErrorCode::contract_violation,
                "benchmark transfer is invalid"
            );
        }
        static_cast<void>(
            postings.apply_delta_unchecked(source, -amount.value())
        );
        static_cast<void>(
            postings.apply_delta_unchecked(destination, amount.value())
        );
        return Status::success();
    }
};

}  // namespace macro_sim::core

namespace {

std::atomic<bool> allocation_measurement{false};
std::atomic<std::uint64_t> measured_allocations{0};

using Clock = std::chrono::steady_clock;
using macro_sim::AccountId;
using macro_sim::HouseholdId;
using macro_sim::Money;
using macro_sim::core::GenesisSpec;
using macro_sim::core::RootState;
using macro_sim::core::SettlementBatch;
using macro_sim::core::SettlementTransaction;
using macro_sim::core::TransactionWorkspace;

struct Statistics final {
    std::uint64_t median{0};
    std::uint64_t p95{0};
    std::uint64_t p99{0};
};

[[nodiscard]] Statistics statistics(std::vector<std::uint64_t> samples) {
    std::sort(samples.begin(), samples.end());
    const auto percentile = [&samples](std::size_t numerator) {
        const auto index =
            ((samples.size() - 1) * numerator + 99) / 100;
        return samples[index];
    };
    return {
        samples[samples.size() / 2],
        percentile(95),
        percentile(99),
    };
}

[[nodiscard]] RootState make_state() {
    GenesisSpec spec;
    spec.households = 64;
    spec.consumption_firms = 8;
    spec.settlement_banks = 2;
    spec.aggregate_opening_money = Money(6400.0);
    auto state = macro_sim::core::build_genesis(spec);
    assert(state.ok());
    return std::move(state).take();
}

[[nodiscard]] AccountId household_account(
    RootState& state,
    std::uint64_t id
) {
    const auto* household = state.households.get(HouseholdId(id));
    assert(household != nullptr);
    return household->primary_account;
}

template <typename Function>
[[nodiscard]] Statistics measure(
    std::size_t repetitions,
    Function&& function
) {
    std::vector<std::uint64_t> samples;
    samples.reserve(repetitions);
    for (std::size_t index = 0; index < repetitions; ++index) {
        const auto start = Clock::now();
        function(index);
        const auto stop = Clock::now();
        samples.push_back(
            static_cast<std::uint64_t>(
                std::chrono::duration_cast<std::chrono::nanoseconds>(
                    stop - start
                ).count()
            )
        );
    }
    return statistics(std::move(samples));
}

template <typename Factory>
[[nodiscard]] Statistics measure_prepared_commit(
    std::size_t repetitions,
    Factory&& factory
) {
    std::vector<std::uint64_t> samples;
    samples.reserve(repetitions);
    for (std::size_t index = 0; index < repetitions; ++index) {
        auto transaction = factory(index);
        transaction->reserve_capacity();
        const auto start = Clock::now();
        const auto result = transaction->commit();
        const auto stop = Clock::now();
        assert(result.ok());
        samples.push_back(
            static_cast<std::uint64_t>(
                std::chrono::duration_cast<std::chrono::nanoseconds>(
                    stop - start
                ).count()
            )
        );
    }
    return statistics(std::move(samples));
}

void print_statistics(
    std::string_view name,
    const Statistics& value,
    std::uint64_t divisor = 1
) {
    std::cout << '"' << name << "\":{"
              << "\"median_ns\":" << value.median / divisor << ','
              << "\"p95_ns\":" << value.p95 / divisor << ','
              << "\"p99_ns\":" << value.p99 / divisor << '}';
}

}  // namespace

void* operator new(std::size_t size) {
    if (allocation_measurement.load(std::memory_order_relaxed)) {
        measured_allocations.fetch_add(1, std::memory_order_relaxed);
    }
    if (void* pointer = std::malloc(size); pointer != nullptr) {
        return pointer;
    }
    throw std::bad_alloc();
}

void operator delete(void* pointer) noexcept {
    std::free(pointer);
}

void operator delete(void* pointer, std::size_t) noexcept {
    std::free(pointer);
}

int main(int argc, char** argv) {
    std::size_t repetitions = 1000;
    if (argc == 3 && std::string_view(argv[1]) == "--repetitions") {
        repetitions = static_cast<std::size_t>(
            std::strtoull(argv[2], nullptr, 10)
        );
    }
    if (repetitions < 10) {
        std::cerr << "repetitions must be at least 10\n";
        return 2;
    }

    auto state = make_state();
    const auto same_first = household_account(state, 1);
    const auto same_second = household_account(state, 3);
    const auto cross_first = household_account(state, 1);
    const auto cross_second = household_account(state, 2);

    const auto no_journal = measure(
        repetitions * 10,
        [&state, same_first, same_second](std::size_t index) {
            const auto status =
                index % 2 == 0
                ? macro_sim::core::AccountingBenchmarkAccess::
                    transfer_no_journal(
                        state.postings,
                        same_first,
                        same_second,
                        Money(0.5)
                    )
                : macro_sim::core::AccountingBenchmarkAccess::
                    transfer_no_journal(
                        state.postings,
                        same_second,
                        same_first,
                        Money(0.5)
                    );
            assert(status.ok());
        }
    );

    TransactionWorkspace workspace;
    workspace.reserve(state);
    const auto same_bank = measure(
        repetitions,
        [&state, &workspace, same_first, same_second](std::size_t index) {
            SettlementTransaction transaction(state, workspace);
            const auto status =
                index % 2 == 0
                ? transaction.transfer(
                    same_first,
                    same_second,
                    Money(0.5)
                )
                : transaction.transfer(
                    same_second,
                    same_first,
                    Money(0.5)
                );
            assert(status.ok());
            assert(transaction.commit().ok());
        }
    );
    const auto cross_bank = measure(
        repetitions,
        [&state, &workspace, cross_first, cross_second](std::size_t index) {
            SettlementTransaction transaction(state, workspace);
            const auto status =
                index % 2 == 0
                ? transaction.transfer(
                    cross_first,
                    cross_second,
                    Money(0.25)
                )
                : transaction.transfer(
                    cross_second,
                    cross_first,
                    Money(0.25)
                );
            assert(status.ok());
            assert(transaction.commit().ok());
        }
    );

    constexpr std::uint64_t batch_size = 1024;
    SettlementBatch batch;
    batch.transfers.reserve(batch_size);
    for (std::uint64_t index = 0; index < batch_size; ++index) {
        batch.transfers.push_back(
            index % 2 == 0
            ? macro_sim::core::TransferCommand{
                cross_first,
                cross_second,
                Money(0.01),
            }
            : macro_sim::core::TransferCommand{
                cross_second,
                cross_first,
                Money(0.01),
            }
        );
    }
    const auto batch_commit = measure_prepared_commit(
        repetitions,
        [&state, &workspace, &batch](std::size_t) {
            auto transaction = std::make_unique<SettlementTransaction>(
                state,
                workspace
            );
            assert(transaction->append(batch).ok());
            return transaction;
        }
    );
    SettlementBatch rollback_batch;
    rollback_batch.transfers.reserve(batch_size);
    for (std::uint64_t index = 0; index < batch_size; ++index) {
        rollback_batch.transfers.push_back(
            {
                cross_first,
                cross_second,
                Money(0.001),
            }
        );
    }
    const auto rollback = measure(
        repetitions,
        [&state, &workspace, &rollback_batch](std::size_t) {
            SettlementTransaction transaction(state, workspace, 2);
            assert(transaction.append(rollback_batch).ok());
            transaction.reserve_capacity();
            const auto before = macro_sim::core::state_digest(state);
            const auto result = transaction.commit();
            assert(!result.ok());
            assert(macro_sim::core::state_digest(state) == before);
        }
    );

    std::uint64_t no_journal_allocations = 0;
    measured_allocations.store(0, std::memory_order_relaxed);
    allocation_measurement.store(true, std::memory_order_relaxed);
    assert(
        macro_sim::core::AccountingBenchmarkAccess::transfer_no_journal(
            state.postings,
            same_first,
            same_second,
            Money(0.5)
        ).ok()
    );
    assert(
        macro_sim::core::AccountingBenchmarkAccess::transfer_no_journal(
            state.postings,
            same_second,
            same_first,
            Money(0.5)
        ).ok()
    );
    allocation_measurement.store(false, std::memory_order_relaxed);
    no_journal_allocations =
        measured_allocations.load(std::memory_order_relaxed);

    auto measured_transaction = std::make_unique<SettlementTransaction>(
        state,
        workspace
    );
    assert(measured_transaction->append(batch).ok());
    measured_transaction->reserve_capacity();
    measured_allocations.store(0, std::memory_order_relaxed);
    allocation_measurement.store(true, std::memory_order_relaxed);
    const auto measured_receipt = measured_transaction->commit();
    allocation_measurement.store(false, std::memory_order_relaxed);
    assert(measured_receipt.ok());
    const auto batch_allocations =
        measured_allocations.load(std::memory_order_relaxed);

    auto rollback_transaction = std::make_unique<SettlementTransaction>(
        state,
        workspace,
        2
    );
    assert(rollback_transaction->append(rollback_batch).ok());
    rollback_transaction->reserve_capacity();
    measured_allocations.store(0, std::memory_order_relaxed);
    allocation_measurement.store(true, std::memory_order_relaxed);
    const auto rollback_receipt = rollback_transaction->commit();
    allocation_measurement.store(false, std::memory_order_relaxed);
    assert(!rollback_receipt.ok());
    const auto rollback_allocations =
        measured_allocations.load(std::memory_order_relaxed);

    assert(macro_sim::core::run_invariants(state).ok());
    std::cout << '{'
              << "\"schema_version\":\"m2-accounting-benchmark-v1\","
              << "\"repetitions\":" << repetitions << ','
              << "\"batch_size\":" << batch_size << ',';
    print_statistics("no_journal_transfer", no_journal);
    std::cout << ',';
    print_statistics("same_bank_commit", same_bank);
    std::cout << ',';
    print_statistics("cross_bank_commit", cross_bank);
    std::cout << ',';
    print_statistics("batch_commit_per_transfer", batch_commit, batch_size);
    std::cout << ',';
    print_statistics("rollback_per_transfer", rollback, batch_size);
    std::cout << ",\"no_journal_measured_allocations\":"
              << no_journal_allocations
              << ",\"batch_measured_allocations\":"
              << batch_allocations
              << ",\"rollback_measured_allocations\":"
              << rollback_allocations
              << ",\"invariant_status\":\"passed\"}\n";
    return 0;
}
