#!/bin/bash
# Usage: run-phase3.sh <strategy> <file.smt2> [results-dir]
# Phase 3: solve the strategy-specific SMT2 variant.
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ "$#" -lt 2 ] || [ "$#" -gt 3 ] && { echo "Usage: $0 <strategy> <file.smt2> [results-dir]" >&2; exit 1; }
strategy=$1
input_file=$2
[[ "$input_file" != *.smt2 ]] && input_file="${input_file}.smt2"

z3="$script_dir/../solvers/z3.sh"
parallel_solver="$script_dir/parallel_solver.py"
workers="${WORKERS:-16}"

input_base=$(basename "$input_file" .smt2)
out_dir="${3:-$DEFAULT_RESULTS_DIR}/$input_base"

out_smt2="$out_dir/${input_base}-${strategy}.smt2"
[ ! -f "$out_smt2" ] && { echo "Phase 2 not done: $out_smt2" >&2; exit 1; }

if [ "$strategy" = "opt" ]; then
    solver_cmd=("$z3" "$out_smt2")
else
    solver_cmd=(python3 -u "$parallel_solver" --workers "$workers" --solver z3 "$out_smt2")
fi

log_file="$out_dir/logs/solver-${strategy}.log"
: > "$log_file"
printf "=== benchmark %s: %s ===\n" "$input_base" "$strategy" | tee -a "$log_file"
"${solver_cmd[@]}" 2>&1 | tee -a "$log_file"
printf "exit_code: %s\n\n" "${PIPESTATUS[0]}" | tee -a "$log_file"
sleep 5
