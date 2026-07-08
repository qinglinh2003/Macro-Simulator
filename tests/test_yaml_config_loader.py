import subprocess
import sys
from pathlib import Path

import pytest

from macro_sim.config import Config


def test_yaml_loader_merges_extends_and_overrides(tmp_path):
    base = tmp_path / "base.yaml"
    child = tmp_path / "child.yaml"
    base.write_text(
        """
params:
  n_households: 10
  n_firms_c: 3
  n_firms_k: 1
  theta_price: 0.25
""".strip()
    )
    child.write_text(
        """
extends:
  - base.yaml
params:
  n_households: 12
  theta_price: 0.125
""".strip()
    )

    from macro_sim.config.loader import load_config_file

    cfg = load_config_file(child)

    assert isinstance(cfg, Config)
    assert cfg.n_households == 12
    assert cfg.n_firms_c == 3
    assert cfg.n_firms_k == 1
    assert cfg.theta_price == 0.125


def test_yaml_loader_rejects_unknown_config_keys(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
params:
  n_households: 10
  typo_households: 99
""".strip()
    )

    from macro_sim.config.loader import load_config_file

    with pytest.raises(ValueError, match="typo_households"):
        load_config_file(path)


def test_v124_daily_light_yaml_loads_daily_tick_parameters():
    from macro_sim.config.loader import config_to_dict, load_config_file

    cfg = load_config_file("configs/runs/v124_daily_light.yaml")
    resolved = config_to_dict(cfg)

    assert cfg.n_households == 200
    assert cfg.n_firms_c == 20
    assert cfg.n_firms_k == 10
    assert cfg.n_ticks == 180
    assert cfg.theta_price == pytest.approx(0.0037)
    assert cfg.theta_wage == pytest.approx(0.0027)
    assert cfg.bond_coupon == pytest.approx(1.08e-4)
    assert cfg.bond_maturity == 365
    assert cfg.bankrupt_persist == 548
    assert resolved["portfolio_adjust"] == pytest.approx(0.048)


def test_run_py_accepts_yaml_config_file(tmp_path):
    cmd = [
        sys.executable,
        "run.py",
        "--config",
        "configs/runs/v124_daily_light.yaml",
        "--ticks",
        "2",
        "--output-dir",
        str(tmp_path),
        "--no-plots",
        "--no-sweep",
    ]

    result = subprocess.run(cmd, text=True, capture_output=True, timeout=60)

    assert result.returncode == 0, result.stderr
    assert "config=configs/runs/v124_daily_light.yaml" in result.stdout
    assert "records=2" in result.stdout
    assert any(Path(tmp_path).iterdir())
