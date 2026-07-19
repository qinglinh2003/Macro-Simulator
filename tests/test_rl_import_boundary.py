from __future__ import annotations

import subprocess
import sys


def test_rl_package_and_portable_loader_do_not_eagerly_import_torch():
    script = """
import sys
import macro_sim.rl
assert 'torch' not in sys.modules
from macro_sim.rl import load_artifact
assert callable(load_artifact)
assert 'torch' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
