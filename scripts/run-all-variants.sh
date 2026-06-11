#!/bin/bash
# Usage: run-all-variants.sh <file.smt2> [results-dir]
# Runs all strategies for a single benchmark, phase-by-phase.
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ "$#" -lt 1 ] || [ "$#" -gt 2 ] && { echo "Usage: $0 <file.smt2> [results-dir]" >&2; exit 1; }
results_dir="${2:-$DEFAULT_RESULTS_DIR}"

"$script_dir/smt-to-ir.sh" "$1" "$results_dir"

for strategy in "${STRATEGIES[@]}"; do
    "$script_dir/smt-query-gen.sh" "$strategy" "$1" "$results_dir"
done

for strategy in "${STRATEGIES[@]}"; do
    "$script_dir/query-solver.sh" "$strategy" "$1" "$results_dir"
done
