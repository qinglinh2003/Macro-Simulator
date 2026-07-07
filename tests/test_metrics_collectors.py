import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from macro_sim.config import Config
from macro_sim.economy import Economy


def test_metric_collector_protocol_preserves_tick_metric_keys():
    from macro_sim.reporting.collectors import EconomyMetricCollector, collect_metric_groups
    from macro_sim.reporting.metrics import _compute_tick_metrics, compute_tick_metrics

    cfg = Config.v124(n_firms_c=8, n_firms_k=4, n_households=80, n_ticks=1, seed=0)
    direct = compute_tick_metrics(Economy(cfg))
    collected = collect_metric_groups(Economy(cfg), [EconomyMetricCollector(_compute_tick_metrics)])

    assert collected.keys() == direct.keys()
    assert collected["total_money"] == direct["total_money"]
    assert collected["real_output"] == direct["real_output"]
