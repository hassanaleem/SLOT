#!/usr/bin/env python3
"""Cactus (survival) plots: x = benchmarks solved (cumulative, sorted by time),
y = time to solve (log scale). Standard solver-comparison plot — where a line
stops (short of the full benchmark count) is where that approach ran out of
budget, so this is the clearest way to compare timeout behavior across methods.

Reads the same sources as plot_paired_scatter.py (and reuses its benchmark
normalization/index helpers, so "N attempted" always means the same set of
benchmarks across every line drawn together on one plot):
  - ../scripts/time_breakdown-llvm22-z3.csv / time_breakdown-llvm22-cvc5.csv
    (chain, chain-sink, chained-single-query, and their path-opt variants)
  - ../z3-variants.csv / ../cvc5-variants.csv (baseline + flag variants)

Writes PDF and PNG versions into this directory:
  z3_cactus_chain_vs_chained_single_query_{solver,total}.pdf
  cvc5_cactus_chain_vs_chained_single_query_{solver,total}.pdf
                                           - the four ThunderFork strategies,
                                             with and without per-path optimization
  {z3,cvc5}_cactus_chain_vs_chain_sink_{solver,total}.pdf
                                           - chain vs chain-sink
  thunderfork_vs_slot_{solver,total}.pdf - ThunderFork vs SLOT, Z3 and cvc5
  z3_cactus_baseline_{solver,total}.pdf   - chain vs z3 baseline vs z3+flag
  cvc5_cactus_baseline_{solver,total}.pdf - chain vs cvc5 baseline vs cvc5+ite(-heuristics)
"""
import argparse
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
POSTER_MODE = False

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
PURPLE = "#7a5c99"

# Keep each strategy's label/color tied to its timing CSV column prefix.
THUNDERFORK_METHODS = [
    ("ThunderFork-Parallel", ORANGE, "chain"),
    ("ThunderFork-Single-Query", AQUA, "chained_single_query"),
    ("ThunderFork-Parallel + Path Opt", BLUE, "chain_path_opt"),
    ("ThunderFork-Single-Query + Path Opt", PURPLE, "chained_single_query_path_opt"),
]


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


def plot_cactus(series, total_attempted, filename, legend_loc="best"):
    """series: list of (label, color, times) tuples, drawn in the given order."""
    if POSTER_MODE:
        fig = plt.figure(figsize=(25 / 2.54, 21 / 2.54), dpi=150)
        ax = fig.add_axes((0.17, 0.16, 0.79, 0.79))
    else:
        fig, ax = plt.subplots(figsize=(18, 14), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    max_y = 1.0
    for label, color, times in series:
        xs, ys = survival_xy(times)
        max_y = max(max_y, max(ys, default=1.0))
        ax.plot(xs, ys, color=color, linewidth=4, solid_capstyle="round",
                 marker="o" if len(ys) == 1 else None,
                 label=label, zorder=3)

    ax.set_yscale("log")
    ax.set_xlim(0, total_attempted + 1)
    ax.set_ylim(top=max_y * 1.6)

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.grid(axis="y", color=GRIDLINE, linewidth=0.8, zorder=0)

    ax.set_xlabel("Benchmarks solved",
                  color="#222222" if POSTER_MODE else INK_SECONDARY,
                  fontsize=26 if POSTER_MODE else 30)
    metric_label = "Solver time" if Path(filename).stem.endswith("_solver") else "Total time"
    ax.set_ylabel(f"{metric_label}(s, log scale)",
                  color="#222222" if POSTER_MODE else INK_SECONDARY,
                  fontsize=26 if POSTER_MODE else 30)
    ax.tick_params(colors="#222222" if POSTER_MODE else INK_MUTED,
                   labelsize=24 if POSTER_MODE else 30)
    if POSTER_MODE:
        ax.xaxis.set_major_locator(mticker.MultipleLocator(10))
    for spine in ax.spines.values():
        spine.set_color(BASELINE_AXIS)

    if POSTER_MODE:
        ax.legend(loc="upper left", frameon=True, facecolor=SURFACE,
                  edgecolor="none", framealpha=0.9, fontsize=24,
                  labelcolor="#222222", handlelength=1.5, labelspacing=0.25)
    else:
        ax.legend(loc=legend_loc, ncol=1, frameon=True, facecolor=SURFACE,
                  edgecolor="none", framealpha=0.9, fontsize=30,
                  labelcolor=INK_SECONDARY, handlelength=1.8, columnspacing=1.3)
        fig.tight_layout()
    counts = ", ".join(f"{label}={len(times)}" for label, _, times in series)
    output_dir = GRAPHS_DIR / "poster" if POSTER_MODE else GRAPHS_DIR
    output_dir.mkdir(exist_ok=True)
    for extension in (".pdf", ".png"):
        out_path = (output_dir / filename).with_suffix(extension)
        fig.savefig(out_path, facecolor=SURFACE,
                    bbox_inches=None if POSTER_MODE else "tight",
                    dpi=300 if POSTER_MODE else 200)
        print(f"wrote {out_path} (of {total_attempted} attempted: {counts})")
    plt.close(fig)


def plot_chain_sink(idx, solver_name, metric_suffix, metric_tag):
    # Compare the same benchmarks, keeping timeouts in the attempted count.
    methods = [
        ("ThunderFork-Parallel", ORANGE, "chain"),
        ("ThunderFork-Parallel + Sink", BLUE, "chain_sink"),
    ]
    common_keys = [
        key for key, row in idx.items()
        if all(parse_time(row, f"{method}_{metric_suffix}") is not None
               for _, _, method in methods)
    ]
    filename = f"{solver_name}_cactus_chain_vs_chain_sink_{metric_tag}.pdf"
    if not common_keys:
        print(f"skipped {filename} (no paired data)")
        return
    series = [
        (label, color, breakdown_series_common(idx, method, metric_suffix, common_keys))
        for label, color, method in methods
    ]
    plot_cactus(series, len(common_keys), filename)



def build_slot_comparisons():
    """Compare both solvers using current breakdown data and shared benchmarks."""
    z3_idx = load_breakdown_index(Z3_BREAKDOWN_CSV)
    cvc5_idx = load_breakdown_index(CVC5_BREAKDOWN_CSV)
    methods = [
        ("ThunderFork–Z3", ORANGE, z3_idx, "chain"),
        ("SLOT–Z3", BLUE, z3_idx, "slot"),
        ("ThunderFork–cvc5", AQUA, cvc5_idx, "chain"),
        ("SLOT–cvc5", PURPLE, cvc5_idx, "slot"),
    ]
    for metric_suffix, metric_tag in [
        ("solver_time", "solver"), ("total_seconds", "total"),
    ]:
        common_keys = [
            key for key in sorted(z3_idx.keys() & cvc5_idx.keys())
            if all(parse_time(idx[key], f"{method}_{metric_suffix}") is not None
                   for _, _, idx, method in methods)
        ]
        filename = f"thunderfork_vs_slot_{metric_tag}.pdf"
        if not common_keys:
            print(f"skipped {filename} (no paired data)")
            continue
        print(f"SLOT comparison: {len(common_keys)} shared benchmarks with all four timings "
              f"(Z3 has {len(z3_idx)} inputs; cvc5 has {len(cvc5_idx)} inputs)")
        series = [
            (label, color, breakdown_series_common(idx, method, metric_suffix, common_keys))
            for label, color, idx, method in methods
        ]
        plot_cactus(series, len(common_keys), filename, legend_loc="upper left")


def plot_z3_baseline(z3_idx, z3_variants_idx, metric_suffix, metric_tag):
    common_keys = sorted(z3_idx.keys() & z3_variants_idx.keys())
    series = [
        ("ThunderFork", ORANGE, breakdown_series_common(z3_idx, "chain", metric_suffix, common_keys)),
        ("z3 baseline", BLUE, variant_series_common(z3_variants_idx, "time-z3", "result-z3", common_keys)),
        ("z3 + simplify-split-clause", AQUA,
         variant_series_common(z3_variants_idx, "time-simplify-split-clause", "result-simplify-split-clause", common_keys)),
    ]
    plot_cactus(series, len(common_keys),
                f"z3_cactus_baseline_{metric_tag}.pdf", legend_loc="upper left")


def build_requested_comparisons():
    build_slot_comparisons()
    z3_idx = load_breakdown_index(Z3_BREAKDOWN_CSV)
    z3_variants_idx = load_variants_index(Z3_VARIANTS_CSV)
    for metric_suffix, metric_tag in [("solver_time", "solver"), ("total_seconds", "total")]:
        plot_z3_baseline(z3_idx, z3_variants_idx, metric_suffix, metric_tag)


def build_and_plot():
    build_slot_comparisons()
    z3_idx = load_breakdown_index(Z3_BREAKDOWN_CSV)
    cvc5_idx = load_breakdown_index(CVC5_BREAKDOWN_CSV)
    z3_variants_idx = load_variants_index(Z3_VARIANTS_CSV)
    cvc5_variants_idx = load_variants_index(CVC5_VARIANTS_CSV)

    # --- chain vs baseline solvers: restrict to benchmarks common to the
    # breakdown CSV and the variants CSV, so every line shares one denominator. ---
    cvc5_common = sorted(cvc5_idx.keys() & cvc5_variants_idx.keys())

    for metric_suffix, metric_tag in [
        ("solver_time", "solver"), ("total_seconds", "total"),
    ]:
        # --- Four ThunderFork strategies, all drawn from the
        # same breakdown CSV, so "attempted" is that CSV's own benchmark count. ---
        for solver_name, idx in [("z3", z3_idx), ("cvc5", cvc5_idx)]:
            plot_chain_sink(idx, solver_name, metric_suffix, metric_tag)
            series = [
                (label, color, method_series(idx, method, metric_suffix))
                for label, color, method in THUNDERFORK_METHODS
            ]
            plot_cactus(
                series, len(idx),
                f"{solver_name}_cactus_chain_vs_chained_single_query_{metric_tag}.pdf",
            )

        plot_z3_baseline(z3_idx, z3_variants_idx, metric_suffix, metric_tag)

        cvc5_series = [
            ("ThunderFork", ORANGE, breakdown_series_common(cvc5_idx, "chain", metric_suffix, cvc5_common)),
            ("cvc5 baseline", BLUE, variant_series_common(cvc5_variants_idx, "time-cvc5", "result-cvc5", cvc5_common)),
            ("cvc5 + ite", AQUA,
             variant_series_common(cvc5_variants_idx, "time-cvc5-ite", "result-cvc5-ite", cvc5_common)),
            ("cvc5 + ite-heuristics", YELLOW,
             variant_series_common(cvc5_variants_idx, "time-cvc5-ite-heuristics", "result-cvc5-ite-heuristics", cvc5_common)),
        ]
        plot_cactus(cvc5_series, len(cvc5_common),
                    f"cvc5_cactus_baseline_{metric_tag}.pdf", legend_loc="upper left")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--slot-only", action="store_true",
                        help="generate only ThunderFork versus SLOT plots")
    selection.add_argument("--requested-only", action="store_true",
                           help="generate ThunderFork versus Z3 configurations and SLOT, in PDF and PNG")
    parser.add_argument("--poster", action="store_true",
                        help="save 25 cm wide figures with print-sized text in graphs/poster")
    args = parser.parse_args()
    POSTER_MODE = args.poster
    if args.slot_only:
        build_slot_comparisons()
    elif args.requested_only:
        build_requested_comparisons()
    else:
        build_and_plot()
