#include <cassert>
#include <cstdint>
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

[[nodiscard]] M11ProtocolWorker worker() {
    M11ProtocolOptions options;
    options.capability_token = std::string(kToken);
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
           "treasury");

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

} // namespace

int main() {
    test_authentication_framing_and_sequence();
    test_session_owner_snapshot_and_delta();
    test_human_advance_pauses_without_consuming_time();
    return 0;
}
