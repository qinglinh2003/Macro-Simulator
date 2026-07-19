"""Deployment gates for the safe RL context/model artifact contract."""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import hashlib
import json
import pickle
from pathlib import Path
import zipfile

import numpy as np
import pytest

from macro_sim.config import Config
from macro_sim.controllers.gym_adapter import ControllerEnv
from macro_sim.controllers.observation import InstitutionObservation, Release
from macro_sim.controllers.occupants import RLOccupant
from macro_sim.controllers.protocol import DecisionContext, PermittedAction
from macro_sim.controllers.scheduler import (
    DEFAULT_CALENDARS,
    CalendarSpec,
    DecisionScheduler,
)
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.rl.artifact import (
    ArtifactError,
    MANIFEST_NAME,
    WEIGHTS_NAME,
    load_artifact,
    save_artifact,
)
from macro_sim.rl.codec import ContextCodec, DirectionalActionCodec
from macro_sim.rl.envs import FiscalStabilizationConfig, FiscalStabilizationEnvFactory
from macro_sim.rl.model import NumpyMLPPolicy
from macro_sim.world import World


LEVERS = ("inflation_target", "manual_policy_rate", "monetary_regime")


def _context(
    *,
    regime: str = "taylor",
    manual_rate: float | None = None,
    inflation_allowed: bool = True,
) -> DecisionContext:
    boundary = 12
    observation = InstitutionObservation(
        boundary_tick=boundary,
        economy_id=0,
        role="central_bank",
        elapsed_ticks=4,
        releases=(Release(
            "headline_inflation",
            0.03,
            11,
            11,
            12,
            economy_id=0,
        ),),
    )
    permitted = (
        PermittedAction(
            "inflation_target",
            0.0,
            inflation_allowed,
            None if inflation_allowed else "minimum_hold",
            value_kind="number",
            minimum=-0.02,
            maximum=0.02,
            control_scale=0.00025,
            max_step=0.001,
            earliest_effective_tick=13,
        ),
        PermittedAction(
            "manual_policy_rate",
            manual_rate,
            True,
            value_kind="number",
            minimum=0.0,
            maximum=0.01,
            nullable=True,
            control_scale=0.0001,
            max_step=0.001,
            earliest_effective_tick=13,
        ),
        PermittedAction(
            "monetary_regime",
            regime,
            True,
            value_kind="choice",
            choices=("exogenous", "taylor", "manual"),
            earliest_effective_tick=13,
        ),
    )
    current = {
        "inflation_target": 0.0,
        "manual_policy_rate": manual_rate,
        "monetary_regime": regime,
    }
    return DecisionContext(
        context_id="ctx:0:central_bank:12",
        decision_window_id="window:12",
        economy_id=0,
        seat="central_bank",
        decision_group="monetary_stance",
        boundary_tick=boundary,
        expires_at_tick=14,
        policy_versions={name: 3 for name in LEVERS},
        observation=observation,
        permitted_actions=permitted,
        current_policy=current,
        last_effective_ticks={name: 8 for name in LEVERS},
        next_eligibility_ticks={name: 13 for name in LEVERS},
        admin_remaining=8.0,
        admin_reserved=1.0,
        admin_capacity=10.0,
        elapsed_ticks=4,
    )


def _fx_context(*, regime: str, anchor: int | None) -> DecisionContext:
    permitted = (
        PermittedAction(
            "fx_regime",
            regime,
            True,
            value_kind="choice",
            choices=("float", "peg"),
            earliest_effective_tick=4,
        ),
        PermittedAction(
            "peg_anchor",
            anchor,
            True,
            value_kind="economy_id",
            choices=(1, 2, None),
            nullable=True,
            earliest_effective_tick=4,
        ),
    )
    return DecisionContext(
        context_id="ctx:fx:3",
        decision_window_id="window:fx:3",
        economy_id=0,
        seat="central_bank",
        decision_group="fx_operations",
        boundary_tick=3,
        expires_at_tick=5,
        policy_versions={"fx_regime": 0, "peg_anchor": 0},
        observation=InstitutionObservation(
            3, 0, "central_bank", (), elapsed_ticks=3,
        ),
        permitted_actions=permitted,
        current_policy={"fx_regime": regime, "peg_anchor": anchor},
        last_effective_ticks={"fx_regime": None, "peg_anchor": None},
        next_eligibility_ticks={"fx_regime": 4, "peg_anchor": 4},
        admin_remaining=10.0,
        admin_capacity=10.0,
        elapsed_ticks=3,
    )


def _codecs() -> tuple[ContextCodec, DirectionalActionCodec]:
    context_codec = ContextCodec.from_parts(
        economy_id=0,
        seat="central_bank",
        action_levers=LEVERS,
        observation_series=("headline_inflation",),
        normalization_scales={"headline_inflation": 0.01},
    )
    return context_codec, DirectionalActionCodec.from_context_codec(context_codec)


def test_context_codec_rejects_multi_economy_universe_drift():
    codec = ContextCodec.from_parts(
        economy_id=0,
        seat="central_bank",
        action_levers=("fx_regime", "peg_anchor"),
        economy_targets=(1, 2),
    )
    context = _fx_context(regime="float", anchor=None)
    codec.encode(context)
    actions = tuple(
        replace(item, choices=(1, 2, 3, None))
        if item.lever == "peg_anchor" else item
        for item in context.permitted_actions
    )
    with pytest.raises(ValueError, match="economy universe drift"):
        codec.encode(replace(context, permitted_actions=actions))


def _policy(
    *,
    deterministic: bool = True,
    seed: int = 44,
    biases: np.ndarray | None = None,
) -> NumpyMLPPolicy:
    context_codec, action_codec = _codecs()
    output_dim = action_codec.action_dim * 3
    if biases is None:
        biases = np.zeros(output_dim, dtype=np.float32)
        # Raise inflation, hold the two regime controls.
        biases.reshape(action_codec.action_dim, 3)[:, 1] = 2.0
        inflation_index = action_codec.action_dimensions.index(
            ("inflation_target", None)
        )
        biases.reshape(action_codec.action_dim, 3)[inflation_index] = (0.0, 0.0, 4.0)
    return NumpyMLPPolicy(
        context_codec,
        action_codec,
        (np.zeros(
            (output_dim, context_codec.observation_dim), dtype=np.float32,
        ),),
        (biases,),
        input_mean=np.zeros(context_codec.observation_dim, dtype=np.float32),
        input_scale=np.full(context_codec.observation_dim, 2.0, dtype=np.float32),
        deterministic=deterministic,
        seed=seed,
    )


def _rewrite_artifact(
    source: Path,
    target: Path,
    transform,
) -> None:
    with zipfile.ZipFile(source, "r") as archive:
        manifest = json.loads(archive.read(MANIFEST_NAME))
        weights = archive.read(WEIGHTS_NAME)
    manifest, weights = transform(manifest, weights)
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr(
            MANIFEST_NAME,
            json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        )
        archive.writestr(WEIGHTS_NAME, weights)


def test_context_codec_has_golden_layout_hash_and_no_live_session_dependency():
    codec, action_codec = _codecs()
    context = _context()

    assert codec.feature_names[:9] == (
        "boundary_tick",
        "elapsed_ticks",
        "release:headline_inflation:value",
        "release:headline_inflation:missing",
        "decision:ticks_to_expiry",
        "decision:emergency",
        "decision:emergency_trigger_present",
        "admin:remaining",
        "admin:reserved",
    )
    assert codec.observation_dim == 39
    assert codec.contract_hash == (
        "5d0d26aed9d39b9ff6671129b143da2bca0c512cec373405a08368f1e3bf6883"
    )
    assert action_codec.contract_hash == (
        "bca8111a3867ec44e9949a6823d1596d5a7521300af433cf5acd518f696048ed"
    )
    assert ContextCodec.from_dict(codec.to_dict()) == codec
    assert DirectionalActionCodec.from_dict(
        action_codec.to_dict(), context_codec=codec,
    ) == action_codec

    encoded = codec.encode(context)
    assert encoded.shape == (39,)
    assert encoded.flags.writeable is False
    assert encoded[0] == 12.0
    assert encoded[1] == 4.0
    assert encoded[2] == pytest.approx(3.0)  # frozen release normalization
    assert np.all(np.isfinite(encoded))


def test_context_codec_rejects_schema_economy_release_and_registry_drift():
    codec, _action_codec = _codecs()
    context = _context()
    with pytest.raises(ValueError, match="economy_id"):
        codec.encode(replace(context, economy_id=1))
    with pytest.raises(ValueError, match="observation schema"):
        codec.encode(replace(context, observation_schema_version=2))
    empty_observation = replace(context.observation, releases=())
    with pytest.raises(ValueError, match="release series"):
        codec.encode(replace(context, observation=empty_observation))

    malformed = codec.to_dict()
    malformed["lever_specs"][0]["maximum"] = 123.0
    drifted = ContextCodec.from_dict(malformed)
    with pytest.raises(ValueError, match="registry schema drift"):
        drifted.verify_runtime_registry()


def test_from_env_matches_real_context_base_vector_and_includes_denied_releases():
    calendars = {
        name: CalendarSpec(1_000, offset_ticks=999, admin_capacity=100.0)
        for name in DEFAULT_CALENDARS
    }
    calendars["monetary_stance"] = CalendarSpec(4, admin_capacity=100.0)
    session = ControlledSimulationSession(
        World([Config.v13(
            seed=410,
            n_households=8,
            n_firms_c=5,
            n_firms_k=3,
            n_banks=1,
            n_ticks=12,
            government=True,
        )]),
        scheduler=DecisionScheduler(calendars=calendars, triggers=()),
    )
    env = ControllerEnv(session, economy_id=0, seat="central_bank")
    env.reset()
    assert env.context is not None
    codec = ContextCodec.from_env(env)
    deployed = codec.encode(env.context)
    gym_vector = env._vector(env.context)

    assert codec.feature_names == env.observation_features[:codec.observation_dim]
    np.testing.assert_array_equal(deployed, gym_vector[:codec.observation_dim])
    assert len(codec.release_specs) == len(session.release_service.spec.fields)
    # Every declared series is position-stable; unauthorized values are explicit
    # missing releases, never dropped dimensions.
    assert any(
        release.missing_reason == "access_denied"
        for release in env.context.observation.releases
    )


def test_directional_codec_masks_unavailable_actions_and_builds_joint_templates():
    codec, actions = _codecs()
    context = _context(inflation_allowed=False)
    mask = actions.action_mask(context, context_codec=codec)
    inflation_index = actions.action_dimensions.index(("inflation_target", None))
    np.testing.assert_array_equal(mask[inflation_index], (False, True, False))
    with pytest.raises(ValueError, match="unavailable dimensions"):
        codes = np.ones(actions.action_dim, dtype=np.int64)
        codes[inflation_index] = 2
        actions.decode(codes, context, context_codec=codec)

    context = _context(regime="taylor", manual_rate=None)
    regime_index = actions.action_dimensions.index(("monetary_regime", None))
    enter_manual = np.ones(actions.action_dim, dtype=np.int64)
    enter_manual[regime_index] = 2
    decoded = actions.decode(enter_manual, context, context_codec=codec)
    assert [(item.lever, item.value) for item in decoded] == [
        ("manual_policy_rate", 0.0),
        ("monetary_regime", "manual"),
    ]

    context = _context(regime="manual", manual_rate=0.004)
    leave_manual = np.ones(actions.action_dim, dtype=np.int64)
    leave_manual[regime_index] = 0
    decoded = actions.decode(leave_manual, context, context_codec=codec)
    assert [(item.lever, item.value) for item in decoded] == [
        ("manual_policy_rate", None),
        ("monetary_regime", "taylor"),
    ]

    fx_codec = ContextCodec.from_parts(
        economy_id=0,
        seat="central_bank",
        action_levers=("fx_regime", "peg_anchor"),
        economy_targets=(1, 2),
    )
    fx_actions = DirectionalActionCodec.from_context_codec(fx_codec)
    regime_index = fx_actions.action_dimensions.index(("fx_regime", None))
    enter = np.ones(fx_actions.action_dim, dtype=np.int64)
    enter[regime_index] = 2
    assert [(item.lever, item.value) for item in fx_actions.decode(
        enter, _fx_context(regime="float", anchor=None), context_codec=fx_codec,
    )] == [("fx_regime", "peg"), ("peg_anchor", 1)]
    leave = np.ones(fx_actions.action_dim, dtype=np.int64)
    leave[regime_index] = 0
    assert [(item.lever, item.value) for item in fx_actions.decode(
        leave, _fx_context(regime="peg", anchor=1), context_codec=fx_codec,
    )] == [("fx_regime", "float"), ("peg_anchor", None)]


def test_model_supports_context_callable_and_vector_evaluation_interfaces():
    policy = _policy()
    context = _context()

    actions = policy(context)
    assert [(item.lever, item.value) for item in actions] == [
        ("inflation_target", 0.00025),
    ]
    vector = policy.context_codec.encode(context)
    mask = policy.action_codec.action_mask(
        context, context_codec=policy.context_codec,
    )
    np.testing.assert_array_equal(
        policy.predict(vector, action_mask=mask, deterministic=True),
        policy.predict_codes(context, deterministic=True),
    )
    with pytest.raises(ValueError, match="observation shape"):
        policy.predict(vector[:-1], action_mask=mask)
    with pytest.raises(ValueError, match="action_mask shape"):
        policy.predict(vector, action_mask=mask[:-1])
    poisoned = vector.copy()
    poisoned[0] = np.nan
    with pytest.raises(ValueError, match="NaN or Infinity"):
        policy.predict(poisoned, action_mask=mask)


def test_trusted_actor_export_matches_network_dense_parameters():
    codec, actions = _codecs()

    class Tensor:
        def __init__(self, value):
            self.value = np.asarray(value, dtype=np.float32)

        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return self.value

    class Linear:
        def __init__(self, weight, bias):
            self.weight = Tensor(weight)
            self.bias = Tensor(bias)

    class Network:
        observation_dim = codec.observation_dim
        action_dims = actions.action_dim
        activation_name = "tanh"
        actor = (
            Linear(
                np.zeros((5, codec.observation_dim), dtype=np.float32),
                np.zeros(5, dtype=np.float32),
            ),
            object(),  # activation modules carry no parameters and are skipped
        )
        policy_head = Linear(
            np.zeros((actions.action_dim * 3, 5), dtype=np.float32),
            np.zeros(actions.action_dim * 3, dtype=np.float32),
        )

    exported = NumpyMLPPolicy.from_actor_critic(
        codec,
        actions,
        Network(),
        input_mean=np.arange(codec.observation_dim, dtype=np.float32),
        input_scale=np.full(codec.observation_dim, 3.0, dtype=np.float32),
    )
    assert exported.layer_shapes == ((5, 39), (9, 5))
    assert exported.input_mean[-1] == 38.0
    assert exported.input_scale[-1] == 3.0


def test_real_actor_critic_export_is_logit_equivalent():
    torch = pytest.importorskip("torch")
    from macro_sim.rl.network import ActorCriticNetwork

    codec, actions = _codecs()
    torch.manual_seed(2027)
    network = ActorCriticNetwork(
        codec.observation_dim,
        actions.action_dim,
        hidden_sizes=(16, 8),
        activation="tanh",
    )
    network.eval()
    exported = NumpyMLPPolicy.from_actor_critic(
        codec,
        actions,
        network,
        input_clip=None,
    )
    context = _context()
    observation = codec.encode(context).astype(np.float32)
    with torch.no_grad():
        expected, _value = network(torch.from_numpy(observation.copy()))
    np.testing.assert_allclose(
        exported.logits(context), expected.detach().cpu().numpy(),
        rtol=2e-5, atol=2e-6,
    )


def test_stochastic_sampling_is_seeded_and_checkpoint_pickle_exact():
    first = _policy(deterministic=False, seed=913)
    second = _policy(deterministic=False, seed=913)
    context = _context()
    first_codes = [first.predict_codes(context).tolist() for _ in range(5)]
    second_codes = [second.predict_codes(context).tolist() for _ in range(5)]
    assert first_codes == second_codes
    first.reseed(913)
    assert [first.predict_codes(context).tolist() for _ in range(5)] == first_codes

    restored = pickle.loads(pickle.dumps(first, protocol=5))
    assert [first.predict_codes(context).tolist() for _ in range(8)] == [
        restored.predict_codes(context).tolist() for _ in range(8)
    ]

    occupant = pickle.loads(pickle.dumps(RLOccupant(policy=restored), protocol=5))
    proposal = occupant.propose(context)
    assert proposal is not None
    assert proposal.context_id == context.context_id
    assert all(item.lever in LEVERS for item in proposal.actions)


def test_constructor_strictly_rejects_shape_dtype_scale_and_nonfinite_parameters():
    context_codec, action_codec = _codecs()
    output = action_codec.action_dim * 3
    weight = np.zeros((output, context_codec.observation_dim), dtype=np.float32)
    bias = np.zeros(output, dtype=np.float32)
    with pytest.raises(ValueError, match="output dimension"):
        NumpyMLPPolicy(
            context_codec,
            action_codec,
            (weight[:-1],),
            (bias[:-1],),
        )
    with pytest.raises(TypeError, match="dtype"):
        NumpyMLPPolicy(
            context_codec,
            action_codec,
            (weight.astype(np.float16),),
            (bias.astype(np.float16),),
        )
    poisoned = bias.copy()
    poisoned[0] = np.inf
    with pytest.raises(ValueError, match="NaN or Infinity"):
        NumpyMLPPolicy(context_codec, action_codec, (weight,), (poisoned,))
    with pytest.raises(ValueError, match="input_scale entries"):
        NumpyMLPPolicy(
            context_codec,
            action_codec,
            (weight,),
            (bias,),
            input_scale=np.zeros(context_codec.observation_dim, dtype=np.float32),
        )


def test_artifact_roundtrip_is_callable_portable_and_overrideable(tmp_path: Path):
    source_policy = _policy(deterministic=False, seed=71)
    target = save_artifact(
        tmp_path / "monetary-policy.mrl",
        source_policy,
        metadata={"experiment": "paired-seed-v1", "score": 1.25},
    )
    with zipfile.ZipFile(target, "r") as archive:
        assert set(archive.namelist()) == {MANIFEST_NAME, WEIGHTS_NAME}
        manifest = json.loads(archive.read(MANIFEST_NAME))
        assert manifest["metadata"]["experiment"] == "paired-seed-v1"
        assert manifest["weights"]["sha256"] == hashlib.sha256(
            archive.read(WEIGHTS_NAME)
        ).hexdigest()

    deterministic = load_artifact(target, deterministic=True)
    context = _context()
    assert deterministic(context) == _policy()(context)
    assert deterministic.input_mean.dtype == np.float32
    assert deterministic.input_scale.tolist() == [2.0] * 39

    stochastic_a = load_artifact(target, deterministic=False, seed=999)
    stochastic_b = load_artifact(target, deterministic=False, seed=999)
    assert [stochastic_a.predict_codes(context).tolist() for _ in range(12)] == [
        stochastic_b.predict_codes(context).tolist() for _ in range(12)
    ]


def test_loaded_artifact_runs_as_rl_occupant_in_real_controlled_session(
    tmp_path: Path,
):
    env = FiscalStabilizationEnvFactory(FiscalStabilizationConfig(
        horizon_ticks=30,
        decision_period_ticks=15,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
    ))(881)
    codec = env.context_codec
    actions = env.action_codec
    # A deliberately inert network makes this an integration test rather than a
    # claim about economic performance: its unique preferred code is hold.
    bias = np.asarray((0.0, 5.0, 0.0), dtype=np.float32)
    policy = NumpyMLPPolicy(
        codec,
        actions,
        (np.zeros((3, codec.observation_dim), dtype=np.float32),),
        (bias,),
    )
    deployed = load_artifact(save_artifact(tmp_path / "fiscal.mrl", policy))
    env.session.assign_seat(
        0,
        "treasury",
        RLOccupant(policy=deployed),
        actor="deployment-test",
        log_event=False,
    )

    result = env.session.advance()
    assert result.status == "advanced"
    assert len(result.decisions) == 1
    assert result.decisions[0].status == "accepted_noop"
    assert env.session.boundary_tick == 1
    restored = pickle.loads(pickle.dumps(env.session, protocol=5))
    restored_policy = restored.seat_assignments[(0, "treasury")].policy
    assert isinstance(restored_policy, NumpyMLPPolicy)
    assert restored.advance().status == env.session.advance().status


def test_artifact_fails_closed_on_manifest_hash_weight_and_finite_tampering(
    tmp_path: Path,
):
    source = save_artifact(tmp_path / "source.mrl", _policy())

    bad_context = tmp_path / "bad-context.mrl"
    _rewrite_artifact(
        source,
        bad_context,
        lambda manifest, weights: (
            {**manifest, "context_contract_hash": "0" * 64}, weights,
        ),
    )
    with pytest.raises(ArtifactError, match="context contract SHA-256"):
        load_artifact(bad_context)

    bad_model = tmp_path / "bad-model.mrl"
    def mutate_model(manifest, weights):
        manifest["model"]["temperature"] = 2.0
        return manifest, weights
    _rewrite_artifact(source, bad_model, mutate_model)
    with pytest.raises(ArtifactError, match="model contract SHA-256"):
        load_artifact(bad_model)

    bad_weights = tmp_path / "bad-weights.mrl"
    _rewrite_artifact(
        source,
        bad_weights,
        lambda manifest, weights: (manifest, weights + b"tamper"),
    )
    with pytest.raises(ArtifactError, match="weights (size|SHA-256)"):
        load_artifact(bad_weights)

    def poison_bias(manifest, weights):
        with np.load(BytesIO(weights), allow_pickle=False) as archive:
            arrays = {name: np.array(archive[name]) for name in archive.files}
        arrays["layer_0_bias"][0] = np.nan
        buffer = BytesIO()
        np.savez_compressed(buffer, **arrays)
        poisoned = buffer.getvalue()
        manifest["weights"]["size_bytes"] = len(poisoned)
        manifest["weights"]["sha256"] = hashlib.sha256(poisoned).hexdigest()
        return manifest, poisoned

    nonfinite = tmp_path / "nonfinite.mrl"
    _rewrite_artifact(source, nonfinite, poison_bias)
    with pytest.raises(ArtifactError, match="NaN or Infinity"):
        load_artifact(nonfinite)


def test_artifact_never_loads_object_arrays(tmp_path: Path):
    source = save_artifact(tmp_path / "source.mrl", _policy())

    def object_payload(manifest, weights):
        with np.load(BytesIO(weights), allow_pickle=False) as archive:
            arrays = {name: np.array(archive[name]) for name in archive.files}
        arrays["layer_0_bias"] = np.asarray([object()] * 9, dtype=object)
        buffer = BytesIO()
        np.savez_compressed(buffer, **arrays)
        payload = buffer.getvalue()
        manifest["weights"]["size_bytes"] = len(payload)
        manifest["weights"]["sha256"] = hashlib.sha256(payload).hexdigest()
        return manifest, payload

    target = tmp_path / "object-array.mrl"
    _rewrite_artifact(source, target, object_payload)
    with pytest.raises(ArtifactError, match="numeric payload"):
        load_artifact(target)
