# Scripts

## Where the solver runs

`run-variant.sh` Phase 3 calls the solver on the generated `.smt2` file:
- All strategies except `opt` → `parallel_solver.py` (bounded-parallel, stops at first SAT)
- `opt` → `solvers/run-solver.sh` directly (single query)

---

## Running variants

### `run-variant.sh`
Runs one strategy end-to-end for one benchmark: generates LLVM IR and SMT2, then solves.

The default sweep runs these four strategies:

| Strategy | SMT output | Per-path LLVM optimization |
|---|---|---|
| `chain` | One query per path | No |
| `chained-single-query` | One disjunction of all paths | No |
| `chain-path-opt` | One query per path | Yes |
| `chained-single-query-path-opt` | One disjunction of all paths | Yes |

All four use the same global optimization pipeline and `-unmerge-chain 5`.
The `-path-opt` variants optimize each selected path's LLVM body before SMT
conversion. The single-query variants then combine the path queries using
`-disjunction-single-query`. Rebuild SLOT with `make -C src` before running
these variants. Each strategy has separate generated files and timing logs;
`make_time_breakdown_csv.py` includes the new variants' generation, solving,
and total times.

Other individually selectable strategies remain available:
`chain-sink`, `first`, `last`, `random`, `all-bfs`, `all-dfs`, and `opt`.

`chain-sink` uses exactly the same flags as `chain`, plus `-unmerge-sink`:
`-pall -unmerge-chain 5 -unmerge-sink`. This enables sinking after each
lowered select. Its timing CSV columns use the `chain_sink` prefix.

Outputs into `select-results-strategies/{benchmark}/`:
- `{benchmark}-{strategy}.ll` / `.smt2` — generated files
- `logs/smt-to-ll.txt` — phase 1 timing (written once, shared across strategies)
- `logs/time-{strategy}.txt` — generation timing
- `logs/solver-{strategy}.log` — solver output
- `logs/{strategy}.err` — slot stderr

```bash
scripts/run-variant.sh chain path/to/benchmark.smt2
scripts/run-variant.sh chain-sink path/to/benchmark.smt2
scripts/run-variant.sh chained-single-query path/to/benchmark.smt2
scripts/run-variant.sh chain-path-opt path/to/benchmark.smt2
scripts/run-variant.sh chained-single-query-path-opt path/to/benchmark.smt2
scripts/run-variant.sh opt path/to/benchmark.smt2 /custom/results/dir
WORKERS=8 scripts/run-variant.sh all-bfs path/to/benchmark.smt2
```

---

### `run-all-variants.sh`
Runs the four default strategies for one benchmark, completing query generation
for all four before solving each variant.

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

### `run-all-unsat.sh`
Runs the benchmarks in `torun-unsat.txt` with the UNSAT configuration and writes a separate, status-aware breakdown CSV after the sweep completes.

```bash
scripts/run-all-unsat.sh
scripts/run-all-unsat.sh /custom/results/dir /custom/time_breakdown_unsat.csv
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

### `graphs/plot_paired_scatter.py`
Reads `scripts/time_breakdown-llvm22-z3.csv` and
`scripts/time_breakdown-llvm22-cvc5.csv`, plus the baseline variant CSVs.
Includes paired `chain` versus `chain-sink` scatter plots for solver time and
total time, using the `chain_*` and `chain_sink_*` columns. The plots put
`chain-sink` on the x-axis and `chain` on the y-axis, and write
`graphs/{z3,cvc5}_chain_vs_chain_sink_{solver,total}.pdf`.
Benchmarks missing either timing are skipped.

```bash
python3 graphs/plot_paired_scatter.py
```

### `graphs/plot_cactus.py`
Reads `scripts/time_breakdown-llvm22-z3.csv` and
`scripts/time_breakdown-llvm22-cvc5.csv`. The strategy-comparison plots show
`chain`, `chained-single-query`, `chain-path-opt`, and
`chained-single-query-path-opt`, with separate PDFs for solver time and total
time. Existing `graphs/{z3,cvc5}_cactus_chain_vs_chained_single_query_{solver,total}.pdf`
filenames are retained. Optimized variants are labeled `+ Path Opt` in the legend.

Separate `chain` versus `chain-sink` cactus plots are written to
`graphs/{z3,cvc5}_cactus_chain_vs_chain_sink_{solver,total}.pdf`. Each comparison
uses benchmarks with timing data for both strategies; timed-out runs remain
in the attempted count but are excluded from the solved curves.

```bash
python3 graphs/plot_cactus.py
```


ThunderFork versus SLOT cactus plots use the current `chain_*` measurements
above and saved `slot_*` measurements from
`scripts/result-csv/time_breakdown-llvm22-{z3,cvc5}.csv`, because the current
CSVs have empty SLOT columns. These are separate runs paired by benchmark
identity. Outputs are `graphs/{z3,cvc5}_cactus_chain_vs_slot_{solver,total}.pdf`;
`solver` uses solver time and `total` includes conversion and generation.
Only benchmarks with both timings enter the comparison. The existing 650-second
timeout rule checks both solver and total time, retaining timeouts in the
attempted count while excluding them from each solved curve.

To generate just these comparisons:

```bash
python3 graphs/plot_cactus.py --slot-only
```

### `make_unsat_time_breakdown_csv.py`
Collects only the benchmarks listed in `torun-unsat.txt` and writes `scripts/time_breakdown_unsat.csv`. Like the general collector, it reads every available timing log without inferring eligibility from select counts. It records solver/result status, excludes stale non-manifest runs, and leaves numeric solver/total fields blank for parse errors or other invalid outcomes.

```bash
python3 scripts/make_unsat_time_breakdown_csv.py
python3 scripts/make_unsat_time_breakdown_csv.py /custom/results/dir /custom/time_breakdown_unsat.csv
```

### `graphs/plot_unsat.py`
Reads the separate UNSAT CSV and writes paired scatter and cactus PDFs under `graphs/unsat/`. Every available numeric timing is included; SAT graph files are not read or overwritten.

```bash
python3 graphs/plot_unsat.py
python3 graphs/plot_unsat.py /custom/time_breakdown_unsat.csv /custom/graph-dir
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
| `STRATEGIES` | `(chain chained-single-query chain-path-opt chained-single-query-path-opt)` |
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
