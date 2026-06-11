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
Runs all strategies for every benchmark in `torun.txt`. Calls `run-all-variants.sh` per benchmark.

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
Sourced by the shell scripts above. Defines shared paths and helpers — not run directly.

| Variable | Value |
|---|---|
| `BENCHMARK_DIR` | `slot-benchmark-sat-with-select/` |
| `BENCHMARK_LIST` | `torun.txt` |
| `DEFAULT_RESULTS_DIR` | `select-results-strategies/` |
| `STRATEGIES` | `(first last random chain all-bfs all-dfs opt)` |

`foreach_benchmark <results_dir> <cmd> [args...]` — iterates `torun.txt` and calls `<cmd> [args...] <benchmark_path> <results_dir>` for each entry.

---

## Legacy (superseded)

| Script | Replaced by |
|---|---|
| `run-select-strategies.sh` | `run-all-variants.sh` |
| `run-select-strategies-all.sh` | `run-all-benchmarks.sh` |
| `run.sh` | `run-variant.sh` |
