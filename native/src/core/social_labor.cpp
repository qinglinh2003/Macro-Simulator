#include "macro_sim/core/social_labor.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>

namespace macro_sim::core {
namespace {

[[nodiscard]] bool finite(double value) noexcept { return std::isfinite(value); }

template <typename Value>
[[nodiscard]] std::uint64_t capacity_bytes(const std::vector<Value> &values) noexcept {
    return static_cast<std::uint64_t>(values.capacity()) * sizeof(Value);
}

constexpr double kDaysPerYear = 365.2425;

[[nodiscard]] double age_at(const PersonRecord &person,
                            std::int32_t day) noexcept {
    return std::max(
        0.0,
        static_cast<double>(day - person.birth_day) / kDaysPerYear
    );
}

[[nodiscard]] bool close_kin(const PersonRecord &left,
                             const PersonRecord &right) noexcept {
    if (left.mother == right.id || left.father == right.id ||
        right.mother == left.id || right.father == left.id) {
        return true;
    }
    return (left.mother.valid() && left.mother == right.mother) ||
           (left.father.valid() && left.father == right.father);
}

} // namespace

void RelationshipBook::ensure_person(PersonId person) {
    const auto size = static_cast<std::size_t>(person.value()) + 1U;
    if (active_union_by_person_.size() < size) {
        active_union_by_person_.resize(size);
        child_head_by_parent_.resize(size, 0U);
    }
}

Status RelationshipBook::append_child(PersonId parent, PersonId child) {
    if (child_links_.size() >=
        static_cast<std::size_t>(std::numeric_limits<std::uint32_t>::max() - 1U)) {
        return Status(ErrorCode::out_of_range, "child lineage space exhausted");
    }
    ensure_person(parent);
    const auto parent_index = static_cast<std::size_t>(parent.value());
    child_links_.push_back({child, child_head_by_parent_[parent_index]});
    child_head_by_parent_[parent_index] =
        static_cast<std::uint32_t>(child_links_.size());
    return Status::success();
}

UnionRecord *RelationshipBook::get(EventId event) noexcept {
    if (!event.valid() || event.value() == 0) {
        return nullptr;
    }
    const auto found = std::find_if(
        unions_.begin(), unions_.end(),
        [event](const UnionRecord &record) {
            return record.event == event;
        }
    );
    return found == unions_.end() ? nullptr : &*found;
}

const UnionRecord *RelationshipBook::get(EventId event) const noexcept {
    if (!event.valid() || event.value() == 0) {
        return nullptr;
    }
    const auto found = std::find_if(
        unions_.begin(), unions_.end(),
        [event](const UnionRecord &record) {
            return record.event == event;
        }
    );
    return found == unions_.end() ? nullptr : &*found;
}

Status RelationshipBook::marry(PersonStore &persons, EventId event,
                               PersonId first, PersonId second,
                               std::int32_t day) {
    auto *left = persons.get(first);
    auto *right = persons.get(second);
    if (!event.valid() || event.value() == 0 || first == second ||
        left == nullptr || right == nullptr || !left->alive ||
        !right->alive || left->partner.valid() ||
        right->partner.valid() || get(event) != nullptr) {
        return Status(ErrorCode::invalid_argument,
                      "union creation is invalid");
    }
    ensure_person(first);
    ensure_person(second);
    if (active_union(first).valid() ||
        active_union(second).valid()) {
        return Status(ErrorCode::already_exists,
                      "person already has an active union");
    }
    unions_.push_back({
        event,
        first,
        second,
        left->household,
        right->household,
        day,
        -1,
        UnionEndKind::active,
        true,
    });
    active_union_by_person_[
        static_cast<std::size_t>(first.value())] = event;
    active_union_by_person_[
        static_cast<std::size_t>(second.value())] = event;
    left->partner = second;
    right->partner = first;
    left->marriage_start_day = day;
    right->marriage_start_day = day;
    ++left->marriage_count;
    ++right->marriage_count;
    return Status::success();
}

Status RelationshipBook::divorce(PersonStore &persons,
                                 PersonId person,
                                 std::int32_t day) {
    const auto event = active_union(person);
    auto *record = get(event);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found,
                      "active union is absent");
    }
    auto *first = persons.get(record->first);
    auto *second = persons.get(record->second);
    if (first == nullptr || second == nullptr ||
        first->partner != second->id ||
        second->partner != first->id) {
        return Status(ErrorCode::invariant_violation,
                      "active union projection is inconsistent");
    }
    first->partner = PersonId{};
    second->partner = PersonId{};
    first->marriage_start_day = -1;
    second->marriage_start_day = -1;
    first->last_divorce_day = day;
    second->last_divorce_day = day;
    active_union_by_person_[
        static_cast<std::size_t>(first->id.value())] = EventId{};
    active_union_by_person_[
        static_cast<std::size_t>(second->id.value())] = EventId{};
    record->active = false;
    record->end_day = day;
    record->end_kind = UnionEndKind::divorce;
    return Status::success();
}

Status RelationshipBook::widow(PersonStore &persons,
                               PersonId deceased,
                               std::int32_t day) {
    const auto event = active_union(deceased);
    if (!event.valid()) {
        return Status::success();
    }
    auto *record = get(event);
    auto *dead = persons.get(deceased);
    if (record == nullptr || !record->active || dead == nullptr) {
        return Status(ErrorCode::invariant_violation,
                      "widowhood union is inconsistent");
    }
    const auto survivor_id =
        record->first == deceased ? record->second : record->first;
    auto *survivor = persons.get(survivor_id);
    if (survivor == nullptr || !survivor->alive ||
        dead->partner != survivor_id ||
        survivor->partner != deceased) {
        return Status(ErrorCode::invariant_violation,
                      "widowhood partner projection is inconsistent");
    }
    dead->partner = PersonId{};
    survivor->partner = PersonId{};
    dead->marriage_start_day = -1;
    survivor->marriage_start_day = -1;
    dead->last_widowed_day = day;
    survivor->last_widowed_day = day;
    active_union_by_person_[
        static_cast<std::size_t>(deceased.value())] = EventId{};
    active_union_by_person_[
        static_cast<std::size_t>(survivor_id.value())] = EventId{};
    record->active = false;
    record->end_day = day;
    record->end_kind = UnionEndKind::widowhood;
    return Status::success();
}

Status RelationshipBook::register_birth(const PersonStore &persons,
                                        PersonId child) {
    const auto *record = persons.get(child);
    if (record == nullptr) {
        return Status(ErrorCode::not_found, "child is absent");
    }
    for (const auto parent :
         std::array{record->mother, record->father}) {
        if (!parent.valid()) {
            continue;
        }
        if (!persons.contains(parent)) {
            return Status(ErrorCode::invariant_violation,
                          "child references an absent parent");
        }
        ensure_person(parent);
        const auto children = this->children(parent);
        if (std::find(children.begin(), children.end(), child) !=
            children.end()) {
            return Status(ErrorCode::already_exists,
                          "child lineage is already registered");
        }
        const auto status = append_child(parent, child);
        if (!status.ok()) {
            return status;
        }
    }
    ensure_person(child);
    return Status::success();
}

EventId
RelationshipBook::active_union(PersonId person) const noexcept {
    if (!person.valid() || person.value() == 0 ||
        person.value() >= active_union_by_person_.size()) {
        return EventId{};
    }
    return active_union_by_person_[
        static_cast<std::size_t>(person.value())];
}

std::span<const PersonId>
RelationshipBook::children(PersonId parent) const {
    child_query_.clear();
    if (!parent.valid() || parent.value() == 0 ||
        parent.value() >= child_head_by_parent_.size()) {
        return {};
    }
    auto link =
        child_head_by_parent_[static_cast<std::size_t>(parent.value())];
    while (link != 0U) {
        const auto &record =
            child_links_[static_cast<std::size_t>(link - 1U)];
        child_query_.push_back(record.child);
        link = record.previous;
    }
    return child_query_;
}

const std::vector<UnionRecord> &
RelationshipBook::unions() const noexcept {
    return unions_;
}

std::uint64_t RelationshipBook::retained_bytes() const noexcept {
    return capacity_bytes(unions_) + capacity_bytes(active_union_by_person_) +
           capacity_bytes(child_head_by_parent_) + capacity_bytes(child_links_) +
           capacity_bytes(child_query_);
}

Status RelationshipBook::replace_unions(
    const PersonStore &persons,
    std::vector<UnionRecord> unions
) {
    unions_ = std::move(unions);
    active_union_by_person_.assign(
        persons.next_id(), EventId{}
    );
    child_head_by_parent_.assign(persons.next_id(), 0U);
    child_links_.clear();
    child_query_.clear();
    for (const auto &record : unions_) {
        if (!record.active) {
            continue;
        }
        ensure_person(record.first);
        ensure_person(record.second);
        auto &first = active_union_by_person_[
            static_cast<std::size_t>(record.first.value())];
        auto &second = active_union_by_person_[
            static_cast<std::size_t>(record.second.value())];
        if (first.valid() || second.valid()) {
            return Status(ErrorCode::corrupt_input,
                          "relationship checkpoint has duplicate unions");
        }
        first = record.event;
        second = record.event;
    }
    for (std::size_t index = 1;
         index < persons.records().size(); ++index) {
        const auto child = PersonId(index);
        const auto *record = persons.get(child);
        for (const auto parent :
             std::array{record->mother, record->father}) {
            if (!parent.valid()) {
                continue;
            }
            if (!persons.contains(parent)) {
                return Status(
                    ErrorCode::corrupt_input,
                    "relationship checkpoint parent is absent"
                );
            }
            const auto status = append_child(parent, child);
            if (!status.ok()) {
                return status;
            }
        }
    }
    return validate(persons);
}

Status RelationshipBook::validate(
    const PersonStore &persons
) const {
    std::vector<std::uint8_t> active_seen(persons.next_id(), 0U);
    for (const auto &record : unions_) {
        const auto *first = persons.get(record.first);
        const auto *second = persons.get(record.second);
        if (!record.event.valid() || record.event.value() == 0 ||
            first == nullptr || second == nullptr ||
            record.first == record.second) {
            return Status(ErrorCode::invariant_violation,
                          "union record is invalid");
        }
        if (!record.active) {
            if (record.end_day < record.start_day ||
                record.end_kind == UnionEndKind::active) {
                return Status(ErrorCode::invariant_violation,
                              "closed union is inconsistent");
            }
            continue;
        }
        if (!first->alive || !second->alive ||
            first->partner != second->id ||
            second->partner != first->id ||
            active_union(first->id) != record.event ||
            active_union(second->id) != record.event ||
            active_seen[
                static_cast<std::size_t>(first->id.value())] != 0U ||
            active_seen[
                static_cast<std::size_t>(second->id.value())] != 0U) {
            return Status(ErrorCode::invariant_violation,
                          "active union is inconsistent");
        }
        active_seen[
            static_cast<std::size_t>(first->id.value())] = 1U;
        active_seen[
            static_cast<std::size_t>(second->id.value())] = 1U;
    }
    for (const auto person_id : persons.alive_ids()) {
        const auto *person = persons.get(person_id);
        const bool partnered = person->partner.valid();
        if (partnered != active_union(person_id).valid()) {
            return Status(ErrorCode::invariant_violation,
                          "person union projection is inconsistent");
        }
        if (person->mother == person_id ||
            person->father == person_id ||
            person->guardian == person_id ||
            (person->mother.valid() &&
             !persons.contains(person->mother)) ||
            (person->father.valid() &&
             !persons.contains(person->father)) ||
            (person->guardian.valid() &&
             !persons.alive(person->guardian))) {
            return Status(
                ErrorCode::invariant_violation,
                "person family reference is inconsistent"
            );
        }
        for (const auto parent :
             std::array{person->mother, person->father}) {
            if (!parent.valid()) {
                continue;
            }
            const auto indexed_children = children(parent);
            if (std::find(
                    indexed_children.begin(),
                    indexed_children.end(), person_id
                ) == indexed_children.end()) {
                return Status(
                    ErrorCode::invariant_violation,
                    "person lineage projection is incomplete"
                );
            }
        }
    }
    for (std::size_t parent_index = 1;
         parent_index < child_head_by_parent_.size(); ++parent_index) {
        std::vector<PersonId> seen;
        for (const auto child : children(PersonId(parent_index))) {
            const auto *record = persons.get(child);
            const auto parent = PersonId(parent_index);
            if (record == nullptr ||
                (record->mother != parent &&
                 record->father != parent) ||
                std::find(seen.begin(), seen.end(), child) !=
                    seen.end()) {
                return Status(ErrorCode::invariant_violation,
                              "lineage index is inconsistent");
            }
            seen.push_back(child);
        }
    }
    return Status::success();
}

Result<std::vector<MarriageMatch>>
exact_marriage_matches(const PersonStore &persons,
                       const HouseholdMembershipBook &membership,
                       const MarriageRules &rules,
                       std::int32_t day) {
    const std::array values{
        rules.preferred_age_gap,
        rules.age_gap_penalty,
        rules.assortativity,
    };
    if (rules.minimum_age == 0 ||
        rules.maximum_age < rules.minimum_age ||
        rules.maximum_age_gap >
            rules.maximum_age - rules.minimum_age ||
        !std::all_of(values.begin(), values.end(), finite) ||
        rules.age_gap_penalty < 0.0 ||
        rules.assortativity < 0.0) {
        return Status(ErrorCode::invalid_argument,
                      "marriage rules are invalid");
    }
    std::vector<PersonId> first_pool;
    std::vector<PersonId> second_pool;
    for (const auto person_id : persons.alive_ids()) {
        const auto *person = persons.get(person_id);
        const double age = age_at(*person, day);
        if (person->partner.valid() ||
            age < static_cast<double>(rules.minimum_age) ||
            age > static_cast<double>(rules.maximum_age)) {
            continue;
        }
        (person->sex == PersonSex::female ? first_pool : second_pool)
            .push_back(person_id);
    }
    std::sort(first_pool.begin(), first_pool.end());
    std::sort(second_pool.begin(), second_pool.end());

    struct Candidate final {
        PersonId id{};
        double age{0.0};
        double log_efficiency{0.0};
    };
    struct SearchNode final {
        Candidate candidate{};
        std::int32_t left{-1};
        std::int32_t right{-1};
        std::int32_t parent{-1};
        double minimum_age{0.0};
        double maximum_age{0.0};
        double minimum_log_efficiency{0.0};
        double maximum_log_efficiency{0.0};
        std::uint64_t minimum_active_id{
            std::numeric_limits<std::uint64_t>::max()
        };
        std::size_t active_count{1};
        bool active{true};
    };

    std::vector<Candidate> candidates;
    candidates.reserve(second_pool.size());
    for (const auto second_id : second_pool) {
        const auto *second = persons.get(second_id);
        candidates.push_back(
            {second_id, age_at(*second, day),
             std::log(second->efficiency)}
        );
    }
    std::sort(
        candidates.begin(), candidates.end(),
        [](const Candidate &left, const Candidate &right) {
            return left.age < right.age ||
                   (left.age == right.age &&
                    left.id < right.id);
        }
    );
    std::vector<SearchNode> search;
    search.reserve(candidates.size());
    const auto refresh = [&search](std::int32_t index) {
        auto &node = search[static_cast<std::size_t>(index)];
        node.active_count = node.active ? 1U : 0U;
        node.minimum_active_id =
            node.active
                ? node.candidate.id.value()
                : std::numeric_limits<std::uint64_t>::max();
        for (const auto child_index :
             std::array{node.left, node.right}) {
            if (child_index < 0) {
                continue;
            }
            const auto &child =
                search[static_cast<std::size_t>(child_index)];
            node.active_count += child.active_count;
            node.minimum_active_id =
                std::min(
                    node.minimum_active_id,
                    child.minimum_active_id
                );
        }
    };
    const auto build_search =
        [&](auto &&self, std::size_t begin, std::size_t end,
            std::int32_t parent) -> std::int32_t {
            if (begin == end) {
                return std::int32_t{-1};
            }
            const auto middle = begin + (end - begin) / 2U;
            const auto node_index =
                static_cast<std::int32_t>(search.size());
            SearchNode node;
            node.candidate = candidates[middle];
            node.parent = parent;
            node.minimum_age = node.candidate.age;
            node.maximum_age = node.candidate.age;
            node.minimum_log_efficiency =
                node.candidate.log_efficiency;
            node.maximum_log_efficiency =
                node.candidate.log_efficiency;
            node.minimum_active_id = node.candidate.id.value();
            search.push_back(node);
            const auto left = self(
                self, begin, middle, node_index
            );
            const auto right = self(
                self, middle + 1U, end, node_index
            );
            auto &stored =
                search[static_cast<std::size_t>(node_index)];
            stored.left = left;
            stored.right = right;
            for (const auto child_index :
                 std::array{left, right}) {
                if (child_index < 0) {
                    continue;
                }
                const auto &child =
                    search[static_cast<std::size_t>(child_index)];
                stored.minimum_age = std::min(
                    stored.minimum_age, child.minimum_age
                );
                stored.maximum_age = std::max(
                    stored.maximum_age, child.maximum_age
                );
                stored.minimum_log_efficiency = std::min(
                    stored.minimum_log_efficiency,
                    child.minimum_log_efficiency
                );
                stored.maximum_log_efficiency = std::max(
                    stored.maximum_log_efficiency,
                    child.maximum_log_efficiency
                );
            }
            refresh(node_index);
            return node_index;
        };
    const auto root = build_search(
        build_search, 0, candidates.size(), -1
    );

    std::vector<MarriageMatch> result;
    result.reserve(std::min(first_pool.size(), second_pool.size()));
    for (const auto first_id : first_pool) {
        const auto *first = persons.get(first_id);
        const double first_age = age_at(*first, day);
        const double first_log_efficiency =
            std::log(first->efficiency);
        const double target_age =
            first_age + rules.preferred_age_gap;
        const double minimum_allowed_age =
            first_age -
            static_cast<double>(rules.maximum_age_gap);
        const double maximum_allowed_age =
            first_age +
            static_cast<double>(rules.maximum_age_gap);
        MarriageMatch best;
        best.score = std::numeric_limits<double>::infinity();
        std::int32_t best_node{-1};
        const auto lower_bound =
            [&](const SearchNode &node) {
                const double lower_age =
                    std::max(
                        node.minimum_age,
                        minimum_allowed_age
                    );
                const double upper_age =
                    std::min(
                        node.maximum_age,
                        maximum_allowed_age
                    );
                if (lower_age > upper_age ||
                    node.active_count == 0) {
                    return std::numeric_limits<double>::infinity();
                }
                const double age_distance =
                    target_age < lower_age
                        ? lower_age - target_age
                        : (target_age > upper_age
                               ? target_age - upper_age
                               : 0.0);
                const double efficiency_distance =
                    first_log_efficiency <
                            node.minimum_log_efficiency
                        ? node.minimum_log_efficiency -
                              first_log_efficiency
                        : (first_log_efficiency >
                                   node.maximum_log_efficiency
                               ? first_log_efficiency -
                                     node.maximum_log_efficiency
                               : 0.0);
                return rules.age_gap_penalty * age_distance +
                       rules.assortativity * efficiency_distance;
            };
        const auto search_nearest =
            [&](auto &&self, std::int32_t node_index) -> void {
            if (node_index < 0) {
                return;
            }
            const auto &node =
                search[static_cast<std::size_t>(node_index)];
            const double bound = lower_bound(node);
            if (bound > best.score ||
                (bound == best.score && best.second.valid() &&
                 node.minimum_active_id >= best.second.value())) {
                return;
            }
            if (node.active &&
                node.candidate.age >= minimum_allowed_age &&
                node.candidate.age <= maximum_allowed_age) {
                const auto second_id = node.candidate.id;
                const auto *second = persons.get(second_id);
                if ((!rules.forbid_same_household ||
                     membership.household_of(first_id) !=
                         membership.household_of(second_id)) &&
                    (!rules.forbid_close_kin ||
                     !close_kin(*first, *second))) {
                    const double score =
                        rules.age_gap_penalty *
                            std::abs(
                                node.candidate.age - target_age
                            ) +
                        rules.assortativity *
                            std::abs(
                                node.candidate.log_efficiency -
                                first_log_efficiency
                            );
                    if (score < best.score ||
                        (score == best.score &&
                         second_id < best.second)) {
                        best = {first_id, second_id, score};
                        best_node = node_index;
                    }
                }
            }
            const auto left = node.left;
            const auto right = node.right;
            const double left_bound =
                left < 0
                    ? std::numeric_limits<double>::infinity()
                    : lower_bound(
                          search[static_cast<std::size_t>(left)]
                      );
            const double right_bound =
                right < 0
                    ? std::numeric_limits<double>::infinity()
                    : lower_bound(
                          search[static_cast<std::size_t>(right)]
                      );
            if (left_bound <= right_bound) {
                self(self, left);
                self(self, right);
            } else {
                self(self, right);
                self(self, left);
            }
        };
        search_nearest(search_nearest, root);
        if (best.second.valid()) {
            result.push_back(best);
            search[static_cast<std::size_t>(best_node)].active = false;
            for (auto node_index = best_node;
                 node_index >= 0;
                 node_index =
                     search[static_cast<std::size_t>(node_index)]
                         .parent) {
                refresh(node_index);
            }
        }
    }
    return result;
}

void EmploymentBook::ensure_person(PersonId person) {
    const auto size = static_cast<std::size_t>(person.value()) + 1U;
    if (primary_by_person_.size() < size) {
        primary_by_person_.resize(size);
        secondary_by_person_.resize(size);
    }
}

void EmploymentBook::ensure_firm(FirmId firm) {
    const auto size = static_cast<std::size_t>(firm.value()) + 1U;
    if (roster_by_firm_.size() < size) {
        roster_by_firm_.resize(size);
    }
}

Result<JobId> EmploymentBook::hire(PersonId person, FirmId firm,
                                   std::int32_t day, double wage,
                                   double hours, bool secondary) {
    if (!person.valid() || person.value() == 0 || !firm.valid() ||
        firm.value() == 0 || !finite(wage) || wage <= 0.0 ||
        !finite(hours) || hours <= 0.0 || hours > 1.0 ||
        next_id_ > static_cast<std::uint64_t>(JobId::max_valid_value())) {
        return Status(ErrorCode::invalid_argument,
                      "employment contract is invalid");
    }
    ensure_person(person);
    ensure_firm(firm);
    auto &slot = secondary
                     ? secondary_by_person_[
                           static_cast<std::size_t>(person.value())]
                     : primary_by_person_[
                           static_cast<std::size_t>(person.value())];
    if (slot.valid()) {
        return Status(ErrorCode::already_exists,
                      "person already holds this job class");
    }
    const auto other =
        secondary
            ? primary_by_person_[static_cast<std::size_t>(person.value())]
            : secondary_by_person_[static_cast<std::size_t>(person.value())];
    if (other.valid()) {
        const auto *other_record = get(other);
        if (other_record != nullptr && other_record->firm == firm) {
            return Status(ErrorCode::contract_violation,
                          "person cannot hold two jobs at one firm");
        }
        if (active_hours(person) + hours > 1.0 + 1.0e-12) {
            return Status(ErrorCode::contract_violation,
                          "person job hours exceed capacity");
        }
    }
    const auto id = JobId(static_cast<JobId::rep_type>(next_id_++));
    jobs_.push_back({
        id,
        person,
        firm,
        day,
        -1,
        -1,
        wage,
        hours,
        secondary,
        false,
        true,
        SeparationKind::churn,
    });
    slot = id;
    auto &firm_roster =
        roster_by_firm_[static_cast<std::size_t>(firm.value())];
    roster_position_by_job_.push_back(
        static_cast<std::uint32_t>(firm_roster.size()));
    firm_roster.push_back(id);
    ++active_count_;
    return id;
}

Status EmploymentBook::separate(JobId job, std::int32_t day,
                                SeparationKind kind) {
    auto *record = get(job);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found,
                      "active employment contract is absent");
    }
    const auto index = static_cast<std::size_t>(job.value());
    const auto position =
        static_cast<std::size_t>(roster_position_by_job_[index]);
    auto &firm_roster =
        roster_by_firm_[static_cast<std::size_t>(record->firm.value())];
    if (position == kNoRoster || position >= firm_roster.size() ||
        firm_roster[position] != job) {
        return Status(ErrorCode::invariant_violation,
                      "employment roster index is inconsistent");
    }
    const auto moved = firm_roster.back();
    firm_roster[position] = moved;
    firm_roster.pop_back();
    if (moved != job) {
        roster_position_by_job_[
            static_cast<std::size_t>(moved.value())] =
            static_cast<std::uint32_t>(position);
    }
    roster_position_by_job_[index] = kNoRoster;
    auto &slot =
        record->secondary
            ? secondary_by_person_[
                  static_cast<std::size_t>(record->person.value())]
            : primary_by_person_[
                  static_cast<std::size_t>(record->person.value())];
    if (slot != job) {
        return Status(ErrorCode::invariant_violation,
                      "employment person index is inconsistent");
    }
    slot = JobId{};
    if (!record->secondary) {
        auto &secondary =
            secondary_by_person_[
                static_cast<std::size_t>(record->person.value())];
        if (secondary.valid()) {
            auto *replacement = get(secondary);
            if (replacement == nullptr || !replacement->active ||
                !replacement->secondary) {
                return Status(
                    ErrorCode::invariant_violation,
                    "secondary employment index is inconsistent"
                );
            }
            slot = secondary;
            secondary = JobId{};
            replacement->secondary = false;
        }
    }
    if (record->suspended) {
        --suspended_count_;
    }
    record->active = false;
    record->suspended = false;
    record->separation_day = day;
    record->separation_kind = kind;
    --active_count_;
    return Status::success();
}

Status EmploymentBook::suspend(JobId job, std::int32_t day) {
    auto *record = get(job);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found,
                      "active employment contract is absent");
    }
    if (record->suspended) {
        return Status(ErrorCode::already_exists,
                      "employment contract is already suspended");
    }
    record->suspended = true;
    record->suspension_day = day;
    ++suspended_count_;
    return Status::success();
}

Status EmploymentBook::recall(JobId job) {
    auto *record = get(job);
    if (record == nullptr || !record->active || !record->suspended) {
        return Status(ErrorCode::not_found,
                      "suspended employment contract is absent");
    }
    record->suspended = false;
    record->suspension_day = -1;
    --suspended_count_;
    return Status::success();
}

Status EmploymentBook::set_hours(JobId job, double hours) {
    auto *record = get(job);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found,
                      "active employment contract is absent");
    }
    if (!finite(hours) || hours <= 0.0 || hours > 1.0) {
        return Status(ErrorCode::invalid_argument,
                      "employment hours are invalid");
    }
    const double other_hours =
        active_hours(record->person) -
        (record->suspended ? 0.0 : record->hours);
    if (other_hours + hours > 1.0 + 1.0e-12) {
        return Status(ErrorCode::contract_violation,
                      "person job hours exceed capacity");
    }
    record->hours = hours;
    return Status::success();
}

Status EmploymentBook::set_wage(JobId job, double wage) {
    auto *record = get(job);
    if (record == nullptr || !record->active) {
        return Status(ErrorCode::not_found,
                      "active employment contract is absent");
    }
    if (!finite(wage) || wage <= 0.0) {
        return Status(ErrorCode::invalid_argument,
                      "employment wage is invalid");
    }
    record->wage = wage;
    return Status::success();
}

Status EmploymentBook::promote_secondary(PersonId person) {
    ensure_person(person);
    auto &primary =
        primary_by_person_[
            static_cast<std::size_t>(person.value())];
    auto &secondary =
        secondary_by_person_[
            static_cast<std::size_t>(person.value())];
    if (primary.valid() || !secondary.valid()) {
        return Status(
            ErrorCode::contract_violation,
            "secondary employment cannot be promoted"
        );
    }
    auto *record = get(secondary);
    if (record == nullptr || !record->active ||
        !record->secondary) {
        return Status(
            ErrorCode::invariant_violation,
            "secondary employment index is inconsistent"
        );
    }
    primary = secondary;
    secondary = JobId{};
    record->secondary = false;
    return Status::success();
}

JobRecord *EmploymentBook::get(JobId id) noexcept {
    if (!id.valid() || id.value() == 0 || id.value() >= jobs_.size()) {
        return nullptr;
    }
    return &jobs_[static_cast<std::size_t>(id.value())];
}

const JobRecord *EmploymentBook::get(JobId id) const noexcept {
    if (!id.valid() || id.value() == 0 || id.value() >= jobs_.size()) {
        return nullptr;
    }
    return &jobs_[static_cast<std::size_t>(id.value())];
}

JobId EmploymentBook::primary_job(PersonId person) const noexcept {
    if (!person.valid() || person.value() == 0 ||
        person.value() >= primary_by_person_.size()) {
        return JobId{};
    }
    return primary_by_person_[
        static_cast<std::size_t>(person.value())];
}

JobId EmploymentBook::secondary_job(PersonId person) const noexcept {
    if (!person.valid() || person.value() == 0 ||
        person.value() >= secondary_by_person_.size()) {
        return JobId{};
    }
    return secondary_by_person_[
        static_cast<std::size_t>(person.value())];
}

std::span<const JobId>
EmploymentBook::roster(FirmId firm) const noexcept {
    if (!firm.valid() || firm.value() == 0 ||
        firm.value() >= roster_by_firm_.size()) {
        return {};
    }
    return roster_by_firm_[
        static_cast<std::size_t>(firm.value())];
}

const std::vector<std::vector<JobId>> &
EmploymentBook::firm_rosters() const noexcept {
    return roster_by_firm_;
}

const std::vector<JobRecord> &EmploymentBook::records() const noexcept {
    return jobs_;
}

Status EmploymentBook::replace_records(
    std::vector<JobRecord> records
) {
    if (records.empty()) {
        return Status(ErrorCode::corrupt_input,
                      "employment checkpoint records are empty");
    }
    jobs_ = std::move(records);
    primary_by_person_.assign(1, JobId{});
    secondary_by_person_.assign(1, JobId{});
    roster_by_firm_.assign(1, std::vector<JobId>{});
    roster_position_by_job_.assign(jobs_.size(), kNoRoster);
    active_count_ = 0;
    suspended_count_ = 0;
    for (std::size_t index = 1; index < jobs_.size(); ++index) {
        auto &job = jobs_[index];
        if (job.id != JobId(index)) {
            return Status(ErrorCode::corrupt_input,
                          "employment checkpoint identity is invalid");
        }
        if (!job.active) {
            continue;
        }
        ensure_person(job.person);
        ensure_firm(job.firm);
        auto &slot =
            job.secondary
                ? secondary_by_person_[
                      static_cast<std::size_t>(job.person.value())]
                : primary_by_person_[
                      static_cast<std::size_t>(job.person.value())];
        if (slot.valid()) {
            return Status(ErrorCode::corrupt_input,
                          "employment checkpoint has duplicate jobs");
        }
        slot = job.id;
        auto &firm_roster =
            roster_by_firm_[
                static_cast<std::size_t>(job.firm.value())];
        roster_position_by_job_[index] =
            static_cast<std::uint32_t>(firm_roster.size());
        firm_roster.push_back(job.id);
        ++active_count_;
        suspended_count_ += job.suspended ? 1U : 0U;
    }
    next_id_ = jobs_.size();
    return Status::success();
}

Status EmploymentBook::restore_firm_rosters(
    std::vector<std::vector<JobId>> rosters
) {
    if (rosters.empty() || !rosters.front().empty()) {
        return Status(ErrorCode::corrupt_input,
                      "employment checkpoint firm rosters are invalid");
    }
    std::vector<bool> seen(jobs_.size(), false);
    std::vector<std::uint32_t> positions(jobs_.size(), kNoRoster);
    for (std::size_t firm_index = 1; firm_index < rosters.size(); ++firm_index) {
        const auto &firm_roster = rosters[firm_index];
        if (firm_roster.size() >= std::numeric_limits<std::uint32_t>::max()) {
            return Status(ErrorCode::out_of_range,
                          "employment checkpoint roster exceeds compact position range");
        }
        for (std::size_t position = 0; position < firm_roster.size(); ++position) {
            const auto job_id = firm_roster[position];
            const auto job_index = static_cast<std::size_t>(job_id.value());
            if (!job_id.valid() || job_index == 0 || job_index >= jobs_.size() ||
                seen[job_index]) {
                return Status(ErrorCode::corrupt_input,
                              "employment checkpoint roster identity is invalid");
            }
            const auto &job = jobs_[job_index];
            if (!job.active || job.firm.value() != firm_index) {
                return Status(ErrorCode::corrupt_input,
                              "employment checkpoint roster membership is invalid");
            }
            seen[job_index] = true;
            positions[job_index] = static_cast<std::uint32_t>(position);
        }
    }
    for (std::size_t index = 1; index < jobs_.size(); ++index) {
        if (jobs_[index].active != seen[index]) {
            return Status(ErrorCode::corrupt_input,
                          "employment checkpoint roster coverage is invalid");
        }
    }
    roster_by_firm_ = std::move(rosters);
    roster_position_by_job_ = std::move(positions);
    return Status::success();
}

std::uint64_t EmploymentBook::next_id() const noexcept {
    return next_id_;
}

std::size_t EmploymentBook::active_count() const noexcept {
    return active_count_;
}

std::size_t EmploymentBook::suspended_count() const noexcept {
    return suspended_count_;
}

Status EmploymentBook::compact_inactive() {
    if (jobs_.empty()) {
        return Status(ErrorCode::invariant_violation,
                      "employment store has no sentinel record");
    }
    std::size_t write = 1U;
    for (std::size_t read = 1U; read < jobs_.size(); ++read) {
        if (!jobs_[read].active) {
            continue;
        }
        if (write != read) {
            jobs_[write] = std::move(jobs_[read]);
        }
        jobs_[write].id = JobId(write);
        ++write;
    }
    jobs_.resize(write);

    std::fill(primary_by_person_.begin(), primary_by_person_.end(), JobId{});
    std::fill(secondary_by_person_.begin(), secondary_by_person_.end(), JobId{});
    for (auto &roster : roster_by_firm_) {
        roster.clear();
    }
    roster_position_by_job_.assign(jobs_.size(), kNoRoster);
    active_count_ = 0U;
    suspended_count_ = 0U;
    for (std::size_t index = 1U; index < jobs_.size(); ++index) {
        auto &job = jobs_[index];
        ensure_person(job.person);
        ensure_firm(job.firm);
        auto &person_slot =
            job.secondary
                ? secondary_by_person_[static_cast<std::size_t>(job.person.value())]
                : primary_by_person_[static_cast<std::size_t>(job.person.value())];
        if (person_slot.valid()) {
            return Status(ErrorCode::invariant_violation,
                          "employment compaction found duplicate jobs");
        }
        person_slot = job.id;
        auto &firm_roster = roster_by_firm_[static_cast<std::size_t>(job.firm.value())];
        if (firm_roster.size() >= std::numeric_limits<std::uint32_t>::max()) {
            return Status(ErrorCode::out_of_range,
                          "employment roster exceeds compact position range");
        }
        roster_position_by_job_[index] = static_cast<std::uint32_t>(firm_roster.size());
        firm_roster.push_back(job.id);
        ++active_count_;
        suspended_count_ += job.suspended ? 1U : 0U;
    }
    next_id_ = jobs_.size();
    return Status::success();
}

std::uint64_t EmploymentBook::retained_bytes() const noexcept {
    std::uint64_t bytes = capacity_bytes(jobs_) + capacity_bytes(primary_by_person_) +
                          capacity_bytes(secondary_by_person_) +
                          capacity_bytes(roster_by_firm_) +
                          capacity_bytes(roster_position_by_job_);
    for (const auto &roster : roster_by_firm_) {
        bytes += capacity_bytes(roster);
    }
    return bytes;
}

double EmploymentBook::active_hours(PersonId person) const noexcept {
    double result = 0.0;
    for (const auto job :
         std::array{primary_job(person), secondary_job(person)}) {
        const auto *record = get(job);
        if (record != nullptr && record->active && !record->suspended) {
            result += record->hours;
        }
    }
    return result;
}

double EmploymentBook::active_hours(FirmId firm) const noexcept {
    double result = 0.0;
    for (const auto job : roster(firm)) {
        const auto *record = get(job);
        if (record != nullptr && record->active && !record->suspended) {
            result += record->hours;
        }
    }
    return result;
}

Status EmploymentBook::validate(const PersonStore &persons,
                                const RootState &state,
                                double tolerance) const {
    if (jobs_.empty() || roster_position_by_job_.size() != jobs_.size() ||
        next_id_ != jobs_.size()) {
        return Status(ErrorCode::invariant_violation,
                      "employment store dimensions are inconsistent");
    }
    std::vector<std::uint8_t> roster_seen(jobs_.size(), 0U);
    std::size_t active = 0;
    std::size_t suspended = 0;
    for (std::size_t firm_index = 1;
         firm_index < roster_by_firm_.size(); ++firm_index) {
        const auto firm = FirmId(firm_index);
        if (!roster_by_firm_[firm_index].empty() &&
            state.firms.get(firm) == nullptr) {
            return Status(ErrorCode::invariant_violation,
                          "employment roster references an absent firm");
        }
        for (std::size_t position = 0;
             position < roster_by_firm_[firm_index].size(); ++position) {
            const auto job_id = roster_by_firm_[firm_index][position];
            const auto *job = get(job_id);
            if (job == nullptr || !job->active || job->firm != firm ||
                roster_position_by_job_[
                    static_cast<std::size_t>(job_id.value())] != position ||
                roster_seen[
                    static_cast<std::size_t>(job_id.value())] != 0U) {
                return Status(ErrorCode::invariant_violation,
                              "employment roster is inconsistent");
            }
            roster_seen[
                static_cast<std::size_t>(job_id.value())] = 1U;
        }
    }
    for (std::size_t index = 1; index < jobs_.size(); ++index) {
        const auto &job = jobs_[index];
        if (job.id.value() != index || !finite(job.wage) ||
            job.wage <= 0.0 || !finite(job.hours) ||
            job.hours <= 0.0 || job.hours > 1.0 + tolerance) {
            return Status(ErrorCode::invariant_violation,
                          "employment contract is invalid");
        }
        if (!job.active) {
            if (job.separation_day < job.hire_day ||
                roster_seen[index] != 0U ||
                roster_position_by_job_[index] != kNoRoster) {
                return Status(ErrorCode::invariant_violation,
                              "separated employment contract is inconsistent");
            }
            continue;
        }
        ++active;
        suspended += job.suspended ? 1U : 0U;
        const auto expected =
            job.secondary ? secondary_job(job.person)
                          : primary_job(job.person);
        if (!persons.alive(job.person) || expected != job.id ||
            state.firms.get(job.firm) == nullptr ||
            roster_seen[index] != 1U ||
            (job.suspended && job.suspension_day < job.hire_day)) {
            return Status(ErrorCode::invariant_violation,
                          "active employment contract is inconsistent");
        }
    }
    if (active != active_count_ || suspended != suspended_count_) {
        return Status(ErrorCode::invariant_violation,
                      "employment aggregate counters are inconsistent");
    }
    for (const auto person : persons.alive_ids()) {
        const double hours = active_hours(person);
        if (!finite(hours) || hours > 1.0 + tolerance) {
            return Status(ErrorCode::invariant_violation,
                          "person employment hours exceed capacity");
        }
    }
    return Status::success();
}

Status validate_labor_accounts(const LaborAccounts &accounts,
                               double tolerance) noexcept {
    const std::array values{
        accounts.employed_fte,
        accounts.employed_heads,
        accounts.unemployed,
        accounts.suspended,
        accounts.job_guarantee,
        accounts.out_of_labor_force,
        accounts.labor_supply,
        accounts.vacancies,
        accounts.underemployed_heads,
        accounts.underemployment_hours,
        accounts.suspended_memo,
        accounts.second_job_heads,
        accounts.second_job_hours,
        accounts.nonsearching,
        accounts.hires_total,
        accounts.churn_separations_total,
        accounts.layoff_separations_total,
        accounts.cash_layoffs_total,
        accounts.firm_exit_separations_total,
        accounts.death_separations_total,
        accounts.retirement_separations_total,
        accounts.recalls_total,
        accounts.suspensions_total,
        accounts.suspension_poaches_total,
        accounts.welfare_quits_total,
        accounts.job_to_job_moves_total,
        accounts.private_fte_inflows_total,
        accounts.private_fte_outflows_total,
        accounts.previous_employed_fte,
        accounts.previous_fte_flow_balance,
        accounts.previous_employed_heads,
        accounts.previous_head_flow_balance,
    };
    if (!std::all_of(values.begin(), values.end(), finite)) {
        return Status(ErrorCode::invariant_violation,
                      "labor accounts contain a non-finite value");
    }
    const auto nonnegative = std::array{
        accounts.employed_fte,
        accounts.employed_heads,
        accounts.unemployed,
        accounts.suspended,
        accounts.job_guarantee,
        accounts.out_of_labor_force,
        accounts.labor_supply,
        accounts.vacancies,
        accounts.underemployed_heads,
        accounts.underemployment_hours,
        accounts.suspended_memo,
        accounts.second_job_heads,
        accounts.second_job_hours,
        accounts.nonsearching,
    };
    if (std::any_of(nonnegative.begin(), nonnegative.end(),
                    [tolerance](double value) {
                        return value < -tolerance;
                    }) ||
        accounts.employed_fte >
            accounts.employed_heads + tolerance) {
        return Status(ErrorCode::invariant_violation,
                      "labor stock is inconsistent");
    }
    const double partition =
        accounts.employed_fte + accounts.unemployed +
        accounts.suspended + accounts.job_guarantee;
    if (std::abs(partition - accounts.labor_supply) >
        tolerance * std::max(1.0, accounts.labor_supply)) {
        return Status(ErrorCode::invariant_violation,
                      "labor force partition is inconsistent");
    }
    return Status::success();
}

} // namespace macro_sim::core
