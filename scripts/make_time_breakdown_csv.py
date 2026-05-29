#!/usr/bin/env python3
import csv
import re
import sys
from pathlib import Path

STRATEGIES = ["first", "last", "random", "all-bfs", "all-dfs"]
SLOT_LOG = "slot-optimized-time.log"


def parse_time_file(path):
    data = {}
    for line in path.read_text().splitlines():
        if line.startswith("input="):
            data["input"] = line.removeprefix("input=")
        elif m := re.match(r"^smt_to_ll\b.*\belapsed_ms=(\d+)", line):
            data["smt_to_ll"] = int(m.group(1)) / 1000
        elif m := re.match(r"^strategy=(\S+)\s+elapsed_ms=(\d+)", line):
            data[m.group(1)] = int(m.group(2)) / 1000
    return data


def parse_slot_log(path):
    if not path.exists():
        return {}
    timings = {}
    benchmark, is_slot_opt = None, False
    for line in path.read_text().splitlines():
        if m := re.match(r"^=== benchmark (.+): (.+) ===$", line):
            benchmark, is_slot_opt = m.group(1), m.group(2) == "slot-opt"
        elif is_slot_opt and benchmark:
            if m := re.search(r"\bz3_time_seconds=([0-9]+(?:\.[0-9]+)?)", line):
                timings[benchmark] = float(m.group(1))
    return timings


def fmt(val):
    return f"{val:g}" if val is not None else ""


def main():
    timing_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("select-results-strategies")
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("time_breakdown.csv")

    header = ["benchmark", "input", "smt_to_ll_seconds", "slot_time"]
    for s in STRATEGIES:
        header += [f"{s}_generation_seconds", f"{s}_total_seconds"]

    rows = []
    for time_file in sorted(timing_root.glob("*/time.txt"), key=lambda p: p.parent.name):
        benchmark = time_file.parent.name
        data = parse_time_file(time_file)
        slot = parse_slot_log(time_file.parent / SLOT_LOG)

        smt_to_ll = data.get("smt_to_ll")
        row = {
            "benchmark": benchmark,
            "input": data.get("input", ""),
            "smt_to_ll_seconds": fmt(smt_to_ll),
            "slot_time": fmt(slot.get(benchmark)),
        }
        for s in STRATEGIES:
            gen = data.get(s)
            total = smt_to_ll + gen if smt_to_ll is not None and gen is not None else None
            row[f"{s}_generation_seconds"] = fmt(gen)
            row[f"{s}_total_seconds"] = fmt(total)
        rows.append(row)

    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
```
