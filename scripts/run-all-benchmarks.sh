#!/bin/bash
# Usage: run-all-benchmarks.sh [results-dir]
# Runs all strategies for all benchmarks, phase-by-phase.
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

results_dir="${1:-$DEFAULT_RESULTS_DIR}"

foreach_benchmark "$results_dir" "$script_dir/smt-to-ir.sh"

for strategy in "${STRATEGIES[@]}"; do
    foreach_benchmark "$results_dir" "$script_dir/smt-query-gen.sh" "$strategy"
done

for strategy in "${STRATEGIES[@]}"; do
    foreach_benchmark "$results_dir" "$script_dir/query-solver.sh" "$strategy"
done
