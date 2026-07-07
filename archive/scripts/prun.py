"""Parallel run harness -- fan independent Economy runs across all CPU cores.

Every (config, seed) run is independent, so a seed sweep is embarrassingly parallel. Build a list
of jobs ``(factory_name, kwargs)`` and call ``run_jobs`` -- it returns the records list per job,
in order. macOS uses spawn, so callers MUST guard entry with ``if __name__ == "__main__":``.

    from prun import run_jobs
    jobs = [("v84", dict(n_firms_c=200, n_households=2000, n_ticks=4000, seed=s)) for s in range(8)]
    all_recs = run_jobs(jobs)                       # 8 runs, one per core
"""
from __future__ import annotations

import os
from multiprocessing import Pool

from config import Config
from economy import Economy


def _run(job):
    factory, kwargs = job
    return Economy(getattr(Config, factory)(**kwargs)).run()


def run_jobs(jobs, processes: int | None = None):
    """Run each (factory_name, kwargs) job in its own process; return records in job order."""
    procs = processes or min(len(jobs), os.cpu_count() or 4)
    if procs <= 1:
        return [_run(j) for j in jobs]
    with Pool(procs) as pool:
        return pool.map(_run, jobs)
