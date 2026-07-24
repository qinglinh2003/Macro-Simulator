#include <cassert>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iterator>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include "macro_sim/core/checkpoint.hpp"
#include "macro_sim/core/digest.hpp"
#include "macro_sim/core/root_state.hpp"
#include "macro_sim/core/transaction.hpp"

namespace {

using macro_sim::BankId;
using macro_sim::Capital;
using macro_sim::HouseholdId;
using macro_sim::Money;
using macro_sim::Rate;
using macro_sim::Tick;
using macro_sim::core::CheckpointLimits;
using macro_sim::core::GenesisSpec;
using macro_sim::core::GenesisVertical;
using macro_sim::core::LoanTerms;
using macro_sim::core::OwnerId;
using macro_sim::core::RootState;
using macro_sim::core::SettlementTransaction;

[[nodiscard]] RootState make_state() {
    GenesisSpec spec;
    spec.vertical = GenesisVertical::m4_v1_capital_fiscal;
    spec.households = 7;
    spec.consumption_firms = 3;
    spec.capital_firms = 2;
    spec.settlement_banks = 2;
    spec.government = true;
    spec.aggregate_opening_money = Money(700.0);
    spec.aggregate_opening_capital = Capital(55.0);
    spec.seed = 0x123456789abcdef0ULL;
    spec.named_counter_streams = {9, 17};
    auto result = macro_sim::core::build_genesis(spec);
    assert(result.ok());
    auto state = std::move(result).take();

    const auto* first = state.households.get(HouseholdId(1));
    const auto* second = state.households.get(HouseholdId(2));
    assert(first != nullptr);
    assert(second != nullptr);
    SettlementTransaction transaction(state);
    assert(
        transaction.transfer(
            first->primary_account,
            second->primary_account,
            Money(13.25)
        ).ok()
    );
    assert(
        transaction.originate_loan(
            BankId(1),
            OwnerId::household(HouseholdId(1)),
            first->primary_account,
            Money(27.5),
            LoanTerms{Rate(0.0375), Tick(12), Tick(742)}
        ).ok()
    );
    assert(transaction.increment_counter(9, 17).ok());
    assert(transaction.commit().ok());
    return state;
}

[[nodiscard]] std::vector<std::uint8_t> from_hex(
    const std::string& encoded
) {
    assert(encoded.size() % 2 == 0);
    std::vector<std::uint8_t> output;
    output.reserve(encoded.size() / 2);
    for (std::size_t index = 0; index < encoded.size(); index += 2) {
        output.push_back(
            static_cast<std::uint8_t>(
                std::stoul(encoded.substr(index, 2), nullptr, 16)
            )
        );
    }
    return output;
}

void test_deterministic_round_trip_and_continuation() {
    auto state = make_state();
    const auto before = macro_sim::core::state_digest(state);
    const auto first = macro_sim::core::save_checkpoint(state);
    const auto second = macro_sim::core::save_checkpoint(state);
    assert(first.ok());
    assert(second.ok());
    assert(*first.get_if() == *second.get_if());

    auto loaded_result = macro_sim::core::load_checkpoint(*first.get_if());
    assert(loaded_result.ok());
    auto loaded = std::move(loaded_result).take();
    assert(macro_sim::core::state_digest(loaded) == before);
    assert(loaded.seed == 0x123456789abcdef0ULL);
    assert(loaded.named_counters.contains(9));
    assert(loaded.named_counters.contains(17));
    const auto repeated = macro_sim::core::save_checkpoint(loaded);
    assert(repeated.ok());
    assert(*repeated.get_if() == *first.get_if());

    const auto source =
        state.households.get(HouseholdId(3))->primary_account;
    const auto destination =
        state.households.get(HouseholdId(4))->primary_account;
    SettlementTransaction original_continuation(state);
    SettlementTransaction loaded_continuation(loaded);
    assert(
        original_continuation.transfer(
            source,
            destination,
            Money(4.125)
        ).ok()
    );
    assert(
        loaded_continuation.transfer(
            source,
            destination,
            Money(4.125)
        ).ok()
    );
    assert(original_continuation.commit().ok());
    assert(loaded_continuation.commit().ok());
    assert(
        macro_sim::core::state_digest(state)
        == macro_sim::core::state_digest(loaded)
    );
}

void test_corruption_limits_and_active_transaction_are_rejected() {
    auto state = make_state();
    const auto checkpoint = macro_sim::core::save_checkpoint(state);
    assert(checkpoint.ok());

    auto corrupted = *checkpoint.get_if();
    corrupted[corrupted.size() / 2] ^= 0x01U;
    const auto corrupt_result =
        macro_sim::core::load_checkpoint(corrupted);
    assert(!corrupt_result.ok());
    assert(
        corrupt_result.status().code()
        == macro_sim::ErrorCode::corrupt_input
    );

    CheckpointLimits limits;
    limits.maximum_archive_bytes = checkpoint.get_if()->size() - 1;
    const auto limited =
        macro_sim::core::load_checkpoint(*checkpoint.get_if(), limits);
    assert(!limited.ok());
    assert(limited.status().code() == macro_sim::ErrorCode::corrupt_input);

    SettlementTransaction active(state);
    const auto active_save = macro_sim::core::save_checkpoint(state);
    assert(!active_save.ok());
    assert(
        active_save.status().code()
        == macro_sim::ErrorCode::invalid_transaction_state
    );
    assert(active.commit().ok());
}

void test_m1_canonical_json_vectors() {
    const std::string path =
        std::string(MACRO_SIM_SOURCE_DIR)
        + "/schemas/m1/canonical_encoding_vectors.json";
    std::ifstream stream(path);
    assert(stream.good());
    const nlohmann::json vectors = nlohmann::json::parse(
        std::string(
            std::istreambuf_iterator<char>(stream),
            std::istreambuf_iterator<char>()
        )
    );
    for (const auto& item : vectors["valid"]) {
        const auto encoded =
            from_hex(item["canonical_hex"].get<std::string>());
        assert(macro_sim::core::validate_canonical_json(encoded).ok());
    }
    for (const auto& item : vectors["invalid"]) {
        const auto encoded = from_hex(item["input_hex"].get<std::string>());
        assert(!macro_sim::core::validate_canonical_json(encoded).ok());
    }
}

void test_sha256_known_vectors() {
    const std::vector<std::uint8_t> empty;
    const std::vector<std::uint8_t> abc{'a', 'b', 'c'};
    assert(
        macro_sim::core::sha256_digest(empty).hex()
        == "e3b0c44298fc1c149afbf4c8996fb924"
           "27ae41e4649b934ca495991b7852b855"
    );
    assert(
        macro_sim::core::sha256_digest(abc).hex()
        == "ba7816bf8f01cfea414140de5dae2223"
           "b00361a396177a9cb410ff61f20015ad"
    );
}

}  // namespace

int main() {
    test_deterministic_round_trip_and_continuation();
    test_corruption_limits_and_active_transaction_are_rejected();
    test_m1_canonical_json_vectors();
    test_sha256_known_vectors();
    return 0;
}
