#!/usr/bin/env python3
"""
Bounded-parallel SMT solver runtime.

Splits a .smt2 file into individual queries, runs up to MAX_WORKERS solver
instances concurrently. Stops and reports on the first SAT result.
"""

import os
import sys
import time
import signal
import subprocess
import tempfile
import argparse
from collections import deque
from pathlib import Path

MAX_WORKERS = 10

SOLVERS_DIR = Path(__file__).resolve().parent.parent / "solvers"
SUPPORTED_SOLVERS = ["z3", "cvc5", "mathsat", "opensmt"]


def extract_queries(smt2_file: Path, tmpdir: Path) -> list[Path]:
    queries: list[Path] = []
    state_lines: list[str] = []
    count = 0
    with open(smt2_file) as f:
        for line in f:
            stripped = line.rstrip("\n")
            if stripped == "(check-sat)":
                count += 1
                qfile = tmpdir / f"query_{count}.smt2"
                with open(qfile, "w") as qf:
                    qf.writelines(state_lines)
                    qf.write(stripped + "\n")
                queries.append(qfile)
            elif stripped == "(reset)":
                state_lines = []
            else:
                state_lines.append(line)
    return queries


def start_worker(idx: int, query_file: Path, solver_script: Path) -> dict:
    proc = subprocess.Popen(
        [str(solver_script), str(query_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        preexec_fn=os.setsid,
    )
    return {"proc": proc, "index": idx, "file": query_file}


def kill_worker(worker: dict) -> None:
    try:
        os.killpg(worker["proc"].pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def parse_result(stdout: str, solver: str) -> str:
    prefix = f"{solver}_result="
    for line in stdout.splitlines():
        for token in line.split():
            if token.startswith(prefix):
                return token[len(prefix):]
    return "unknown"


def run(smt2_file: Path, solver: str, max_workers: int = MAX_WORKERS) -> int:
    solver_script = SOLVERS_DIR / f"{solver}.sh"
    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = Path(_tmpdir)
        print(f"Extracting queries from {smt2_file} …")
        queries = extract_queries(smt2_file, tmpdir)
        if not queries:
            print("No (check-sat) queries found.", file=sys.stderr)
            return 1

        n = len(queries)
        width = len(str(n))
        print(f"  {n} queries, max {max_workers} workers, solver={solver}")

        pending: deque[tuple[int, Path]] = deque(enumerate(queries, start=1))
        active: dict[int, dict] = {}
        global_start = time.perf_counter()

        def fill_slots() -> None:
            while pending and len(active) < max_workers:
                idx, qfile = pending.popleft()
                worker = start_worker(idx, qfile, solver_script)
                active[worker["proc"].pid] = worker
                print(f"  [+] query {idx:>{width}}/{n}  pid={worker['proc'].pid}")

        fill_slots()

        while active:
            done = [pid for pid, w in active.items() if w["proc"].poll() is not None]
            if not done:
                continue

            for pid in done:
                worker = active.pop(pid)
                stdout, _ = worker["proc"].communicate()
                result = parse_result(stdout, solver)
                elapsed = time.perf_counter() - global_start
                print(f"  [-] query {worker['index']:>{width}}/{n}  result={result:<7}  elapsed={elapsed:.3f}s")

                if result == "sat":
                    print(f"\nSAT — query {worker['index']} ({worker['file'].name})")
                    print(f"Total time: {elapsed:.6f}s")
                    for w in active.values():
                        kill_worker(w)
                        try:
                            w["proc"].wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            os.killpg(w["proc"].pid, signal.SIGKILL)
                    return 0

                fill_slots()

        elapsed = time.perf_counter() - global_start
        print(f"\nNo satisfying query found among {n} queries.")
        print(f"Total time: {elapsed:.6f}s")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bounded-parallel SMT solver with sliding-window scheduling"
    )
    parser.add_argument("smt2_file", metavar="FILE.smt2")
    parser.add_argument("--solver", choices=SUPPORTED_SOLVERS, default="z3")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, metavar="N")
    args = parser.parse_args()

    smt2_path = Path(args.smt2_file)
    if not smt2_path.exists():
        print(f"Error: {smt2_path} not found", file=sys.stderr)
        sys.exit(1)

    solver_script = SOLVERS_DIR / f"{args.solver}.sh"
    if not solver_script.exists():
        print(f"Error: solver script not found: {solver_script}", file=sys.stderr)
        sys.exit(1)

    if args.workers < 1:
        print("Error: --workers must be >= 1", file=sys.stderr)
        sys.exit(1)

    sys.exit(run(smt2_path, solver=args.solver, max_workers=args.workers))


if __name__ == "__main__":
    main()
