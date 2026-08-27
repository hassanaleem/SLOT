#!/usr/bin/env python3
"""Build a status-aware time breakdown for the UNSAT benchmark sweep."""

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

METHODS = (("slot", "opt"), ("chain", "chain"))
EXPECTED_RESULT = "unsat"
FLOAT_RE = r"[0-9]+(?:\.[0-9]+)?"

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
DEFAULT_TIMING_ROOT = ROOT_DIR / "unsat"
DEFAULT_BENCHMARK_LIST = ROOT_DIR / "torun-unsat.txt"
DEFAULT_OUTPUT = SCRIPT_DIR / "time_breakdown_unsat.csv"


def parse_phase1(path):
    data = {}
    if not path.exists():
        return data
    for line in path.read_text().splitlines():
        if line.startswith("input="):
            data["input"] = line.removeprefix("input=")
        elif match := re.match(r"^elapsed_ms=(\d+)$", line):
            data["elapsed_seconds"] = int(match.group(1)) / 1000
        elif match := re.match(r"^num_selects=(\d+)$", line):
            data["num_selects"] = int(match.group(1))
    return data


def parse_generation_time(path):
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if match := re.match(r"^elapsed_ms=(\d+)$", line):
            return int(match.group(1)) / 1000
    return None


def normalize_result(token):
    if token in {"sat", "unsat", "timeout", "unknown", "no-output"}:
        return token
    if token.startswith("(error_"):
        return "error"
    return "error"


def parse_opt_log(path):
    if not path.exists():
        return {"time": None, "result": "", "solver": ""}

    text = path.read_text()
    match = re.search(
        rf"^query=\d+\s+(?P<solver>\S+)_result=(?P<result>\S+)\s+"
        rf"(?P=solver)_time_seconds=(?P<time>{FLOAT_RE})$",
        text,
        re.MULTILINE,
    )
    if not match:
        return {"time": None, "result": "incomplete", "solver": ""}

    return {
        "time": float(match.group("time")),
        "result": normalize_result(match.group("result")),
        "solver": match.group("solver"),
    }


def parse_parallel_log(path):
    """Parse a parallel run without trusting its misleading final summary.

    parallel_solver.py currently prints "No satisfying query found" after
    parse errors.  A completed UNSAT run therefore requires exactly the
    declared number of query results, with every result equal to UNSAT.
    """
    if not path.exists():
        return {"time": None, "result": "", "solver": ""}

    text = path.read_text()
    header = re.search(
        r"^\s*(\d+) queries, max \d+ workers, solver=(\S+)\s*$",
        text,
        re.MULTILINE,
    )
    raw_results = re.findall(
        rf"^\s*\[-\] query\s+\d+/\d+\s+result=(\S+)\s+"
        rf"elapsed={FLOAT_RE}s\s*$",
        text,
        re.MULTILINE,
    )
    total = re.search(rf"^Total time: ({FLOAT_RE})s$", text, re.MULTILINE)

    results = [normalize_result(result) for result in raw_results]
    declared_queries = int(header.group(1)) if header else None
    solver = header.group(2) if header else ""

    if "sat" in results:
        result = "sat"
    elif (re.search(rf"^Timeout after {FLOAT_RE}s", text, re.MULTILINE)
          or "timeout" in results):
        result = "timeout"
    elif (declared_queries is not None
          and len(results) == declared_queries
          and results
          and all(item == "unsat" for item in results)):
        result = "unsat"
    elif "error" in results:
        result = "error"
    elif "unknown" in results or "no-output" in results:
        result = "unknown"
    else:
        result = "incomplete"

    return {
        "time": float(total.group(1)) if total else None,
        "result": result,
        "solver": solver,
    }


def parse_solver_log(path, key):
    return parse_opt_log(path) if key == "opt" else parse_parallel_log(path)


def fmt(value):
    return f"{value:g}" if value is not None else ""


def load_manifest(path):
    entries = []
    seen = set()
    for raw_line in path.read_text().splitlines():
        input_path = raw_line.strip()
        if not input_path or input_path.startswith("#"):
            continue
        benchmark = Path(input_path).name
        if benchmark.endswith(".smt2"):
            benchmark = benchmark[:-len(".smt2")]
        if benchmark in seen:
            raise ValueError(f"duplicate benchmark basename in {path}: {benchmark}")
        seen.add(benchmark)
        entries.append((benchmark, input_path))
    return entries


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Collect the manifest-scoped UNSAT Slot/ThunderFork timings. "
            "Parse errors and other non-UNSAT outcomes retain a result status "
            "but do not receive numeric solver or total times."
        ),
    )
    parser.add_argument(
        "timing_root",
        nargs="?",
        type=Path,
        default=DEFAULT_TIMING_ROOT,
    )
    parser.add_argument(
        "out_path",
        nargs="?",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    parser.add_argument(
        "--benchmark-list",
        type=Path,
        default=DEFAULT_BENCHMARK_LIST,
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.timing_root.is_dir():
        raise SystemExit(f"timing root is not a directory: {args.timing_root}")
    if not args.benchmark_list.is_file():
        raise SystemExit(f"benchmark list is not a file: {args.benchmark_list}")

    labels = [label for label, _ in METHODS]
    header = (
        ["benchmark", "input", "num_selects", "smt_to_ll_seconds"]
        + [f"{label}_generation_seconds" for label in labels]
        + [f"{label}_solver" for label in labels]
        + [f"{label}_result" for label in labels]
        + [f"{label}_solver_time" for label in labels]
        + [f"{label}_total_seconds" for label in labels]
    )

    rows = []
    observed_solvers = set()
    status_counts = {label: Counter() for label in labels}
    eligible_count = 0

    for benchmark, manifest_input in load_manifest(args.benchmark_list):
        log_dir = args.timing_root / benchmark / "logs"
        phase1 = parse_phase1(log_dir / "smt-to-ll.txt")
        smt_time = phase1.get("elapsed_seconds")
        num_selects = phase1.get("num_selects")
        eligible = num_selects is not None and num_selects > 0
        if eligible:
            eligible_count += 1

        row = {
            "benchmark": benchmark,
            "input": phase1.get("input", manifest_input),
            "num_selects": "" if num_selects is None else num_selects,
            "smt_to_ll_seconds": fmt(smt_time),
        }

        for label, key in METHODS:
            generation_time = None
            solver_run = {"time": None, "result": "", "solver": ""}
            if eligible:
                generation_time = parse_generation_time(
                    log_dir / f"time-{key}.txt"
                )
                solver_run = parse_solver_log(
                    log_dir / f"solver-{key}.log", key
                )

            result = solver_run["result"]
            solver = solver_run["solver"]
            if solver:
                observed_solvers.add(solver)
            if eligible:
                status_counts[label][result or "missing"] += 1

            solver_time = solver_run["time"]
            if result not in {EXPECTED_RESULT, "timeout"}:
                solver_time = None
            total_time = (
                smt_time + generation_time + solver_time
                if None not in (smt_time, generation_time, solver_time)
                else None
            )

            row[f"{label}_generation_seconds"] = fmt(generation_time)
            row[f"{label}_solver"] = solver
            row[f"{label}_result"] = result
            row[f"{label}_solver_time"] = fmt(solver_time)
            row[f"{label}_total_seconds"] = fmt(total_time)

        rows.append(row)

    if len(observed_solvers) > 1:
        names = ", ".join(sorted(observed_solvers))
        raise SystemExit(
            f"refusing to combine multiple solvers in one CSV: {names}"
        )

    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    with args.out_path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)

    solver_summary = next(iter(observed_solvers), "none")
    print(
        f"wrote {len(rows)} manifest rows to {args.out_path} "
        f"(select-eligible={eligible_count}, solver={solver_summary})"
    )
    for label in labels:
        summary = ", ".join(
            f"{status}={count}"
            for status, count in sorted(status_counts[label].items())
        )
        print(f"  {label}: {summary}")


if __name__ == "__main__":
    main()
