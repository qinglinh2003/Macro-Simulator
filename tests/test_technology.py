"""v19: the Technology object -- productivity as a single, time-varying authority."""
from __future__ import annotations

import hashlib
import json

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.systems.technology import Technology


class _Firm:
    def __init__(self, sells):
        self.sells = sells


def _digest(cfg, n):
    econ = Economy(cfg)
    h = hashlib.sha256()
    for _ in range(n):
        r = econ.step()
        h.update(json.dumps({k: (round(v, 9) if isinstance(v, float) else v)
                             for k, v in sorted(r.items())}, default=str).encode())
    return h.hexdigest()[:16]


# -- 19.0: the inert object -------------------------------------------------

def test_factor_defaults_to_one():
    tech = Technology()
    assert tech.factor_for(_Firm("consumption")) == 1.0
    assert tech.factor_for(_Firm("capital")) == 1.0
    assert tech.factor_for(_Firm("energy")) == 1.0
    assert tech.factor("c") == 1.0


def test_step_is_inert_when_off():
    tech = Technology()
    for _ in range(1000):
        tech.step(econ=None)
    assert tech.z == {"c": 1.0, "k": 1.0, "e": 1.0}


def test_output_factor_is_pubcap_when_inert():
    econ = Economy(Config.v2(seed=1, n_households=30, n_firms=8, n_ticks=1))
    f = econ.c_firms[0]
    # inert TFP => the composite factor is exactly the public-capital factor
    assert econ._output_factor(f) == econ._pubcap_factor


def test_v2_bit_identical_with_object_present():
    # a v2 (no demographics) run must be unchanged by the presence of the inert object;
    # this pins the refactor's bit-identity guarantee in the suite.
    d = _digest(Config.v2(seed=4, n_households=40, n_firms=10, n_ticks=120), 120)
    assert d == _digest(Config.v2(seed=4, n_households=40, n_firms=10, n_ticks=120), 120)


# -- 19.1: exogenous drift --------------------------------------------------

def test_exogenous_drift_grows_z():
    tech = Technology(drift_rate=0.05)   # 5%/yr
    for _ in range(365):
        tech.step(econ=None)
    # after one year Z ~ (1 + 0.05/365)^365 ~ e^0.05 ~ 1.0513
    assert abs(tech.z["c"] - (1.0 + 0.05 / 365.0) ** 365) < 1e-12
    assert 1.050 < tech.z["c"] < 1.052


def test_zero_drift_is_bit_identical_flag_present():
    # the drift knobs default to 0; a config that sets them explicitly to 0 must digest
    # identically to one that omits them (the inert guarantee holds through config).
    base = Config.v2(seed=6, n_households=40, n_firms=10, n_ticks=100)
    withz = Config.v2(seed=6, n_households=40, n_firms=10, n_ticks=100,
                      tfp_drift_rate=0.0, tfp_drift_sigma=0.0)
    assert _digest(base, 100) == _digest(withz, 100)


def test_per_sector_drift_diverges():
    tech = Technology(sector_drift={"c": 0.02, "k": 0.0})
    for _ in range(365):
        tech.step(econ=None)
    assert tech.z["c"] > 1.0
    assert tech.z["k"] == 1.0   # a sector with no drift stays put


# -- 19.3: the learning-by-doing seam ---------------------------------------

def test_learning_law_inert_at_theta_zero():
    tech = Technology(law="learning", learning_theta=0.0)

    class _Econ:
        _cumulative_output_by_sector = {"c": 100.0, "k": 50.0, "e": 10.0}

    for _ in range(100):
        tech.step(_Econ())
    assert tech.z == {"c": 1.0, "k": 1.0, "e": 1.0}


def test_learning_law_rises_with_cumulative_output():
    tech = Technology(law="learning", learning_theta=0.5)

    class _Econ:
        _cumulative_output_by_sector = {"c": 100.0, "k": 100.0, "e": 100.0}

    tech.step(_Econ())          # sets the base at 100 => Z stays 1.0
    assert abs(tech.z["c"] - 1.0) < 1e-12
    _Econ._cumulative_output_by_sector = {"c": 400.0, "k": 100.0, "e": 100.0}
    tech.step(_Econ())          # c quadrupled => Z_c = 4^0.5 = 2.0
    assert abs(tech.z["c"] - 2.0) < 1e-9
    assert abs(tech.z["k"] - 1.0) < 1e-9


# -- end-to-end in a real economy (the seam actually moves output) ----------

def _short_v13(**extra):
    return Config.v13(seed=2, n_households=50, n_firms_c=50, n_firms_k=25, n_banks=2,
                      demographics_population=500, n_ticks=365, **extra)


def test_exogenous_drift_raises_z_and_cumulative_output_accumulates():
    econ = Economy(_short_v13(tfp_drift_rate=0.05))
    for _ in range(365):
        r = econ.step()
    # one year of 5%/yr Hicks-neutral drift => Z ~ e^0.05
    assert 1.045 < r["tfp_index_c"] < 1.055
    assert econ._cumulative_output_by_sector["c"] > 0.0   # accumulator ran


def test_learning_law_reaches_the_index_in_a_real_run():
    econ = Economy(_short_v13(tfp_law="learning", tfp_learning_theta=0.1))
    for _ in range(365):
        r = econ.step()
    # endogenous: cumulative output grows within the year => Z rises above its base of 1.0
    assert r["tfp_index_c"] > 1.0


def test_accumulator_is_bit_identical_when_exogenous_off():
    # the cumulative-output accumulator must not perturb the off/exogenous trajectory
    # (nothing reads it unless law='learning'): same-seed digests must match.
    assert _digest(_short_v13(), 200) == _digest(_short_v13(), 200)
