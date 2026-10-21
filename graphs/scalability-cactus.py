#!/usr/bin/env python3
"""Plot four Z3 chain curves (n=5..8).

Reads the existing timing CSV and solver log formats. Writes solver-time and
total-time PDF/PNG plots under scalability-log/plots. Only SAT results count
as solved in this SAT suite; failures and timeouts remain in the denominator.
Incomplete sweeps are rejected unless --allow-partial is explicitly supplied.
"""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

ROOT = Path(__file__).resolve().parents[1]
COLORS = ("#2a78d6", "#eb6834", "#1baf7a", "#7a5c99")
COUNTS = (5, 6, 7, 8)
SOLVERS = ("z3",)


def load_results(directory, allow_partial=False):
    # Entries usually omit .smt2; preserve other dots within benchmark names.
    benchmarks = [Path(line.strip()).name.removesuffix(".smt2")
                  for line in (directory / "torun.txt").read_text().splitlines()
                  if line.strip() and not line.strip().startswith("#")]
    if not benchmarks or len(set(benchmarks)) != len(benchmarks):
        raise ValueError("benchmark list is empty or contains duplicate basenames")
    config = {"benchmarks": benchmarks, "counts": COUNTS, "solvers": SOLVERS}
    expected = {(b, n, s) for b in benchmarks for n in COUNTS for s in SOLVERS}
    rows = {}
    seen = set()
    for n in COUNTS:
        for solver in SOLVERS:
            timing_csv = directory / f"time-breakdown-n{n}-{solver}.csv"
            if not timing_csv.exists():
                continue
            with timing_csv.open(newline="") as stream:
                for source in csv.DictReader(stream):
                    key = (source["benchmark"], n, solver)
                    if key not in expected or key in seen:
                        raise ValueError(f"unexpected or duplicate result: {key}")
                    seen.add(key)
                    log = directory / f"n{n}" / solver / source["benchmark"] / "logs/solver-chain.log"
                    text = log.read_text() if log.exists() else ""
                    exit_code = re.search(r"^exit_code: (\d+)\s*$", text, re.MULTILINE)
                    if not exit_code:
                        continue  # Interrupted solves are not completed attempts.
                    status = "sat" if exit_code[1] == "0" and re.search(r"^SAT — query ", text, re.MULTILINE) else "unsolved"
                    row = {"status": status,
                           "solver_seconds": source["chain_solver_time"],
                           "total_seconds": source["chain_total_seconds"]}
                    if status == "sat":
                        for metric in ("solver_seconds", "total_seconds"):
                            value = float(row[metric])
                            if not math.isfinite(value) or value <= 0:
                                raise ValueError(f"invalid {metric} for {key}")
                    rows[key] = row
    missing = expected - rows.keys()
    if missing and not allow_partial:
        raise ValueError(f"{len(missing)} runs still missing; use --allow-partial for a preview")
    return config, rows, bool(missing)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=ROOT / "scalability-log")
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    config, rows, partial = load_results(args.results_dir, args.allow_partial)
    output = args.results_dir / "plots"
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams["pdf.fonttype"] = 42
    summary = []
    for solver in config["solvers"]:
        for metric, tag, label in (("solver_seconds", "solver", "Solver time"),
                                   ("total_seconds", "total", "Total time (translation + solver)")):
            fig, ax = plt.subplots(figsize=(8, 5.5))
            for n, color in zip(config["counts"], COLORS):
                selected = [r for (b, count, s), r in rows.items() if count == n and s == solver]
                times = sorted(float(r[metric]) for r in selected if r["status"] == "sat")
                ax.plot(range(1, len(times) + 1), times, color=color, linewidth=2,
                        marker="o", markersize=3, label=f"n = {n} ({len(times)} solved)")
                if tag == "solver":
                    summary.append({"solver": solver, "n": n, "expected": len(config["benchmarks"]),
                                    "recorded": len(selected), "solved": len(times),
                                    "statuses": dict(Counter(r["status"] for r in selected))})
            ax.set_yscale("log")
            ax.set_xlim(0, len(config["benchmarks"]) + 1)
            ax.xaxis.set_major_locator(MaxNLocator(integer=True))
            ax.set_xlabel("Benchmarks solved")
            ax.set_ylabel(f"{label} (seconds, log scale)")
            ax.set_title(f"{solver.upper()}: chain" + (" — PARTIAL" if partial else ""))
            ax.grid(axis="y", alpha=0.25)
            ax.legend()
            fig.tight_layout()
            for extension in ("pdf", "png"):
                path = output / f"{solver}_scalability_cactus_{tag}.{extension}"
                fig.savefig(path, dpi=200)
                print(path)
            plt.close(fig)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for entry in summary:
        print(f"{entry['solver']} n={entry['n']}: {entry['solved']}/{entry['expected']} solved; "
              f"{entry['recorded']} recorded")


if __name__ == "__main__":
    main()
