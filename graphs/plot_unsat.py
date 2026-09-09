#!/usr/bin/env python3
"""Generate separate Slot/ThunderFork plots for the UNSAT sweep.

The CSV is expected to come from make_unsat_time_breakdown_csv.py. Every
available numeric timing is used; semantic errors have blank numeric times and
are therefore excluded from performance curves.
"""

import argparse
import re
from pathlib import Path

from plot_cactus import AQUA, BLUE, ORANGE, method_series, plot_cactus
from plot_paired_scatter import (
    load_breakdown_index,
    paired_same_source,
    plot_metric,
)

GRAPHS_DIR = Path(__file__).resolve().parent
ROOT_DIR = GRAPHS_DIR.parent
DEFAULT_BREAKDOWN = ROOT_DIR / "scripts" / "result-csv" / "time_breakdown_unsat.csv"
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


def validate_rows(index):
    solvers = set()
    for benchmark, row in index.items():
        for method in ("slot", "chain", "chained_single_query"):
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


# same-source comparisons: (y_label, x_label, y_method, x_method, name)
SAME_SOURCE = [
    ("Slot", "ThunderFork-Parallel", "slot", "chain", "slot_vs_chain"),
    ("Slot", "ThunderFork-Single-Query", "slot", "chained_single_query",
     "slot_vs_chained_single_query"),
]

# cactus series: (label, color, method)
METHOD_SERIES = [
    ("Slot", BLUE, "slot"),
    ("ThunderFork-Parallel", ORANGE, "chain"),
    ("ThunderFork-Single-Query", AQUA, "chained_single_query"),
]

METRICS = [("solver_time", "solver"), ("total_seconds", "total")]


def main():
    args = parse_args()
    if not args.breakdown_csv.is_file():
        raise SystemExit(f"breakdown CSV is not a file: {args.breakdown_csv}")

    all_rows = load_breakdown_index(args.breakdown_csv)
    solver = validate_rows(all_rows)
    solver_tag = re.sub(r"[^A-Za-z0-9_.-]+", "-", solver.lower())

    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for metric_suffix, metric_tag in METRICS:
        for y_label, x_label, y_method, x_method, name in SAME_SOURCE:
            xs, ys, statuses = paired_same_source(
                all_rows, f"{y_method}_{metric_suffix}", f"{x_method}_{metric_suffix}")
            plot_metric(
                xs, ys, statuses, y_label, x_label,
                args.output_dir / f"{solver_tag}_{name}_{metric_tag}.pdf",
            )

        series = [(label, color, method_series(all_rows, method, metric_suffix))
                  for label, color, method in METHOD_SERIES]
        plot_cactus(
            series,
            len(all_rows),
            args.output_dir / f"{solver_tag}_cactus_methods_{metric_tag}.pdf",
        )

    print(
        f"UNSAT plots use all available timing data from "
        f"{len(all_rows)} manifest rows; output={args.output_dir}"
    )


if __name__ == "__main__":
    main()
