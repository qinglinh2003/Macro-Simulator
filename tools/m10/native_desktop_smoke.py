from __future__ import annotations

import argparse
import json
from pathlib import Path
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
    assert opening["boundary"] == 0
    assert opening["date"] == runtime.spec.start_date
    assert len(opening["policy_values"]) == 102
    assert opening["entity_counts"]["persons_alive"] > 0
    assert len(opening["public_metrics"]["economies"]) == 3
    assert runtime.schema()["policy_count"] == 102

    staged = runtime.stage_policy([
        {"lever": "tax_income_rate", "value": 0.31},
        {"lever": "tariff", "value": 0.08},
    ])
    assert staged["boundary"] == 0
    assert staged["last_policy_event"]["status"] == "staged"
    advanced = runtime.advance(2)
    assert advanced["advanced_ticks"] == 2
    assert advanced["boundary"] == 2
    assert advanced["policy_values"]["tax_income_rate"] == 0.31
    assert advanced["policy_values"]["tariff"] == 0.08
    assert advanced["last_policy_event"]["effective_boundary"] == 1

    households = runtime.entity_page(
        "households", maximum_rows=2,
    )
    assert len(households["rows"]) == 2
    assert households["rows"][0]["member_ids"]
    persons = runtime.entity_page("persons", maximum_rows=2)
    assert len(persons["rows"]) == 2
    firms = runtime.entity_page("firms", maximum_rows=2)
    assert len(firms["rows"]) == 2
    assert {"id", "employee_ids", "cash", "debt"} <= set(firms["rows"][0])

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
