"""Production-scale economic diagnostics and root-cause probes.

The diagnostics package is intentionally outside the model scheduler.  It consumes the
record produced by ``Economy.step`` and immutable reads of live agent state.  Reporting
snapshots are pure; the kernel advances metric-derived behavioral sensors separately and
exactly once per accepted tick.
"""

from macro_sim.diagnostics.models import Finding, Intervention, RunOutcome, RunSpec

__all__ = ["Finding", "Intervention", "RunOutcome", "RunSpec"]
