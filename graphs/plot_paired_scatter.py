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
  z3_chain_vs_chain_sink_{solver,total}.pdf
  z3_chain_vs_z3baseline_{solver,total}.pdf
  z3_chain_vs_z3flag_{solver,total}.pdf
  cvc5_slot_vs_chain_{solver,total}.pdf
  cvc5_chain_vs_chained_single_query_{solver,total}.pdf
  cvc5_chain_vs_chain_sink_{solver,total}.pdf
  cvc5_chain_vs_cvc5baseline_{solver,total}.pdf
  cvc5_chain_vs_cvc5ite_{solver,total}.pdf
  cvc5_chain_vs_cvc5iteheur_{solver,total}.pdf

Points use the usual |diff| magnitude tiers, including pairs where only one
approach timed out (their position already conveys the timeout). Unknown
(crashed/bailed) results retain a distinct marker. Pairs where both approaches
timed out are omitted and counted in the legend.
"""
import argparse
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
POSTER_MODE = False
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
    s = input_path
    for marker in ("slot-benchmark-sat-with-select/", "slot-benchmarks/"):
        idx = input_path.find(marker)
        if idx != -1:
            s = input_path[idx + len(marker):]
            break
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
    normal_idx = [i for i in normal_idx if statuses[i] == (None, None)]
    both_timeout_set = set(both_timeout_idx)
    plotted_idx = [i for i in range(total_pairs) if i not in both_timeout_set]
    plotted_count = len(plotted_idx)

    meaningful_idx = [i for i in normal_idx
                      if abs(ys[i] - xs[i]) >= CLOSE_THRESHOLD_SECONDS]
    # A completed run wins against a timeout, regardless of recorded elapsed time.
    y_timeout_wins = sum(status == ("timeout", None) for status in statuses)
    x_timeout_wins = sum(status == (None, "timeout") for status in statuses)
    y_faster = sum(1 for i in meaningful_idx if ys[i] < xs[i]) + y_timeout_wins
    x_faster = sum(1 for i in meaningful_idx if ys[i] > xs[i]) + x_timeout_wins

    near_equal = [(xs[i], ys[i]) for i in normal_idx
                  if abs(ys[i] - xs[i]) < CLOSE_THRESHOLD_SECONDS]
    regular = [(xs[i], ys[i]) for i in normal_idx
               if abs(ys[i] - xs[i]) >= CLOSE_THRESHOLD_SECONDS]
    unknown_pts = [(xs[i], ys[i]) for i in unknown_idx]
    timeout_idx = [i for i in plotted_idx if "timeout" in statuses[i]
                   and i not in unknown_idx]
    timeout_pts = [(xs[i], ys[i]) for i in timeout_idx]

    if plotted_idx:
        plotted_values = [xs[i] for i in plotted_idx] + [ys[i] for i in plotted_idx]
        lo = min(plotted_values) * 0.7
        hi = max(plotted_values) * 1.4
    else:
        lo = 1.0
        hi = TIMEOUT_SECONDS * 1.4

    if POSTER_MODE:
        fig = plt.figure(figsize=(25 / 2.54, 34 / 2.54), dpi=150)
        ax = fig.add_axes((0.18, 0.36, 0.77, 0.77 * 25 / 34))
    else:
        fig, ax = plt.subplots(figsize=(20, 20), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    # reference lines: y=x, y=2x, y=x/2 (constant ratio -> straight on log-log)
    ax.plot([lo, hi], [lo, hi], color=BASELINE, linewidth=3, zorder=1)
    ax.plot([lo, hi], [lo * 2, hi * 2], color=REF_RED, linewidth=3, linestyle=(0, (4, 3)), zorder=2)
    ax.plot([lo, hi], [lo / 2, hi / 2], color=REF_RED, linewidth=3, linestyle=(0, (4, 3)), zorder=2)

    x2_label = hi / 4 if POSTER_MODE else hi / 2 * 0.88
    ax.annotate("2×", (x2_label, 2 * x2_label), xytext=(0, 6), textcoords="offset points",
                color=REF_RED, fontsize=24 if POSTER_MODE else 30, ha="center", va="bottom")
    y05_label = hi / 4 if POSTER_MODE else hi / 2 * 0.88
    ax.annotate("0.5×", (2 * y05_label, y05_label), xytext=(6, 0), textcoords="offset points",
                color=REF_RED, fontsize=24 if POSTER_MODE else 30, ha="left", va="center")

    if near_equal:
        nx, ny = zip(*near_equal)
        ax.scatter(nx, ny, s=110 if POSTER_MODE else 70, color=NEAR_EQUAL_COLOR, alpha=0.9, marker="s",
                   edgecolors=SURFACE, linewidths=1, zorder=3)
    if regular:
        rx, ry = zip(*regular)
        ax.scatter(rx, ry, s=110 if POSTER_MODE else 70, color=REGULAR_COLOR, alpha=0.9, marker="o",
                   edgecolors=SURFACE, linewidths=1, zorder=4)
    if timeout_pts:
        tx, ty = zip(*timeout_pts)
        ax.scatter(tx, ty, s=120 if POSTER_MODE else 85, facecolors="none", edgecolors=REGULAR_COLOR,
                   marker="^", linewidths=1.5, zorder=6)
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

    axis_color = "#222222" if POSTER_MODE else INK_SECONDARY
    ax.set_xlabel(f"{x_label} time (s)" if POSTER_MODE else
                  f"{x_label} (seconds, log scale)", color=axis_color,
                  fontsize=26 if POSTER_MODE else 30)
    poster_y_label = y_label.replace(" (", " ").replace(")", "")
    ax.set_ylabel(f"{poster_y_label} time (s)" if POSTER_MODE else
                  f"{y_label} (seconds, log scale)", color=axis_color,
                  fontsize=26 if POSTER_MODE else 30)
    ax.tick_params(colors="#222222" if POSTER_MODE else INK_MUTED,
                   labelsize=24 if POSTER_MODE else 30)
    if POSTER_MODE:
        ax.xaxis.set_major_locator(mticker.LogLocator(base=10, numticks=5))
        ax.yaxis.set_major_locator(mticker.LogLocator(base=10, numticks=5))
    for spine in ax.spines.values():
        spine.set_color(BASELINE)

    summary_lines = [f"Both solved: {len(normal_idx)}/{total_pairs}"]
    if both_timeout_idx:
        summary_lines.append(f"Both timeout: {len(both_timeout_idx)}")
    summary_lines.extend([
        f"{y_label} faster: {y_faster} ({y_timeout_wins} timeout wins)",
        f"{x_label} faster: {x_faster} ({x_timeout_wins} timeout wins)",
        f"Both solved: faster requires ≥ {CLOSE_THRESHOLD_SECONDS:g}s difference",
    ])
    if POSTER_MODE:
        native_label = x_label.replace("Pure ", "")
        summary = (f"ThunderFork wins: {y_faster} · {native_label} wins: {x_faster}\n"
                   f"Ties (<1 s): {len(near_equal)} · Both timeout: {len(both_timeout_idx)}\n"
                   "Wins include solved vs timeout.\n"
                   "Timeouts shown at recorded limits.")
        fig.text(0.18, 0.07, summary, color="#222222", fontsize=24,
                 ha="left", va="bottom", linespacing=1.3)
    else:
        ax.text(0.98, 0.03, "\n".join(summary_lines), transform=ax.transAxes,
                color=INK_SECONDARY, fontsize=30, ha="right", va="bottom",
                linespacing=1.3)

    legend_handles = [
        Patch(facecolor=NEAR_EQUAL_COLOR, edgecolor="none",
              label=f"|Δ| < {CLOSE_THRESHOLD_SECONDS:g}s ({len(near_equal)})"),
        Line2D([0], [0], color=BASELINE, linewidth=3, label="y = x (equal)"),
        Line2D([0], [0], color=REF_RED, linewidth=3, linestyle=(0, (4, 3)), label="2× / 0.5× (double)"),
    ]
    if timeout_pts:
        legend_handles.append(Line2D([0], [0], marker="^", color=REGULAR_COLOR,
                                      markerfacecolor="none", linestyle="none", markersize=8,
                                      label=f"One timeout: recorded time is a lower bound ({len(timeout_pts)})"))
    if unknown_pts:
        legend_handles.append(Line2D([0], [0], marker="x", color=UNKNOWN_COLOR, markeredgecolor=UNKNOWN_COLOR,
                                      linestyle="none", markersize=8, markeredgewidth=2,
                                      label=f"Unknown/crashed ({len(unknown_pts)})"))
    if POSTER_MODE:
        legend_handles[0].set_label(f"Tie (<1 s): {len(near_equal)}")
        legend_handles[1].set_label("Equal time")
        legend_handles[2].set_label("2× / 0.5×")
        if timeout_pts:
            legend_handles[3].set_label(f"Timeout: {len(timeout_pts)}")
        fig.legend(handles=legend_handles, loc="upper left",
                   bbox_to_anchor=(0.16, 0.30), ncol=2, frameon=False,
                   fontsize=24, labelcolor="#222222", handlelength=1.3,
                   columnspacing=0.8)
    else:
        ax.legend(handles=legend_handles, loc="upper left", ncol=1, frameon=True,
                  facecolor=SURFACE, edgecolor="none", framealpha=0.9,
                  fontsize=30, labelcolor=INK_SECONDARY,
                  handlelength=1.6, columnspacing=1.3)
        fig.tight_layout()

    output_dir = GRAPHS_DIR / "poster" if POSTER_MODE else GRAPHS_DIR
    output_dir.mkdir(exist_ok=True)
    for extension in (".pdf", ".png"):
        out_path = (output_dir / filename).with_suffix(extension)
        fig.savefig(out_path, facecolor=SURFACE,
                    bbox_inches=None if POSTER_MODE else "tight",
                    dpi=300 if POSTER_MODE else 200)
        print(f"wrote {out_path}")
    plt.close(fig)
    print(f"Comparison (pairs={total_pairs}, plotted={plotted_count}, "
          f"{y_label} faster={y_faster}, {x_label} faster={x_faster}, "
          f"both-timeout={len(both_timeout_idx)}, unknown={len(unknown_pts)})")


# same-source comparisons: (y_method, x_method, y_label, x_label, name)
# both sides come from the same breakdown CSV (generated+solved with one solver)
SAME_SOURCE = [
    ("slot", "chain", "Slot", "ThunderFork", "slot_vs_chain"),
    ("chain", "chain_sink", "ThunderFork-Parallel", "ThunderFork-Parallel + Sink",
     "chain_vs_chain_sink"),
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


def build_comparisons(z3_baseline_only=False, cvc5_baseline_only=False):
    if z3_baseline_only or cvc5_baseline_only:
        solver = "z3" if z3_baseline_only else "cvc5"
        breakdown_path = Z3_BREAKDOWN_CSV if z3_baseline_only else CVC5_BREAKDOWN_CSV
        variants_path = Z3_VARIANTS_CSV if z3_baseline_only else CVC5_VARIANTS_CSV
        idx = load_breakdown_index(breakdown_path)
        variants_idx = load_variants_index(variants_path)
        comparisons = []
        for metric_suffix, metric_tag in METRICS:
            xs, ys, statuses = paired_cross_source(
                idx, f"chain_{metric_suffix}", variants_idx, f"time-{solver}", f"result-{solver}")
            comparisons.append((xs, ys, statuses, f"ThunderFork ({metric_tag})", f"Pure {solver.upper()}",
                                f"{solver}_chain_vs_{solver}baseline_{metric_tag}.pdf"))
        return comparisons

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
    global POSTER_MODE
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--z3-baseline-only", action="store_true",
                        help="compare pure Z3 with ThunderFork, using solver and total times")
    selection.add_argument("--cvc5-baseline-only", action="store_true",
                          help="compare pure cvc5 with ThunderFork, using solver and total times")
    parser.add_argument("--poster", action="store_true",
                        help="save 25 cm wide figures with print-sized text in graphs/poster")
    args = parser.parse_args()
    POSTER_MODE = args.poster
    for xs, ys, statuses, y_label, x_label, filename in build_comparisons(
            args.z3_baseline_only, args.cvc5_baseline_only):
        plot_metric(xs, ys, statuses, y_label, x_label, filename)


if __name__ == "__main__":
    main()
