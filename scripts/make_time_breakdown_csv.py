#!/usr/bin/env python3
import csv
import re
import sys
from pathlib import Path

# (type_label, file_key) — file_key is used in log filenames
TYPES = [
    ("slot",    "opt"),
    ("chain",   "chain"),
    ("first",   "first"),
    ("last",    "last"),
    ("random",  "random"),
    ("all-bfs", "all-bfs"),
    ("all-dfs", "all-dfs"),
]
def parse_smt_to_ll(path):
    data = {}
    if not path.exists():
        return data
    for line in path.read_text().splitlines():
        if line.startswith("input="):
            data["input"] = line.removeprefix("input=")
        elif m := re.match(r"^elapsed_ms=(\d+)", line):
            data["elapsed_ms"] = int(m.group(1)) / 1000
    return data


def parse_generation_time(path):
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if m := re.match(r"^elapsed_ms=(\d+)", line):
            return int(m.group(1)) / 1000
    return None



def parse_solver_time(path, key):
    if not path.exists():
        return None
    text = path.read_text()
    if key == "opt":
        m = re.search(r"\bz3_time_seconds=([0-9]+(?:\.[0-9]+)?)", text)
    else:
        m = re.search(r"^Total time: ([0-9]+(?:\.[0-9]+)?)s$", text, re.MULTILINE)
    return float(m.group(1)) if m else None


def fmt(val):
    return f"{val:g}" if val is not None else ""


SCRIPT_DIR = Path(__file__).parent


def main():
    timing_root = Path(sys.argv[1]) if len(sys.argv) > 1 else SCRIPT_DIR.parent / "select-results-strategies"
    out_path    = Path(sys.argv[2]) if len(sys.argv) > 2 else SCRIPT_DIR / "time_breakdown.csv"

    labels = [t for t, _ in TYPES]
    header = (["benchmark", "input", "smt_to_ll_seconds"]
              + [f"{t}_generation_seconds" for t in labels]
              + [f"{t}_solver_time"        for t in labels]
              + [f"{t}_total_seconds"      for t in labels])

    rows = []
    for timing_csv in sorted(timing_root.glob("*/logs/pass-timings.csv"), key=lambda p: p.parent.parent.name):
        log_dir   = timing_csv.parent
        benchmark = timing_csv.parent.parent.name
        smt_data  = parse_smt_to_ll(log_dir / "smt-to-ll.txt")
        smt_t     = smt_data.get("elapsed_ms")

        row = {"benchmark": benchmark, "input": smt_data.get("input", ""), "smt_to_ll_seconds": fmt(smt_t)}

        for label, key in TYPES:
            gen = parse_generation_time(log_dir / f"time-{key}.txt")
            sol = parse_solver_time(log_dir / f"solver-{key}.log", key)
            total = (smt_t + gen + sol) if None not in (smt_t, gen, sol) else None
            row[f"{label}_generation_seconds"] = fmt(gen)
            row[f"{label}_solver_time"]        = fmt(sol)
            row[f"{label}_total_seconds"]      = fmt(total)

        rows.append(row)

    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
