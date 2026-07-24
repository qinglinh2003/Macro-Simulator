#include <cassert>
#include <cstdint>
#include <utility>
#include <vector>

#include "macro_sim/core/slot_store.hpp"
#include "macro_sim/ids.hpp"

namespace {

struct Record final {
    std::uint64_t payload{0};
};

void test_generation_safe_reuse_and_rollback() {
    macro_sim::core::SlotStore<macro_sim::HouseholdId, Record> store;

    auto first_result = store.create(Record{10});
    auto second_result = store.create(Record{20});
    assert(first_result.ok());
    assert(second_result.ok());
    const auto first = *first_result.get_if();
    const auto second = *second_result.get_if();
    assert(first.id == macro_sim::HouseholdId(1));
    assert(second.id == macro_sim::HouseholdId(2));
    assert(store.get(first.handle)->payload == 10);

    const auto allocator_before_remove = store.allocator_state();
    auto removed_result = store.remove(first.id);
    assert(removed_result.ok());
    auto removed = std::move(*removed_result.get_if());
    assert(store.get(first.handle) == nullptr);
    assert(store.get(first.id) == nullptr);

    auto third_result = store.create(Record{30});
    assert(third_result.ok());
    const auto third = *third_result.get_if();
    assert(third.id == macro_sim::HouseholdId(3));
    assert(third.handle.index == first.handle.index);
    assert(third.handle.generation == first.handle.generation + 1);
    assert(store.get(first.handle) == nullptr);
    assert(store.get(third.handle)->payload == 30);

    std::vector<std::uint64_t> alive;
    store.for_each_alive(
        [&alive](macro_sim::HouseholdId id, const Record&) {
            alive.push_back(id.value());
        }
    );
    assert((alive == std::vector<std::uint64_t>{2, 3}));

    assert(store.rollback_create(third).ok());
    assert(store.rollback_remove(std::move(removed)).ok());
    assert(store.allocator_state() == allocator_before_remove);
    assert(store.alive_count() == 2);
    assert(store.get(first.id)->payload == 10);
    assert(store.get(second.id)->payload == 20);
}

}  // namespace

int main() {
    test_generation_safe_reuse_and_rollback();
    return 0;
}
