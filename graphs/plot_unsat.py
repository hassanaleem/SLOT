#!/usr/bin/env python3
"""Generate separate Slot/ThunderFork plots for the UNSAT sweep.

The CSV is expected to come from make_unsat_time_breakdown_csv.py.  Only
benchmarks with at least one select are part of the plot population; semantic
errors have blank numeric times and are therefore excluded from performance
curves.
"""

import argparse
import re
from pathlib import Path

from plot_cactus import BLUE, ORANGE, method_series, plot_cactus
from plot_paired_scatter import (
    load_breakdown_index,
    paired_same_source,
    plot_metric,
)

GRAPHS_DIR = Path(__file__).resolve().parent
ROOT_DIR = GRAPHS_DIR.parent
DEFAULT_BREAKDOWN = ROOT_DIR / "scripts" / "time_breakdown_unsat.csv"
DEFAULT_OUTPUT_DIR = GRAPHS_DIR / "unsat"
EXPECTED_RESULTS = {"unsat", "timeout"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Plot the UNSAT Slot/ThunderFork results separately.",
    )
    parser.add_argument(
        "breakdown_csv",
        nargs="?",
        type=Path,
        default=DEFAULT_BREAKDOWN,
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    return parser.parse_args()


def select_eligible(index):
    eligible = {}
    for benchmark, row in index.items():
        value = (row.get("num_selects") or "").strip()
        if value and int(value) > 0:
            eligible[benchmark] = row
    return eligible


def validate_rows(index):
    solvers = set()
    for benchmark, row in index.items():
        for method in ("slot", "chain"):
            solver = (row.get(f"{method}_solver") or "").strip()
            result = (row.get(f"{method}_result") or "").strip()
            solver_time = (row.get(f"{method}_solver_time") or "").strip()
            total_time = (row.get(f"{method}_total_seconds") or "").strip()
            if solver:
                solvers.add(solver)
            if (solver_time or total_time) and result not in EXPECTED_RESULTS:
                raise ValueError(
                    f"{benchmark}/{method} has numeric time for invalid "
                    f"UNSAT result {result!r}"
                )
    if len(solvers) != 1:
        names = ", ".join(sorted(solvers)) or "none"
        raise ValueError(f"expected one solver in UNSAT CSV, found: {names}")
    return next(iter(solvers))


def main():
    args = parse_args()
    if not args.breakdown_csv.is_file():
        raise SystemExit(f"breakdown CSV is not a file: {args.breakdown_csv}")

    all_rows = load_breakdown_index(args.breakdown_csv)
    eligible = select_eligible(all_rows)
    solver = validate_rows(eligible)
    solver_tag = re.sub(r"[^A-Za-z0-9_.-]+", "-", solver.lower())

    args.output_dir.mkdir(parents=True, exist_ok=True)

    for metric_suffix, metric_tag in (
        ("solver_time", "solver"),
        ("total_seconds", "total"),
    ):
        xs, ys, statuses = paired_same_source(
            eligible,
            f"slot_{metric_suffix}",
            f"chain_{metric_suffix}",
        )
        plot_metric(
            xs,
            ys,
            statuses,
            "Slot",
            "ThunderFork",
            args.output_dir / f"{solver_tag}_slot_vs_chain_{metric_tag}.pdf",
        )

        series = [
            (
                "Slot",
                BLUE,
                method_series(eligible, "slot", metric_suffix),
            ),
            (
                "ThunderFork",
                ORANGE,
                method_series(eligible, "chain", metric_suffix),
            ),
        ]
        plot_cactus(
            series,
            len(eligible),
            args.output_dir / f"{solver_tag}_cactus_methods_{metric_tag}.pdf",
        )

    print(
        f"UNSAT plots use {len(eligible)} select-eligible benchmarks "
        f"from {len(all_rows)} manifest rows; output={args.output_dir}"
    )


if __name__ == "__main__":
    main()
