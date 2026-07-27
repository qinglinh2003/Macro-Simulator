#include <cassert>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <utility>

#include <nlohmann/json.hpp>

#include "macro_sim/desktop/m11_protocol.hpp"

namespace {

using Json = nlohmann::json;
using namespace macro_sim;
using namespace macro_sim::desktop;

inline constexpr std::string_view kToken =
    "0123456789abcdef0123456789abcdef"
    "0123456789abcdef0123456789abcdef";

[[nodiscard]] M11ProtocolWorker worker(
    std::filesystem::path save_root = {}) {
    M11ProtocolOptions options;
    options.capability_token = std::string(kToken);
    options.save_root = std::move(save_root);
    auto result =
        M11ProtocolWorker::create(std::move(options));
    assert(result.ok());
    return std::move(*result.get_if());
}

[[nodiscard]] Json request(
    std::uint64_t sequence, std::string command,
    std::string request_id = {}) {
    if (request_id.empty()) {
        request_id = "request-" + std::to_string(sequence);
    }
    return {
        {"protocol_version", kM11DesktopProtocolVersion},
        {"request_id", std::move(request_id)},
        {"connection_id", "godot-primary"},
        {"sequence", sequence},
        {"token", kToken},
        {"command", std::move(command)},
    };
}

[[nodiscard]] Json response(
    M11ProtocolWorker &protocol, const Json &value) {
    return Json::parse(protocol.handle_frame(value.dump()));
}

void test_authentication_framing_and_sequence() {
    auto protocol = worker();
    assert(valid_m11_capability_token(kToken));
    assert(!valid_m11_capability_token("short"));

    auto wrong_token = request(1U, "hello");
    wrong_token["token"] =
        "ffffffffffffffffffffffffffffffff"
        "ffffffffffffffffffffffffffffffff";
    const auto rejected =
        response(protocol, wrong_token);
    assert(!rejected.at("ok").get<bool>());
    assert(rejected.at("error").at("code") ==
           "authentication_failed");

    const auto hello_request = request(1U, "hello");
    const auto hello_text =
        protocol.handle_frame(hello_request.dump());
    const auto hello = Json::parse(hello_text);
    assert(hello.at("ok").get<bool>());
    assert(hello.at("result").at("worker") ==
           "macro_sim_server");
    assert(protocol.handle_frame(hello_request.dump()) ==
           hello_text);

    auto conflict = hello_request;
    conflict["request_id"] = "different-request";
    const auto conflict_response =
        response(protocol, conflict);
    assert(!conflict_response.at("ok").get<bool>());
    assert(conflict_response.at("error").at("code") ==
           "sequence_conflict");

    const auto gap =
        response(protocol, request(3U, "hello"));
    assert(!gap.at("ok").get<bool>());
    assert(gap.at("error").at("code") == "sequence_gap");
    assert(gap.at("error").at("full_resync").get<bool>());

    const auto duplicate_key = protocol.handle_frame(
        R"JSON({"protocol_version":5,"request_id":"x","request_id":"y","connection_id":"c","sequence":1,"token":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","command":"hello"})JSON");
    assert(Json::parse(duplicate_key)
               .at("error")
               .at("code") == "malformed_json");
}

void test_session_owner_snapshot_and_delta() {
    auto protocol = worker();
    assert(response(protocol, request(1U, "hello"))
               .at("ok")
               .get<bool>());
    auto create = request(2U, "new_session");
    create["seed"] = 29U;
    const auto created = response(protocol, create);
    assert(created.at("ok").get<bool>());
    assert(protocol.has_session());
    const auto session_id =
        created.at("result")
            .at("session_id")
            .get<std::string>();
    const auto first_snapshot =
        created.at("result")
            .at("projection")
            .at("snapshot");
    const auto first_id =
        first_snapshot.at("snapshot_id")
            .get<std::string>();
    assert(first_snapshot.at("snapshot_sequence") == 1U);
    assert(first_snapshot.at("scope").at("role") ==
           "player");

    auto snapshot = request(3U, "snapshot");
    snapshot["session_id"] = session_id;
    snapshot["base_snapshot_id"] = first_id;
    const auto delta = response(protocol, snapshot);
    assert(delta.at("ok").get<bool>());
    assert(delta.at("result").at("mode") == "delta");
    assert(delta.at("result")
               .at("delta")
               .at("base_snapshot_id") == first_id);
    assert(delta.at("result")
               .at("delta")
               .at("result_sequence") == 2U);

    auto stale = request(4U, "snapshot");
    stale["session_id"] = session_id;
    stale["base_snapshot_id"] =
        "ffffffffffffffffffffffffffffffff"
        "ffffffffffffffffffffffffffffffff";
    const auto resync = response(protocol, stale);
    assert(resync.at("ok").get<bool>());
    assert(resync.at("result").at("mode") ==
           "full_resync");

    auto other = request(1U, "hello", "other-hello");
    other["connection_id"] = "foreign-client";
    assert(response(protocol, other).at("ok").get<bool>());
    other = request(2U, "snapshot", "other-snapshot");
    other["connection_id"] = "foreign-client";
    other["session_id"] = session_id;
    const auto denied = response(protocol, other);
    assert(!denied.at("ok").get<bool>());
    assert(denied.at("error").at("code") ==
           "access_denied");

    auto close = request(5U, "close_session");
    close["session_id"] = session_id;
    const auto closed = response(protocol, close);
    assert(closed.at("ok").get<bool>());
    assert(!protocol.has_session());
}

void test_human_advance_pauses_without_consuming_time() {
    auto protocol = worker();
    assert(response(protocol, request(1U, "hello"))
               .at("ok")
               .get<bool>());
    const auto created =
        response(protocol, request(2U, "new_session"));
    assert(created.at("ok").get<bool>());
    const auto session_id =
        created.at("result")
            .at("session_id")
            .get<std::string>();
    auto advance = request(3U, "advance");
    advance["session_id"] = session_id;
    advance["ticks"] = 5U;
    const auto paused = response(protocol, advance);
    assert(paused.at("ok").get<bool>());
    assert(paused.at("result")
               .at("advance")
               .at("awaiting_human")
               .get<bool>());
    assert(paused.at("result")
               .at("advance")
               .at("elapsed_ticks") == 0U);
    assert(paused.at("result")
               .at("projection")
               .at("snapshot")
               .at("boundary") == 0U);
}

void test_control_commands_are_role_scoped_and_idempotent() {
    auto protocol = worker();
    assert(response(protocol, request(1U, "hello"))
               .at("ok")
               .get<bool>());
    const auto created =
        response(protocol, request(2U, "new_session"));
    const auto session_id =
        created.at("result")
            .at("session_id")
            .get<std::string>();

    auto schema_request = request(3U, "policy_schema");
    schema_request["session_id"] = session_id;
    schema_request["role"] = "central_bank";
    const auto schema =
        response(protocol, schema_request);
    assert(schema.at("ok").get<bool>());
    assert(!schema.at("result")
                .at("levers")
                .empty());
    for (const auto &lever :
         schema.at("result").at("levers")) {
        assert(lever.at("owner_role") == "central_bank");
    }

    auto advance = request(4U, "advance");
    advance["session_id"] = session_id;
    const auto paused = response(protocol, advance);
    assert(paused.at("ok").get<bool>());
    const auto &contexts =
        paused.at("result")
            .at("projection")
            .at("snapshot")
            .at("contexts");
    assert(!contexts.empty());
    const auto context_id =
        contexts.front()
            .at("context_id")
            .get<std::string>();

    auto proposal =
        request(5U, "submit_human_policy");
    proposal["session_id"] = session_id;
    proposal["context_id"] = context_id;
    proposal["operation_id"] = "hold-context";
    proposal["actions"] = Json::array();
    const auto held = response(protocol, proposal);
    assert(held.at("ok").get<bool>());
    assert(held.at("result")
               .at("decision")
               .at("status") == "accepted_noop");

    auto shock = request(6U, "schedule_shock");
    shock["session_id"] = session_id;
    shock["operation_id"] = "shock-operation";
    shock["seat"] = "energy";
    shock["shock"] = {
        {"shock_id", 9001U},
        {"kind", "energy_capacity"},
        {"economy_id", 0U},
        {"start", 1U},
        {"duration", 3U},
        {"magnitude", 0.25},
        {"shape", "step"},
    };
    const auto scheduled = response(protocol, shock);
    assert(scheduled.at("ok").get<bool>());
    assert(!scheduled.at("result")
                .at("repeated")
                .get<bool>());

    shock["sequence"] = 7U;
    shock["request_id"] = "shock-retry-new-sequence";
    const auto repeated = response(protocol, shock);
    assert(repeated.at("ok").get<bool>());
    assert(repeated.at("result")
               .at("repeated")
               .get<bool>());
    assert(repeated.at("result").at("shock_id") == 9001U);

    auto contexts_request =
        request(8U, "decision_context");
    contexts_request["session_id"] = session_id;
    contexts_request["role"] = "central_bank";
    const auto central_contexts =
        response(protocol, contexts_request);
    assert(central_contexts.at("ok").get<bool>());
    for (const auto &context :
         central_contexts.at("result").at("contexts")) {
        assert(context.at("seat") == "central_bank");
    }
}

void test_entity_pages_and_details_preserve_links() {
    auto protocol = worker();
    assert(response(protocol, request(1U, "hello"))
               .at("ok")
               .get<bool>());
    const auto created =
        response(protocol, request(2U, "new_session"));
    const auto session_id =
        created.at("result")
            .at("session_id")
            .get<std::string>();

    auto page_request = request(3U, "entity_page");
    page_request["session_id"] = session_id;
    page_request["kind"] = "households";
    page_request["economy_id"] = 0U;
    page_request["after_id"] = 0U;
    page_request["maximum_rows"] = 4U;
    const auto page = response(protocol, page_request);
    assert(page.at("ok").get<bool>());
    assert(page.at("result").at("kind") == "households");
    assert(!page.at("result").at("rows").empty());
    const auto first =
        page.at("result").at("rows").front();
    assert(first.at("member_ids").empty());
    const auto household_id =
        first.at("id").get<std::uint64_t>();

    auto detail_request = request(4U, "entity_detail");
    detail_request["session_id"] = session_id;
    detail_request["kind"] = "household";
    detail_request["economy_id"] = 0U;
    detail_request["entity_id"] = household_id;
    const auto detail = response(protocol, detail_request);
    assert(detail.at("ok").get<bool>());
    const auto entity = detail.at("result").at("entity");
    assert(entity.at("id") == household_id);
    assert(entity.at("member_count") ==
           entity.at("member_ids").size());
    if (!entity.at("member_ids").empty()) {
        const auto person_id =
            entity.at("member_ids")
                .front()
                .get<std::uint64_t>();
        auto person_request =
            request(5U, "entity_detail");
        person_request["session_id"] = session_id;
        person_request["kind"] = "person";
        person_request["economy_id"] = 0U;
        person_request["entity_id"] = person_id;
        const auto person =
            response(protocol, person_request);
        assert(person.at("ok").get<bool>());
        assert(person.at("result")
                   .at("entity")
                   .at("household_id") == household_id);
    }
}

void test_save_load_is_sandboxed_atomic_and_verified() {
    const auto root =
        std::filesystem::temp_directory_path() /
        "macro-sim-m11-protocol-save-test";
    std::error_code cleanup_error;
    std::filesystem::remove_all(root, cleanup_error);
    auto protocol = worker(root);
    assert(response(protocol, request(1U, "hello"))
               .at("ok")
               .get<bool>());
    const auto created =
        response(protocol, request(2U, "new_session"));
    const auto first_session =
        created.at("result")
            .at("session_id")
            .get<std::string>();

    auto save = request(3U, "save_slot");
    save["session_id"] = first_session;
    save["slot_id"] = "campaign_01";
    const auto saved = response(protocol, save);
    assert(saved.at("ok").get<bool>());
    assert(saved.at("result").at("bytes")
               .get<std::uint64_t>() > 0U);
    assert(std::filesystem::is_regular_file(
        root / "campaign_01.msim"));

    auto close = request(4U, "close_session");
    close["session_id"] = first_session;
    assert(response(protocol, close).at("ok").get<bool>());

    auto load = request(5U, "load_slot");
    load["slot_id"] = "campaign_01";
    const auto loaded = response(protocol, load);
    assert(loaded.at("ok").get<bool>());
    const auto second_session =
        loaded.at("result")
            .at("session_id")
            .get<std::string>();
    assert(second_session != first_session);
    assert(loaded.at("result")
               .at("projection")
               .at("snapshot")
               .at("boundary") == 0U);

    save = request(6U, "save_slot");
    save["session_id"] = second_session;
    save["slot_id"] = "campaign_01";
    assert(response(protocol, save).at("ok").get<bool>());
    close = request(7U, "close_session");
    close["session_id"] = second_session;
    assert(response(protocol, close).at("ok").get<bool>());

    const auto path = root / "campaign_01.msim";
    const auto size = std::filesystem::file_size(path);
    assert(size > 32U);
    {
        std::fstream stream(
            path, std::ios::binary | std::ios::in |
                      std::ios::out);
        assert(stream);
        stream.seekg(
            static_cast<std::streamoff>(size - 1U));
        char corrupt = '\0';
        stream.read(&corrupt, 1);
        assert(stream);
        corrupt = static_cast<char>(
            static_cast<unsigned char>(corrupt) ^ 0x5aU);
        stream.seekp(
            static_cast<std::streamoff>(size - 1U));
        stream.write(&corrupt, 1);
        assert(stream);
    }
    load = request(8U, "load_slot");
    load["slot_id"] = "campaign_01";
    const auto corrupt = response(protocol, load);
    assert(!corrupt.at("ok").get<bool>());
    assert(corrupt.at("error").at("code") ==
           "corrupt_input");
    assert(!protocol.has_session());

    auto invalid_slot = request(9U, "load_slot");
    invalid_slot["slot_id"] = "../escape";
    const auto rejected =
        response(protocol, invalid_slot);
    assert(!rejected.at("ok").get<bool>());
    assert(rejected.at("error").at("code") ==
           "invalid_argument");
    std::filesystem::remove_all(root, cleanup_error);
}

} // namespace

int main() {
    test_authentication_framing_and_sequence();
    test_session_owner_snapshot_and_delta();
    test_human_advance_pauses_without_consuming_time();
    test_control_commands_are_role_scoped_and_idempotent();
    test_entity_pages_and_details_preserve_links();
    test_save_load_is_sandboxed_atomic_and_verified();
    return 0;
}
