# Scripts

## Where the solver runs

`run-variant.sh` Phase 3 calls the solver on the generated `.smt2` file:
- All strategies except `opt` → `parallel_solver.py` (bounded-parallel, stops at first SAT)
- `opt` → `solvers/z3.sh` directly (single query)

---

## Running variants

### `run-variant.sh`
Runs one strategy end-to-end for one benchmark: generates LLVM IR and SMT2, then solves.

Strategies: `first` `last` `random` `chain` `all-bfs` `all-dfs` `opt`

Outputs into `select-results-strategies/{benchmark}/`:
- `{benchmark}-{strategy}.ll` / `.smt2` — generated files
- `logs/smt-to-ll.txt` — phase 1 timing (written once, shared across strategies)
- `logs/time-{strategy}.txt` — generation timing
- `logs/solver-{strategy}.log` — solver output
- `logs/{strategy}.err` — slot stderr

```bash
scripts/run-variant.sh chain path/to/benchmark.smt2
scripts/run-variant.sh opt path/to/benchmark.smt2 /custom/results/dir
WORKERS=8 scripts/run-variant.sh all-bfs path/to/benchmark.smt2
```

---

### `run-all-variants.sh`
Runs all 7 strategies for one benchmark by calling `run-variant.sh` in sequence.

```bash
scripts/run-all-variants.sh path/to/benchmark.smt2
scripts/run-all-variants.sh path/to/benchmark.smt2 /custom/results/dir
```

---

### `run-variant-all-benchmarks.sh`
Runs one strategy across every benchmark listed in `torun.txt`.

```bash
scripts/run-variant-all-benchmarks.sh chain
scripts/run-variant-all-benchmarks.sh opt /custom/results/dir
```

---

### `run-all-benchmarks.sh`
Runs all strategies for every benchmark in `torun.txt`, phase-by-phase: phase 1 for all benchmarks, then phase 2 for every strategy, then phase 3 for every strategy. All query generation completes before any solving starts.

```bash
scripts/run-all-benchmarks.sh
scripts/run-all-benchmarks.sh /custom/results/dir
```

---

### `runall.sh`
Top-level entry point: runs all benchmarks then generates the summary CSV.

```bash
scripts/runall.sh
```

---

## Solving

### `parallel_solver.py`
Splits a multi-query `.smt2` file into individual queries, runs up to N solver workers concurrently, and stops at the first SAT result.

```bash
python3 scripts/parallel_solver.py path/to/file.smt2 --solver z3 --workers 16
python3 scripts/parallel_solver.py path/to/file.smt2 --solver cvc5
```

---

## Analysis

### `make_time_breakdown_csv.py`
Collects results from all benchmark `logs/` directories into a single CSV with generation time, solver time, and total time per strategy.

Reads from: `select-results-strategies/*/logs/`  
Writes to: `scripts/time_breakdown.csv`

```bash
python3 scripts/make_time_breakdown_csv.py
python3 scripts/make_time_breakdown_csv.py /custom/results/dir /custom/output.csv
```

---

### `total_times_only.sh`
Extracts only the `*_total_seconds` columns from `time_breakdown.csv`, generates `time_totals.csv`, then runs `generate_colored_table.py` to produce the highlighted Excel file.

```bash
scripts/total_times_only.sh
```

---

### `generate_colored_table.py`
Reads `time_totals.csv` and produces `time_totals_highlighted.xlsx` with color-coded cells (best result per benchmark highlighted).

```bash
python3 scripts/generate_colored_table.py
```

---

## Shared

### `common.sh`
Sourced by the shell scripts above. Defines shared paths and helpers — not run directly. Fails immediately if the `slot` executable is missing.

| Variable | Value |
|---|---|
| `BENCHMARK_DIR` | `slot-benchmark-sat-with-select/` |
| `BENCHMARK_LIST` | `torun.txt` |
| `DEFAULT_RESULTS_DIR` | `select-results-strategies/` |
| `SLOT` | `src/slot` |
| `SOLVERS_DIR` | `solvers/` |
| `PARALLEL_SOLVER` | `scripts/parallel_solver.py` |
| `STRATEGIES` | `(first last random chain all-bfs all-dfs opt)` |
| `SELECT_COUNT` | `5` |
| `WORKERS` | `16` (env-overridable) |
| `SKIP_DONE` | `1` — skip phases whose outputs exist; set `0` to always rerun (env-overridable) |
| `COOLDOWN_SECONDS` | `5` — sleep after each solver run; set `0` to disable (env-overridable) |

Helpers:
- `foreach_benchmark <results_dir> <cmd> [args...]` — iterates `torun.txt` and calls `<cmd> [args...] <benchmark_path> <results_dir>` for each entry.
- `resolve_input <file[.smt2]> [results_dir]` — appends `.smt2` if missing; sets `input_file`, `input_base`, `out_dir`.
- `should_skip <file> [pattern]` — true when `SKIP_DONE=1` and `<file>` exists (and contains `<pattern>`, if given). Phase 1 checks the simple `.ll`, phase 2 the strategy `.ll`+`.smt2`, phase 3 the solver log's final `exit_code:` line.
- `strategy_flags <strategy>` — sets `slot_flags` with the slot arguments for the strategy.
- `run_timed <cmd...>` — runs the command, sets `elapsed_ms`, returns the command's status.

---

## Legacy (superseded)

Kept for reference; all three now share paths and helpers from `common.sh`.

| Script | Replaced by |
|---|---|
| `run-select-strategies.sh` | `run-all-variants.sh` |
| `run-select-strategies-all.sh` | `run-all-benchmarks.sh` |
| `run.sh` | `run-variant.sh` |
