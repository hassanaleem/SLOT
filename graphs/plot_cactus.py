#!/usr/bin/env python3
"""Cactus (survival) plots: x = benchmarks solved (cumulative, sorted by time),
y = time to solve (log scale). Standard solver-comparison plot — where a line
stops (short of the full benchmark count) is where that approach ran out of
budget, so this is the clearest way to compare timeout behavior across methods.

Reads the same sources as plot_paired_scatter.py (and reuses its benchmark
normalization/index helpers, so "N attempted" always means the same set of
benchmarks across every line drawn together on one plot):
  - ../scripts/time_breakdown_z3.csv / time_breakdown_cvc5.csv (chain,
    chained-single-query methods)
  - ../z3-variants.csv / ../cvc5-variants.csv (baseline + flag variants)

Writes into this directory:
  z3_cactus_chain_vs_chained_single_query_{solver,total}.pdf
  cvc5_cactus_chain_vs_chained_single_query_{solver,total}.pdf
                                           - ThunderFork-Parallel (chain) vs
                                             ThunderFork-Single-Query (chained_single_query)
  z3_cactus_baseline_{solver,total}.pdf   - chain vs z3 baseline vs z3+flag
  cvc5_cactus_baseline_{solver,total}.pdf - chain vs cvc5 baseline vs cvc5+ite(-heuristics)
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from plot_paired_scatter import (
    Z3_BREAKDOWN_CSV, CVC5_BREAKDOWN_CSV, Z3_VARIANTS_CSV, CVC5_VARIANTS_CSV,
    TIMEOUT_SECONDS, SOLVED_RESULTS,
    load_breakdown_index, load_variants_index, parse_time,
)

GRAPHS_DIR = Path(__file__).parent

# dataviz skill: validated categorical order, fixed assignment (never cycled)
SURFACE = "#ffffff"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE_AXIS = "#c3c2b7"

BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
YELLOW = "#eda100"


def breakdown_timed_out(row, method):
    """Infer a timeout from either time recorded for a breakdown method.

    In particular, some capped cvc5 solver runs are recorded as exactly 650s,
    while the associated total time (which includes setup) is greater than
    650s. Looking at both fields keeps those implicit timeouts out of both the
    solver-time and total-time cactus curves.
    """
    solver_time = parse_time(row, f"{method}_solver_time")
    total_time = parse_time(row, f"{method}_total_seconds")
    return any(value is not None and value > TIMEOUT_SECONDS
               for value in (solver_time, total_time))


def method_series(idx, method, metric_suffix):
    col = f"{method}_{metric_suffix}"
    return [value for row in idx.values()
            if (value := parse_time(row, col)) is not None
            and not breakdown_timed_out(row, method)]


def variant_series_common(idx_x, x_col, status_col, common_keys):
    times = []
    for key in common_keys:
        row = idx_x[key]
        value = parse_time(row, x_col)
        status = (row.get(status_col) or "").strip().lower()
        if value is not None and value <= TIMEOUT_SECONDS and status in SOLVED_RESULTS:
            times.append(value)
    return times


def breakdown_series_common(idx_y, method, metric_suffix, common_keys):
    col = f"{method}_{metric_suffix}"
    return [value for key in common_keys
            if (value := parse_time(idx_y[key], col)) is not None
            and not breakdown_timed_out(idx_y[key], method)]


def survival_xy(times):
    ys = sorted(times)
    xs = list(range(1, len(ys) + 1))
    return xs, ys


def plot_cactus(series, total_attempted, filename):
    """series: list of (label, color, times) tuples, drawn in the given order."""
    fig, ax = plt.subplots(figsize=(8.5, 6.5), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    max_y = 1.0
    for label, color, times in series:
        if not times:
            continue
        xs, ys = survival_xy(times)
        max_y = max(max_y, max(ys))
        ax.plot(xs, ys, color=color, linewidth=2, solid_capstyle="round",
                 label=f"{label} ({len(ys)}/{total_attempted})", zorder=3)

    ax.set_yscale("log")
    ax.set_xlim(0, total_attempted + 1)
    ax.set_ylim(top=max_y * 1.6)

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.grid(axis="y", color=GRIDLINE, linewidth=0.8, zorder=0)

    ax.set_xlabel("Benchmarks solved (cumulative, sorted by time)", color=INK_SECONDARY, fontsize=12)
    ax.set_ylabel("Time (seconds, log scale)", color=INK_SECONDARY, fontsize=12)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(BASELINE_AXIS)

    ax.legend(loc="upper left", ncol=1, frameon=True, facecolor=SURFACE,
              edgecolor="none", framealpha=0.9, fontsize=12,
              labelcolor=INK_SECONDARY, handlelength=1.8, columnspacing=1.3)

    fig.tight_layout()
    out_path = GRAPHS_DIR / filename
    fig.savefig(out_path, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    counts = ", ".join(f"{label}={len(times)}" for label, _, times in series)
    print(f"wrote {out_path} (of {total_attempted} attempted: {counts})")


def build_and_plot():
    z3_idx = load_breakdown_index(Z3_BREAKDOWN_CSV)
    cvc5_idx = load_breakdown_index(CVC5_BREAKDOWN_CSV)
    z3_variants_idx = load_variants_index(Z3_VARIANTS_CSV)
    cvc5_variants_idx = load_variants_index(CVC5_VARIANTS_CSV)

    # --- chain vs baseline solvers: restrict to benchmarks common to the
    # breakdown CSV and the variants CSV, so every line shares one denominator. ---
    z3_common = sorted(z3_idx.keys() & z3_variants_idx.keys())
    cvc5_common = sorted(cvc5_idx.keys() & cvc5_variants_idx.keys())

    for metric_suffix, metric_tag in [
        ("solver_time", "solver"), ("total_seconds", "total"),
    ]:
        # --- ThunderFork chain vs chained-single-query: both drawn from the
        # same breakdown CSV, so "attempted" is that CSV's own benchmark count. ---
        for solver_name, idx in [("z3", z3_idx), ("cvc5", cvc5_idx)]:
            series = [
                ("ThunderFork-Parallel", ORANGE, method_series(idx, "chain", metric_suffix)),
                ("ThunderFork-Single-Query", AQUA, method_series(idx, "chained_single_query", metric_suffix)),
            ]
            plot_cactus(
                series, len(idx),
                f"{solver_name}_cactus_chain_vs_chained_single_query_{metric_tag}.pdf",
            )

        z3_series = [
            ("ThunderFork", ORANGE, breakdown_series_common(z3_idx, "chain", metric_suffix, z3_common)),
            ("z3 baseline", BLUE, variant_series_common(z3_variants_idx, "time-z3", "result-z3", z3_common)),
            ("z3 + simplify-split-clause", AQUA,
             variant_series_common(z3_variants_idx, "time-simplify-split-clause", "result-simplify-split-clause", z3_common)),
        ]
        plot_cactus(z3_series, len(z3_common),
                    f"z3_cactus_baseline_{metric_tag}.pdf")

        cvc5_series = [
            ("ThunderFork", ORANGE, breakdown_series_common(cvc5_idx, "chain", metric_suffix, cvc5_common)),
            ("cvc5 baseline", BLUE, variant_series_common(cvc5_variants_idx, "time-cvc5", "result-cvc5", cvc5_common)),
            ("cvc5 + ite", AQUA,
             variant_series_common(cvc5_variants_idx, "time-cvc5-ite", "result-cvc5-ite", cvc5_common)),
            ("cvc5 + ite-heuristics", YELLOW,
             variant_series_common(cvc5_variants_idx, "time-cvc5-ite-heuristics", "result-cvc5-ite-heuristics", cvc5_common)),
        ]
        plot_cactus(cvc5_series, len(cvc5_common),
                    f"cvc5_cactus_baseline_{metric_tag}.pdf")


if __name__ == "__main__":
    build_and_plot()
