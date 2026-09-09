#!/usr/bin/env python3
"""Paired runtime scatter plots, log-log, one point per benchmark.

Reads:
  - ../scripts/time_breakdown_z3.csv   (slot/chain/... generation, solved with z3)
  - ../scripts/time_breakdown_cvc5.csv (slot/chain/... generation, solved with cvc5)
  - ../z3-variants.csv                 (z3 baseline + z3 flag variant, direct on .smt2)
  - ../cvc5-variants.csv               (cvc5 baseline + cvc5 flag variants, direct on .smt2)

Writes PDFs into this directory, one per comparison (see COMPARISONS below):
  z3_slot_vs_chain_{solver,total}.pdf
  z3_chain_vs_chained_single_query_{solver,total}.pdf
  z3_chain_vs_z3baseline_{solver,total}.pdf
  z3_chain_vs_z3flag_{solver,total}.pdf
  cvc5_slot_vs_chain_{solver,total}.pdf
  cvc5_chain_vs_chained_single_query_{solver,total}.pdf
  cvc5_chain_vs_cvc5baseline_{solver,total}.pdf
  cvc5_chain_vs_cvc5ite_{solver,total}.pdf
  cvc5_chain_vs_cvc5iteheur_{solver,total}.pdf

Points use the usual |diff| magnitude tiers, including pairs where only one
approach timed out (their position already conveys the timeout). Unknown
(crashed/bailed) results retain a distinct marker. Pairs where both approaches
timed out are omitted and counted in the legend.
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

GRAPHS_DIR = Path(__file__).parent
ROOT_DIR = GRAPHS_DIR.parent

Z3_BREAKDOWN_CSV = ROOT_DIR / "scripts" / "time_breakdown-llvm22-z3.csv"
CVC5_BREAKDOWN_CSV = ROOT_DIR / "scripts" / "time_breakdown-llvm22-cvc5.csv"
Z3_VARIANTS_CSV = ROOT_DIR / "z3-variants.csv"
CVC5_VARIANTS_CSV = ROOT_DIR / "cvc5-variants.csv"

# palette (dataviz skill defaults, light surface)
SURFACE = "#ffffff"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
BASELINE = "#c3c2b7"

# normal (sat/unsat) points: orange marks near-equal runs; blue marks
# comparisons with a meaningful absolute difference
NEAR_EQUAL_COLOR = "#eb6834"
REGULAR_COLOR = "#2a78d6"
REF_RED = "#e34948"          # 2x / 0.5x reference lines

# result-status override
UNKNOWN_COLOR = "#7a5c99"    # purple x: solver bailed out with "unknown"

CLOSE_THRESHOLD_SECONDS = 1.0

SOLVED_RESULTS = {"sat", "unsat"}
TIMEOUT_SECONDS = 650.0


def normalize_benchmark_from_input(input_path):
    marker = "slot-benchmark-sat-with-select/"
    idx = input_path.find(marker)
    s = input_path[idx + len(marker):] if idx != -1 else input_path
    if s.endswith(".smt2"):
        s = s[:-len(".smt2")]
    return s.strip("/")


def load_breakdown_index(path):
    idx = {}
    with path.open() as f:
        for row in csv.DictReader(f):
            inp = row.get("input", "")
            if not inp:
                continue
            idx[normalize_benchmark_from_input(inp)] = row
    return idx


def load_variants_index(path):
    idx = {}
    with path.open() as f:
        for row in csv.DictReader(f):
            key = (row.get("benchmark") or "").strip().strip("/")
            if not key:
                continue
            idx[key] = row
    return idx


def parse_time(row, col):
    value = (row.get(col) or "").strip()
    return float(value) if value else None


def breakdown_method(time_col):
    for suffix in ("_solver_time", "_total_seconds"):
        if time_col.endswith(suffix):
            return time_col[:-len(suffix)]
    raise ValueError(f"not a breakdown time column: {time_col}")


def breakdown_result(row, time_col):
    """Return timeout when either related breakdown time exceeds 650s."""
    method = breakdown_method(time_col)
    solver_time = parse_time(row, f"{method}_solver_time")
    total_time = parse_time(row, f"{method}_total_seconds")
    if any(value is not None and value > TIMEOUT_SECONDS
           for value in (solver_time, total_time)):
        return "timeout"
    return None


def variant_result(row, time_col, status_col):
    """Combine an explicit result with an implicit runtime timeout."""
    value = parse_time(row, time_col)
    status = (row.get(status_col) or "").strip().lower()
    if status == "timeout" or (value is not None and value > TIMEOUT_SECONDS):
        return "timeout"
    if status in SOLVED_RESULTS:
        return None
    return "unknown"


def paired_same_source(idx, y_col, x_col):
    xs, ys, statuses = [], [], []
    for row in idx.values():
        xv, yv = row.get(x_col, ""), row.get(y_col, "")
        if not xv or not yv:
            continue
        xv, yv = float(xv), float(yv)
        if xv <= 0 or yv <= 0:
            continue
        xs.append(xv)
        ys.append(yv)
        statuses.append((breakdown_result(row, x_col), breakdown_result(row, y_col)))
    return xs, ys, statuses


def paired_cross_source(idx_y, y_col, idx_x, x_col, status_col):
    xs, ys, statuses = [], [], []
    for bench in idx_y.keys() & idx_x.keys():
        yv = idx_y[bench].get(y_col, "")
        xrow = idx_x[bench]
        xv = xrow.get(x_col, "")
        if not xv or not yv:
            continue
        xv, yv = float(xv), float(yv)
        if xv <= 0 or yv <= 0:
            continue
        xs.append(xv)
        ys.append(yv)
        statuses.append((variant_result(xrow, x_col, status_col),
                         breakdown_result(idx_y[bench], y_col)))
    return xs, ys, statuses


def classify(statuses):
    """Separate jointly timed-out and unknown pairs from plotted normal points."""
    normal, both_timeout, unknown = [], [], []
    for i, (x_status, y_status) in enumerate(statuses):
        if x_status == "timeout" and y_status == "timeout":
            both_timeout.append(i)
        elif x_status == "unknown" or y_status == "unknown":
            unknown.append(i)
        else:
            normal.append(i)
    return normal, both_timeout, unknown


def plot_metric(xs, ys, statuses, y_label, x_label, filename):
    total_pairs = len(xs)
    if total_pairs == 0:
        print(f"skipped {filename} (no paired data)")
        return

    normal_idx, both_timeout_idx, unknown_idx = classify(statuses)
    both_timeout_set = set(both_timeout_idx)
    plotted_idx = [i for i in range(total_pairs) if i not in both_timeout_set]
    plotted_count = len(plotted_idx)

    meaningful_idx = [i for i in plotted_idx
                      if abs(ys[i] - xs[i]) >= CLOSE_THRESHOLD_SECONDS]
    y_faster = sum(1 for i in meaningful_idx if ys[i] < xs[i])
    x_faster = sum(1 for i in meaningful_idx if ys[i] > xs[i])

    near_equal = [(xs[i], ys[i]) for i in normal_idx
                  if abs(ys[i] - xs[i]) < CLOSE_THRESHOLD_SECONDS]
    regular = [(xs[i], ys[i]) for i in normal_idx
               if abs(ys[i] - xs[i]) >= CLOSE_THRESHOLD_SECONDS]
    unknown_pts = [(xs[i], ys[i]) for i in unknown_idx]

    if plotted_idx:
        plotted_values = [xs[i] for i in plotted_idx] + [ys[i] for i in plotted_idx]
        lo = min(plotted_values) * 0.7
        hi = max(plotted_values) * 1.4
    else:
        lo = 1.0
        hi = TIMEOUT_SECONDS * 1.4

    fig, ax = plt.subplots(figsize=(7, 7), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    # reference lines: y=x, y=2x, y=x/2 (constant ratio -> straight on log-log)
    ax.plot([lo, hi], [lo, hi], color=BASELINE, linewidth=1.5, zorder=1)
    ax.plot([lo, hi], [lo * 2, hi * 2], color=REF_RED, linewidth=1.3, linestyle=(0, (4, 3)), zorder=2)
    ax.plot([lo, hi], [lo / 2, hi / 2], color=REF_RED, linewidth=1.3, linestyle=(0, (4, 3)), zorder=2)

    x2_label = hi / 2 * 0.88
    ax.annotate("2×", (x2_label, 2 * x2_label), xytext=(0, 6), textcoords="offset points",
                color=REF_RED, fontsize=9, ha="center", va="bottom")
    y05_label = hi / 2 * 0.88
    ax.annotate("0.5×", (2 * y05_label, y05_label), xytext=(6, 0), textcoords="offset points",
                color=REF_RED, fontsize=9, ha="left", va="center")

    if near_equal:
        nx, ny = zip(*near_equal)
        ax.scatter(nx, ny, s=70, color=NEAR_EQUAL_COLOR, alpha=0.9, marker="s",
                   edgecolors=SURFACE, linewidths=1, zorder=3)
    if regular:
        rx, ry = zip(*regular)
        ax.scatter(rx, ry, s=70, color=REGULAR_COLOR, alpha=0.9, marker="o",
                   edgecolors=SURFACE, linewidths=1, zorder=4)
    if unknown_pts:
        ux, uy = zip(*unknown_pts)
        ax.scatter(ux, uy, s=80, color=UNKNOWN_COLOR, alpha=0.9, marker="x",
                   linewidths=2, zorder=7)

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_aspect("equal")

    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:g}"))

    ax.set_xlabel(f"{x_label} (seconds, log scale)", color=INK_SECONDARY, fontsize=12)
    ax.set_ylabel(f"{y_label} (seconds, log scale)", color=INK_SECONDARY, fontsize=12)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(BASELINE)

    summary_lines = []
    if both_timeout_idx:
        summary_lines.append(f"Both timeout: {len(both_timeout_idx)}")
    summary_lines.extend([
        f"{y_label} faster (difference ≥ 1s): {y_faster}",
        f"{x_label} faster (difference ≥ 1s): {x_faster}",
    ])
    ax.text(0.98, 0.03, "\n".join(summary_lines), transform=ax.transAxes,
            color=INK_SECONDARY, fontsize=11, ha="right", va="bottom",
            linespacing=1.3)

    legend_handles = [
        Patch(facecolor=NEAR_EQUAL_COLOR, edgecolor="none",
              label=f"|Δ| < {CLOSE_THRESHOLD_SECONDS:g}s ({len(near_equal)})"),
        Line2D([0], [0], color=BASELINE, linewidth=1.5, label="y = x (equal)"),
        Line2D([0], [0], color=REF_RED, linewidth=1.3, linestyle=(0, (4, 3)), label="2× / 0.5× (double)"),
    ]
    if unknown_pts:
        legend_handles.append(Line2D([0], [0], marker="x", color=UNKNOWN_COLOR, markeredgecolor=UNKNOWN_COLOR,
                                      linestyle="none", markersize=8, markeredgewidth=2,
                                      label=f"Unknown/crashed ({len(unknown_pts)})"))
    ax.legend(handles=legend_handles, loc="upper left", ncol=1, frameon=True,
              facecolor=SURFACE, edgecolor="none", framealpha=0.9,
              fontsize=12, labelcolor=INK_SECONDARY,
              handlelength=1.6, columnspacing=1.3)

    fig.tight_layout()
    out_path = GRAPHS_DIR / filename
    fig.savefig(out_path, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path} (pairs={total_pairs}, plotted={plotted_count}, "
          f"{y_label} faster={y_faster}, {x_label} faster={x_faster}, "
          f"both-timeout={len(both_timeout_idx)}, unknown={len(unknown_pts)})")


# same-source comparisons: (y_method, x_method, y_label, x_label, name)
# both sides come from the same breakdown CSV (generated+solved with one solver)
SAME_SOURCE = [
    ("slot", "chain", "Slot", "ThunderFork", "slot_vs_chain"),
    ("chain", "chained_single_query", "ThunderFork-Parallel", "ThunderFork-Single-Query",
     "chain_vs_chained_single_query"),
]

# cross-source comparisons per solver: chain vs a variant solved directly on
# the .smt2 (time_col, status_col, x_label, tag)
CROSS_SOURCE = {
    "z3": [
        ("time-z3", "result-z3", "Z3 baseline", "z3baseline"),
        ("time-simplify-split-clause", "result-simplify-split-clause",
         "Z3 + simplify-split-clause", "z3flag"),
    ],
    "cvc5": [
        ("time-cvc5", "result-cvc5", "CVC5 baseline", "cvc5baseline"),
        ("time-cvc5-ite", "result-cvc5-ite", "CVC5 + ite", "cvc5ite"),
        ("time-cvc5-ite-heuristics", "result-cvc5-ite-heuristics",
         "CVC5 + ite-heuristics", "cvc5iteheur"),
    ],
}

METRICS = [("solver_time", "solver"), ("total_seconds", "total")]


def build_comparisons():
    solvers = [
        ("z3", load_breakdown_index(Z3_BREAKDOWN_CSV), load_variants_index(Z3_VARIANTS_CSV)),
        ("cvc5", load_breakdown_index(CVC5_BREAKDOWN_CSV), load_variants_index(CVC5_VARIANTS_CSV)),
    ]

    comparisons = []
    for solver_name, idx, variants_idx in solvers:
        for metric_suffix, metric_tag in METRICS:
            for y_method, x_method, y_label, x_label, name in SAME_SOURCE:
                xs, ys, statuses = paired_same_source(
                    idx, f"{y_method}_{metric_suffix}", f"{x_method}_{metric_suffix}")
                comparisons.append((xs, ys, statuses, y_label, x_label,
                                     f"{solver_name}_{name}_{metric_tag}.pdf"))

            y_col = f"chain_{metric_suffix}"
            y_label = f"ThunderFork ({metric_tag})"
            for time_col, status_col, x_label, tag in CROSS_SOURCE[solver_name]:
                xs, ys, statuses = paired_cross_source(idx, y_col, variants_idx, time_col, status_col)
                comparisons.append((xs, ys, statuses, y_label, x_label,
                                     f"{solver_name}_chain_vs_{tag}_{metric_tag}.pdf"))

    return comparisons


def main():
    for xs, ys, statuses, y_label, x_label, filename in build_comparisons():
        plot_metric(xs, ys, statuses, y_label, x_label, filename)


if __name__ == "__main__":
    main()
