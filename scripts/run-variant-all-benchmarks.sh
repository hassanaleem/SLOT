#!/bin/bash
# Usage: run-variant-all-benchmarks.sh <strategy> [results-dir]
# Runs one strategy for all benchmarks, phase-by-phase.
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ "$#" -lt 1 ] || [ "$#" -gt 2 ] && { echo "Usage: $0 <strategy> [results-dir]" >&2; exit 1; }
strategy=$1
results_dir="${2:-$DEFAULT_RESULTS_DIR}"

# foreach_benchmark "$results_dir" "$script_dir/smt-to-ir.sh"
foreach_benchmark "$results_dir" "$script_dir/smt-query-gen.sh" "$strategy"
foreach_benchmark "$results_dir" "$script_dir/query-solver.sh" "$strategy"
