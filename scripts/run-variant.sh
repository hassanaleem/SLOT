#!/bin/bash
# Usage: run-variant.sh <strategy> <file.smt2> [results-dir]
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

usage() { echo "Usage: $0 <strategy> <file.smt2> [results-dir]  strategy: ${STRATEGIES[*]}" >&2; exit 1; }
[ "$#" -lt 2 ] || [ "$#" -gt 3 ] && usage

strategy=$1
results_dir="${3:-$DEFAULT_RESULTS_DIR}"

"$script_dir/smt-to-ir.sh" "$2" "$results_dir"
"$script_dir/smt-query-gen.sh" "$strategy" "$2" "$results_dir"
"$script_dir/query-solver.sh" "$strategy" "$2" "$results_dir"
