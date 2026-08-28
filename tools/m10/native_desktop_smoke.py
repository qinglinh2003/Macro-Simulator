from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import socket
import sys
import threading


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.native_dir))
    sys.path.insert(1, str(args.source_dir))

    from macro_sim.desktop.native_runtime import (
        NATIVE_DESKTOP_PROTOCOL_VERSION,
        NativeSimulationRuntime,
    )
    from macro_sim.desktop.server import _Server
    from macro_sim.native_backend import NativeSimulationSession

    runtime = NativeSimulationRuntime(seed=1601)
    opening = runtime.snapshot()
    assert opening["backend"] == "native_m10_world"
    assert opening["protocol_version"] == 4
    assert opening["boundary"] == 0
    assert opening["tick"] == 0
    assert opening["date"] == runtime.spec.start_date
    assert len(opening["policy_values"]) == 102
    assert opening["entity_counts"]["persons_alive"] > 0
    assert len(opening["maintained_metrics"]["economies"]) == 3
    assert opening["free_policy"]["enabled"]
    assert not opening["contexts"]
    assert not opening["pending"]
    assert len(opening["households"]["items"]) > 0
    assert len(opening["firms"]["items"]) > 0
    assert len(opening["stock_market"]["listings"]) > 0
    first_firm = opening["firms"]["items"][0]
    for field in (
        "operations", "labor", "capital", "balance_sheet", "pnl",
        "equity", "parameters", "signals", "bank",
    ):
        assert isinstance(first_firm[field], dict), field
    latest_world = opening["world"]["latest"]
    assert isinstance(latest_world["dealer_valuation"], float)
    assert isinstance(latest_world["peg_intact"], bool)
    assert {
        "population", "labor", "real_economy", "distribution",
        "capital_market",
    } <= set(opening["panel_details"])
    schema = runtime.schema()
    assert schema["protocol_version"] == 4
    assert schema["control_mode"] == "free_policy"
    assert sum(
        len(seat["levers"]) for seat in schema["seats"].values()
    ) == 102
    assert all(
        set(lever["player_help"]) == {
            "meaning", "mechanics", "tradeoffs", "watch",
        }
        and isinstance(lever["evidence_scope"], dict)
        and lever["read_point"]
        and "state_notes" in lever
        and "help_key" in lever
        for seat in schema["seats"].values()
        for lever in seat["levers"]
    )
    assert len(schema["policy_evidence_sha256"]) == 64
    structural_schema = json.loads(json.dumps(schema))
    for seat in structural_schema["seats"].values():
        for lever in seat["levers"]:
            # Localized economics prose is a packaged data resource.  Stable
            # wire identifiers and executable state remain language-neutral.
            lever.pop("player_help", None)
    structural_schema["levers"] = structural_schema["seats"]["treasury"][
        "levers"
    ]
    assert not re.search(
        r"[\u3400-\u9fff]",
        json.dumps(
            {"snapshot": opening, "schema": structural_schema},
            ensure_ascii=False,
        ),
    )

    staged = runtime.stage_policy([
        {"lever": "tax_income_rate", "value": 0.31},
        {"lever": "tariff", "value": 0.08},
    ])
    assert staged["boundary"] == 0
    assert staged["last_verdict"]["status"] == "staged"
    assert staged["free_policy"]["effective_tick"] == 1
    advanced = runtime.advance(2)
    assert advanced["advanced_ticks"] == 2
    assert advanced["boundary"] == 2
    assert advanced["policy_values"]["tax_income_rate"] == 0.31
    assert advanced["policy_values"]["tariff"] == 0.08
    assert advanced["last_verdict"]["effective_tick"] == 1
    assert len(advanced["series"]) == 3

    households = runtime.entity_page(
        "households", maximum_rows=2,
    )
    assert len(households["rows"]) == 2
    assert households["rows"][0]["member_ids"]
    persons = runtime.entity_page("persons", maximum_rows=2)
    assert len(persons["rows"]) == 2
    firms = runtime.entity_page("firms", maximum_rows=2)
    assert len(firms["rows"]) == 2
    assert {
        "id", "employee_ids", "cash", "debt", "book_equity",
        "outstanding_shares", "share_price",
    } <= set(firms["rows"][0])
    equities = runtime.entity_page("equities", maximum_rows=2)
    assert equities["rows"]
    positions = runtime.entity_page(
        "security_positions", maximum_rows=2,
    )
    assert positions["rows"]

    checkpoint = runtime.checkpoint()
    restored, objective = NativeSimulationSession.restore(
        runtime.spec, checkpoint,
    )
    assert objective == b'{"client":"native_desktop_m10"}'
    assert restored.tick == runtime.tick
    assert restored.native_snapshot()["digest"] == (
        runtime.session.native_snapshot()["digest"]
    )

    with _Server(("127.0.0.1", 0), runtime) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with socket.create_connection(server.server_address, timeout=2.0) as client:
                client.sendall(
                    b'{"request_id":"native-smoke","command":"hello"}\n'
                )
                stream = client.makefile("rb")
                response = json.loads(stream.readline())
            assert response["ok"]
            assert response["request_id"] == "native-smoke"
            assert response["protocol_version"] == NATIVE_DESKTOP_PROTOCOL_VERSION
            assert response["snapshot"]["backend"] == "native_m10_world"
        finally:
            server.shutdown()
            thread.join(timeout=2.0)

    print("M10 native desktop smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
