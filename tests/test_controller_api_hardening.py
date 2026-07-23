"""Frontend schema must preserve the Registry validation union exactly."""
import pytest

from macro_sim.checkpoint import session_digest
from macro_sim.config import Config
from macro_sim.controllers.api import ControllerService
from macro_sim.controllers.occupants import NullOccupant
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.economy import Economy
from macro_sim.core.policy_explanations import POLICY_EXPLANATIONS
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.world import World


def _service(n: int = 2) -> ControllerService:
    cfg = Config.v13(
        seed=91,
        n_households=6,
        n_firms_c=4,
        n_firms_k=2,
        n_banks=1,
        n_ticks=5,
        government=True,
    )
    return ControllerService(ControlledSimulationSession(
        World([cfg] * n, base_seed=91)
    ))


def _payload(**patch):
    payload = {
        "schema_version": 1,
        "proposal_id": "proposal:test",
        "idempotency_key": "idempotency:test",
        "context_id": "context:test",
        "actions": [],
        "based_on_policy_versions": {},
    }
    payload.update(patch)
    return payload


def test_policy_schema_distinguishes_integer_nullable_and_dynamic_reference_types():
    service = _service()

    treasury = {
        row["name"]: row
        for row in service.policy_schema(economy_id=0, seat="treasury")["levers"]
    }
    assert treasury["bond_maturity"]["value_kind"] == "integer"
    assert treasury["bond_maturity"]["nullable"] is False
    assert treasury["tax_income_rate"]["current_value"] == 0.20
    assert treasury["tax_necessity_rate"]["value_kind"] == "number"
    assert treasury["tax_necessity_rate"]["nullable"] is True
    assert treasury["gov_consumption_share"]["read_point"]
    assert treasury["gov_consumption_share"]["shadowed_by"] == [
        "gov_deficit_target>0",
    ]
    assert "state_notes" in treasury["gov_consumption_share"]
    assert treasury["gov_consumption_share"]["player_help"] == {
        "meaning": POLICY_EXPLANATIONS["gov_consumption_share"].meaning,
        "mechanics": POLICY_EXPLANATIONS["gov_consumption_share"].mechanics,
        "tradeoffs": POLICY_EXPLANATIONS["gov_consumption_share"].tradeoffs,
        "watch": POLICY_EXPLANATIONS["gov_consumption_share"].watch,
    }

    central_bank = {
        row["name"]: row
        for row in service.policy_schema(economy_id=0, seat="central_bank")["levers"]
    }
    assert central_bank["peg_anchor"]["value_kind"] == "economy_id"
    assert central_bank["peg_anchor"]["choices"] == [1, None]
    assert central_bank["peg_anchor"]["nullable"] is True

    external = {
        row["name"]: row
        for row in service.policy_schema(economy_id=0, seat="external_affairs")["levers"]
    }
    assert external["sanctions_imposed_on"]["value_kind"] == "economy_set"
    assert external["sanctions_imposed_on"]["choices"] == [1]
    assert external["sanctions_imposed_on"]["nullable"] is False
    assert external["sanctions_imposed_on"]["current_value"] == []


def test_every_registered_policy_has_complete_player_help():
    assert set(POLICY_EXPLANATIONS) == set(REGISTRY)
    for name, explanation in POLICY_EXPLANATIONS.items():
        values = explanation.to_dict()
        assert set(values) == {"meaning", "mechanics", "tradeoffs", "watch"}
        assert all(
            isinstance(text, str) and len(text.strip()) >= 10
            for text in values.values()
        ), name
        # Policy meaning is an economics concept, not a description of the UI
        # control or simulation implementation. Those rules are shown separately.
        assert "模型" not in explanation.meaning, name
        assert not any(
            marker in explanation.meaning
            for marker in ("旋钮", "控制形式", "生效方式", "注册表")
        ), name


def test_bare_economy_schema_excludes_structurally_absent_external_levers():
    cfg = Config.v13(
        seed=92,
        n_households=6,
        n_firms_c=4,
        n_firms_k=2,
        n_banks=1,
        n_ticks=5,
        government=True,
    )
    service = ControllerService(ControlledSimulationSession(Economy(cfg)))

    central_bank = service.policy_schema(economy_id=0, seat="central_bank")
    names = {row["name"] for row in central_bank["levers"]}
    assert names
    assert not {
        name for name, lever in REGISTRY.items() if lever.scope == "external"
    } & names
    assert service.policy_schema(
        economy_id=0, seat="external_affairs",
    )["levers"] == []


@pytest.mark.parametrize(
    "patch",
    (
        {"schema_version": True},
        {"schema_version": 1.0},
        {"proposal_id": 12},
        {"context_id": None},
        {"based_on_policy_versions": {"tax_income_rate": True}},
    ),
)
def test_frontend_proposal_parser_rejects_coercible_wrong_types(patch):
    service = _service()
    payload = _payload(**patch)
    before = session_digest(service.session)
    with pytest.raises((TypeError, ValueError)):
        service.submit_proposal(payload, actor="frontend")
    assert session_digest(service.session) == before


def test_frontend_proposal_parser_requires_schema_and_exact_action_shape():
    service = _service()
    before = session_digest(service.session)
    payload = {
        "proposal_id": "proposal:test",
        "idempotency_key": "idempotency:test",
        "context_id": "context:test",
        "actions": [{"lever": "tax_income_rate"}],
        "based_on_policy_versions": {},
    }
    with pytest.raises(ValueError, match="missing required"):
        service.submit_proposal(payload, actor="frontend")
    assert session_digest(service.session) == before
    payload["schema_version"] = 1
    with pytest.raises(ValueError, match="exactly lever and value"):
        service.submit_proposal(payload, actor="frontend")
    assert session_digest(service.session) == before


@pytest.mark.parametrize(
    "payload,actor",
    (
        (_payload(), None),
        (_payload(), "   "),
        (_payload(proposal_id="\t"), "frontend"),
        (_payload(idempotency_key=" "), "frontend"),
        (_payload(context_id="\n"), "frontend"),
        (_payload(actions=[{"lever": " ", "value": 0.1}]), "frontend"),
        (_payload(supersedes_proposal_id=" "), "frontend"),
        ({**_payload(), 3: "non-string-key"}, "frontend"),
    ),
)
def test_transport_proposal_ingress_rejects_before_state_mutation(payload, actor):
    service = _service()
    before = session_digest(service.session)

    with pytest.raises((TypeError, ValueError)):
        service.submit_proposal(payload, actor=actor)

    assert session_digest(service.session) == before


@pytest.mark.parametrize(
    "call",
    (
        lambda service: service.policy_schema(economy_id=True, seat="treasury"),
        lambda service: service.policy_schema(economy_id=1.0, seat="treasury"),
        lambda service: service.policy_schema(economy_id=-1, seat="treasury"),
        lambda service: service.policy_schema(economy_id=2, seat="treasury"),
        lambda service: service.policy_schema(economy_id=0, seat="unknown"),
        lambda service: service.decision_context("   "),
        lambda service: service.decision_context(None),
        lambda service: service.pending(economy_id=True),
        lambda service: service.pending(economy_id=-1),
        lambda service: service.cancel_pending(" ", actor="frontend"),
        lambda service: service.cancel_pending("decision:missing", actor=" "),
        lambda service: service.cancel_pending("decision:missing", actor="frontend"),
    ),
)
def test_identifier_ingress_failure_is_state_neutral(call):
    service = _service()
    before = session_digest(service.session)

    with pytest.raises((KeyError, TypeError, ValueError)):
        call(service)

    assert session_digest(service.session) == before


@pytest.mark.parametrize(
    "kwargs",
    (
        {"economy_id": True, "seat": "treasury", "actor": "admin"},
        {"economy_id": -1, "seat": "treasury", "actor": "admin"},
        {"economy_id": 0, "seat": "unknown", "actor": "admin"},
        {"economy_id": 0, "seat": "treasury", "actor": " "},
        {
            "economy_id": 0,
            "seat": "treasury",
            "actor": "admin",
            "initialization": "restore:",
        },
        {
            "economy_id": 0,
            "seat": "treasury",
            "actor": "admin",
            "initialization": "restore: ",
        },
        {
            "economy_id": 0,
            "seat": "treasury",
            "actor": "admin",
            "initialization": "reuse",
        },
    ),
)
def test_seat_assignment_ingress_failure_is_state_neutral(kwargs):
    service = _service()
    before = session_digest(service.session)

    with pytest.raises((TypeError, ValueError)):
        service.assign_seat(occupant=NullOccupant(), **kwargs)

    assert session_digest(service.session) == before


def test_invalid_occupant_rejects_before_assignment_state_mutation():
    service = _service()
    before = session_digest(service.session)

    with pytest.raises(TypeError, match="callable propose"):
        service.assign_seat(
            economy_id=0,
            seat="treasury",
            occupant=object(),
            actor="admin",
        )

    assert session_digest(service.session) == before
