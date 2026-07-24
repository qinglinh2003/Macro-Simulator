#ifndef MACRO_SIM_CORE_SLOT_STORE_HPP
#define MACRO_SIM_CORE_SLOT_STORE_HPP

#include <compare>
#include <cstdint>
#include <limits>
#include <optional>
#include <utility>
#include <vector>

#include "macro_sim/error.hpp"

namespace macro_sim::core {

class CheckpointCodec;

struct SlotHandle final {
    std::uint32_t index{std::numeric_limits<std::uint32_t>::max()};
    std::uint32_t generation{std::numeric_limits<std::uint32_t>::max()};

    [[nodiscard]] constexpr bool valid() const noexcept {
        return index != std::numeric_limits<std::uint32_t>::max();
    }

    constexpr auto operator<=>(const SlotHandle&) const noexcept = default;
};

template <typename Id, typename Value>
class SlotStore final {
public:
    struct CreateReceipt final {
        Id id{};
        SlotHandle handle{};
        bool appended_slot{false};
    };

    struct RemoveReceipt final {
        Id id{};
        SlotHandle handle{};
        Value value;
    };

    struct AllocatorState final {
        std::uint64_t next_id{1};
        std::uint64_t next_sequence{1};
        std::vector<std::uint32_t> free_slots;

        bool operator==(const AllocatorState&) const = default;
    };

    struct Slot final {
        std::optional<Value> value;
        Id id{};
        std::uint32_t generation{0};
        std::uint64_t sequence{0};
    };

    [[nodiscard]] Result<CreateReceipt> create(Value value) {
        if (next_id_ == std::numeric_limits<std::uint64_t>::max()) {
            return Status(ErrorCode::out_of_range, "stable ID space exhausted");
        }
        if (next_sequence_ == std::numeric_limits<std::uint64_t>::max()) {
            return Status(
                ErrorCode::out_of_range,
                "stable iteration sequence exhausted"
            );
        }

        const auto id = Id(next_id_);
        ++next_id_;
        const auto sequence = next_sequence_;
        ++next_sequence_;

        std::uint32_t index = 0;
        bool appended = false;
        if (free_slots_.empty()) {
            if (slots_.size() >= std::numeric_limits<std::uint32_t>::max()) {
                --next_id_;
                --next_sequence_;
                return Status(ErrorCode::out_of_range, "slot space exhausted");
            }
            index = static_cast<std::uint32_t>(slots_.size());
            slots_.push_back(Slot{});
            appended = true;
        } else {
            index = free_slots_.back();
            free_slots_.pop_back();
        }

        auto& slot = slots_[index];
        slot.value.emplace(std::move(value));
        slot.id = id;
        slot.sequence = sequence;
        const SlotHandle handle{index, slot.generation};

        const auto id_index = static_cast<std::size_t>(id.value());
        if (id_to_handle_.size() <= id_index) {
            id_to_handle_.resize(id_index + 1);
        }
        id_to_handle_[id_index] = handle;
        iteration_order_.push_back(id);
        ++alive_count_;
        return CreateReceipt{id, handle, appended};
    }

    [[nodiscard]] Result<RemoveReceipt> remove(Id id) {
        const auto handle_result = resolve(id);
        if (!handle_result.ok()) {
            return handle_result.status();
        }
        const auto handle = *handle_result.get_if();
        auto& slot = slots_[handle.index];
        Value value = std::move(*slot.value);
        slot.value.reset();
        slot.id = Id{};
        slot.sequence = 0;
        ++slot.generation;
        id_to_handle_[static_cast<std::size_t>(id.value())] = SlotHandle{};
        free_slots_.push_back(handle.index);
        --alive_count_;
        return RemoveReceipt{id, handle, std::move(value)};
    }

    [[nodiscard]] Status rollback_create(const CreateReceipt& receipt) {
        if (next_id_ != receipt.id.value() + 1 || iteration_order_.empty()
            || iteration_order_.back() != receipt.id) {
            return Status(
                ErrorCode::invalid_transaction_state,
                "create rollback order is invalid"
            );
        }
        const auto resolved = resolve(receipt.id);
        if (!resolved.ok() || *resolved.get_if() != receipt.handle) {
            return Status(
                ErrorCode::invalid_transaction_state,
                "created slot no longer matches receipt"
            );
        }
        if (receipt.appended_slot
            && receipt.handle.index + 1 != slots_.size()) {
            return Status(
                ErrorCode::invalid_transaction_state,
                "appended slot is no longer last"
            );
        }

        auto& slot = slots_[receipt.handle.index];
        slot.value.reset();
        slot.id = Id{};
        slot.sequence = 0;
        id_to_handle_.pop_back();
        iteration_order_.pop_back();
        --next_id_;
        --next_sequence_;
        --alive_count_;

        if (receipt.appended_slot) {
            slots_.pop_back();
        } else {
            free_slots_.push_back(receipt.handle.index);
        }
        return Status::success();
    }

    [[nodiscard]] Status rollback_remove(RemoveReceipt receipt) {
        if (free_slots_.empty() || free_slots_.back() != receipt.handle.index) {
            return Status(
                ErrorCode::invalid_transaction_state,
                "remove rollback order is invalid"
            );
        }
        auto& slot = slots_[receipt.handle.index];
        if (slot.value.has_value()
            || slot.generation != receipt.handle.generation + 1) {
            return Status(
                ErrorCode::invalid_transaction_state,
                "removed slot no longer matches receipt"
            );
        }

        free_slots_.pop_back();
        slot.generation = receipt.handle.generation;
        slot.id = receipt.id;
        slot.value.emplace(std::move(receipt.value));
        const auto id_index = static_cast<std::size_t>(receipt.id.value());
        id_to_handle_[id_index] = receipt.handle;
        ++alive_count_;
        return Status::success();
    }

    [[nodiscard]] Result<SlotHandle> resolve(Id id) const noexcept {
        if (!id.valid()) {
            return Status(ErrorCode::invalid_argument, "invalid stable ID");
        }
        const auto index = static_cast<std::size_t>(id.value());
        if (index >= id_to_handle_.size() || !id_to_handle_[index].valid()) {
            return Status(ErrorCode::not_found, "stable ID is not alive");
        }
        return id_to_handle_[index];
    }

    [[nodiscard]] Value* get(Id id) noexcept {
        const auto handle = resolve(id);
        return handle.ok() ? get(*handle.get_if()) : nullptr;
    }

    [[nodiscard]] const Value* get(Id id) const noexcept {
        const auto handle = resolve(id);
        return handle.ok() ? get(*handle.get_if()) : nullptr;
    }

    [[nodiscard]] Value* get(SlotHandle handle) noexcept {
        if (handle.index >= slots_.size()) {
            return nullptr;
        }
        auto& slot = slots_[handle.index];
        if (slot.generation != handle.generation || !slot.value.has_value()) {
            return nullptr;
        }
        return &*slot.value;
    }

    [[nodiscard]] const Value* get(SlotHandle handle) const noexcept {
        if (handle.index >= slots_.size()) {
            return nullptr;
        }
        const auto& slot = slots_[handle.index];
        if (slot.generation != handle.generation || !slot.value.has_value()) {
            return nullptr;
        }
        return &*slot.value;
    }

    template <typename Function>
    void for_each_alive(Function&& function) {
        for (const auto id : iteration_order_) {
            if (auto* value = get(id); value != nullptr) {
                function(id, *value);
            }
        }
    }

    template <typename Function>
    void for_each_alive(Function&& function) const {
        for (const auto id : iteration_order_) {
            if (const auto* value = get(id); value != nullptr) {
                function(id, *value);
            }
        }
    }

    [[nodiscard]] std::size_t alive_count() const noexcept {
        return alive_count_;
    }

    [[nodiscard]] std::size_t slot_count() const noexcept {
        return slots_.size();
    }

    [[nodiscard]] const std::vector<Slot>& slots() const noexcept {
        return slots_;
    }

    [[nodiscard]] const std::vector<Id>& iteration_order() const noexcept {
        return iteration_order_;
    }

    [[nodiscard]] AllocatorState allocator_state() const {
        return AllocatorState{next_id_, next_sequence_, free_slots_};
    }

private:
    friend class CheckpointCodec;

    std::vector<Slot> slots_;
    std::vector<SlotHandle> id_to_handle_{SlotHandle{}};
    std::vector<std::uint32_t> free_slots_;
    std::vector<Id> iteration_order_;
    std::uint64_t next_id_{1};
    std::uint64_t next_sequence_{1};
    std::size_t alive_count_{0};
};

}  // namespace macro_sim::core

#endif
