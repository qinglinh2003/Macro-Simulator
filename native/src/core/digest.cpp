#include "macro_sim/core/digest.hpp"

#include <bit>
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <string_view>
#include <vector>

#include "macro_sim/core/root_state.hpp"
#include "picosha2.h"

namespace macro_sim::core {
namespace {

class DigestWriter final {
public:
    explicit DigestWriter(std::vector<std::uint8_t>& bytes) noexcept
        : bytes_(bytes) {
        bytes_.clear();
    }

    void text(std::string_view value) {
        u64(static_cast<std::uint64_t>(value.size()));
        bytes_.insert(bytes_.end(), value.begin(), value.end());
    }

    void boolean(bool value) {
        u8(value ? 1U : 0U);
    }

    void u8(std::uint8_t value) {
        bytes_.push_back(value);
    }

    void u32(std::uint32_t value) {
        for (int shift = 24; shift >= 0; shift -= 8) {
            u8(static_cast<std::uint8_t>(value >> shift));
        }
    }

    void u64(std::uint64_t value) {
        for (int shift = 56; shift >= 0; shift -= 8) {
            u8(static_cast<std::uint8_t>(value >> shift));
        }
    }

    void f64(double value) {
        u64(std::bit_cast<std::uint64_t>(value));
    }

    [[nodiscard]] const std::vector<std::uint8_t>& bytes() const noexcept {
        return bytes_;
    }

private:
    std::vector<std::uint8_t>& bytes_;
};

template <typename Id>
void append_id(DigestWriter& writer, Id id) {
    writer.u64(static_cast<std::uint64_t>(id.value()));
}

void append_owner(DigestWriter& writer, OwnerId owner) {
    writer.u8(static_cast<std::uint8_t>(owner.kind));
    writer.u64(owner.value);
}

template <typename Id, typename Value, typename AppendValue>
void append_slot_store(
    DigestWriter& writer,
    const SlotStore<Id, Value>& store,
    AppendValue&& append_value
) {
    const auto allocator = store.allocator_state();
    writer.u64(allocator.next_id);
    writer.u64(allocator.next_sequence);
    writer.u64(static_cast<std::uint64_t>(allocator.free_slots.size()));
    for (const auto index : allocator.free_slots) {
        writer.u32(index);
    }
    writer.u64(static_cast<std::uint64_t>(store.slots().size()));
    for (const auto& slot : store.slots()) {
        append_id(writer, slot.id);
        writer.u32(slot.generation);
        writer.u64(slot.sequence);
        writer.boolean(slot.value.has_value());
        if (slot.value.has_value()) {
            append_value(writer, *slot.value);
        }
    }
    writer.u64(static_cast<std::uint64_t>(store.iteration_order().size()));
    for (const auto id : store.iteration_order()) {
        append_id(writer, id);
    }
}

void append_account_key(DigestWriter& writer, const AccountKey& key) {
    writer.u8(static_cast<std::uint8_t>(key.kind));
    append_id(writer, key.economy);
    append_owner(writer, key.owner);
    writer.u32(key.currency.value());
    append_id(writer, key.settlement_node);
}

void append_root(DigestWriter& writer, const RootState& state) {
    writer.text("macro-sim-m2-state-digest-v1");
    append_id(writer, state.economy);
    writer.u32(state.currency.value());
    writer.u64(state.seed);
    writer.f64(state.genesis_money.value());
    writer.f64(state.accounting_tolerance);

    append_slot_store(
        writer,
        state.households,
        [](DigestWriter& output, const HouseholdComponent& household) {
            append_id(output, household.primary_account);
        }
    );
    append_slot_store(
        writer,
        state.firms,
        [](DigestWriter& output, const FirmComponent& firm) {
            output.u8(static_cast<std::uint8_t>(firm.sector));
            append_id(output, firm.primary_account);
            output.f64(firm.goods_inventory.value());
            output.f64(firm.physical_capital.value());
            output.f64(firm.productivity);
        }
    );
    append_slot_store(
        writer,
        state.banks,
        [](DigestWriter& output, const BankComponent& bank) {
            append_id(output, bank.cash_account);
            append_id(output, bank.settlement_node);
        }
    );

    writer.u64(static_cast<std::uint64_t>(state.postings.records().size()));
    for (const auto& account : state.postings.records()) {
        append_id(writer, account.id);
        append_account_key(writer, account.key);
        writer.f64(account.balance.value());
        writer.f64(account.roundoff_drift);
        writer.boolean(account.allow_negative);
        writer.boolean(account.open);
    }

    writer.u64(static_cast<std::uint64_t>(state.reserves.records().size()));
    for (const auto& reserve : state.reserves.records()) {
        append_id(writer, reserve.node);
        append_id(writer, reserve.bank);
        writer.f64(reserve.balance.value());
        writer.f64(reserve.roundoff_drift);
    }
    writer.f64(state.reserves.reserve_stock().value());
    writer.f64(state.reserves.reserve_stock_roundoff_drift());

    writer.u64(static_cast<std::uint64_t>(state.loans.records().size()));
    for (const auto& loan : state.loans.records()) {
        append_id(writer, loan.id);
        append_id(writer, loan.lender);
        append_owner(writer, loan.borrower);
        append_id(writer, loan.borrower_account);
        writer.f64(loan.principal.value());
        writer.f64(loan.roundoff_drift);
        writer.f64(loan.terms.annual_rate.value());
        writer.u64(loan.terms.originated_tick.value());
        writer.u64(loan.terms.maturity_tick.value());
        writer.boolean(loan.active);
        writer.u8(static_cast<std::uint8_t>(loan.purpose));
    }

    writer.u64(static_cast<std::uint64_t>(state.ownership.records().size()));
    for (const auto& lot : state.ownership.records()) {
        append_id(writer, lot.id);
        writer.u8(static_cast<std::uint8_t>(lot.asset.kind));
        append_id(writer, lot.asset.economy);
        writer.u64(lot.asset.value);
        append_owner(writer, lot.owner);
        writer.f64(lot.share);
        writer.boolean(lot.active);
    }

    writer.u64(
        static_cast<std::uint64_t>(state.named_counters.records().size())
    );
    for (const auto& [stream, value] : state.named_counters.records()) {
        writer.u64(stream);
        writer.u64(value);
    }

    append_id(writer, state.institutions.central_bank_account);
    append_id(writer, state.institutions.dealer_account);
    append_id(writer, state.institutions.rounding_residual_account);
    append_id(writer, state.institutions.treasury_account);
}

}  // namespace

StateDigest sha256_digest(
    std::span<const std::uint8_t> bytes
) noexcept {
    std::array<picosha2::word_t, 8> words{};
    std::copy(
        picosha2::detail::initial_message_digest,
        picosha2::detail::initial_message_digest + 8,
        words.begin()
    );
    std::size_t offset = 0;
    while (bytes.size() - offset >= 64) {
        picosha2::detail::hash256_block(
            words.begin(),
            bytes.begin() + static_cast<std::ptrdiff_t>(offset),
            bytes.begin() + static_cast<std::ptrdiff_t>(offset + 64)
        );
        offset += 64;
    }

    std::array<std::uint8_t, 128> final_blocks{};
    const auto remainder = bytes.size() - offset;
    std::copy(
        bytes.begin() + static_cast<std::ptrdiff_t>(offset),
        bytes.end(),
        final_blocks.begin()
    );
    final_blocks[remainder] = 0x80U;
    const std::size_t block_count = remainder > 55 ? 2 : 1;
    const auto bit_length = static_cast<std::uint64_t>(bytes.size()) * 8U;
    const auto length_offset = block_count * 64 - 8;
    for (std::size_t index = 0; index < 8; ++index) {
        final_blocks[length_offset + index] = static_cast<std::uint8_t>(
            bit_length >> static_cast<unsigned>((7 - index) * 8)
        );
    }
    for (std::size_t block = 0; block < block_count; ++block) {
        picosha2::detail::hash256_block(
            words.begin(),
            final_blocks.begin()
                + static_cast<std::ptrdiff_t>(block * 64),
            final_blocks.begin()
                + static_cast<std::ptrdiff_t>((block + 1) * 64)
        );
    }

    StateDigest output;
    std::size_t output_index = 0;
    for (const auto word : words) {
        for (int shift = 24; shift >= 0; shift -= 8) {
            output.bytes[output_index++] =
                static_cast<std::uint8_t>(word >> shift);
        }
    }
    return output;
}

std::string StateDigest::hex() const {
    constexpr char digits[] = "0123456789abcdef";
    std::string output;
    output.resize(bytes.size() * 2);
    for (std::size_t index = 0; index < bytes.size(); ++index) {
        output[index * 2] = digits[bytes[index] >> 4U];
        output[index * 2 + 1] = digits[bytes[index] & 0x0FU];
    }
    return output;
}

StateDigest state_digest(const RootState& state) {
    std::vector<std::uint8_t> scratch;
    return state_digest(state, scratch);
}

StateDigest state_digest(
    const RootState& state,
    std::vector<std::uint8_t>& scratch
) {
    DigestWriter writer(scratch);
    append_root(writer, state);
    return sha256_digest(writer.bytes());
}

}  // namespace macro_sim::core
