#!/bin/bash
# Usage: query-solver.sh <strategy> <file.smt2> [results-dir]
# Phase 3: solve the strategy-specific SMT2 variant.
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ "$#" -lt 2 ] || [ "$#" -gt 3 ] && { echo "Usage: $0 <strategy> <file.smt2> [results-dir]" >&2; exit 1; }
strategy=$1
resolve_input "$2" "${3:-}"

out_smt2="$out_dir/${input_base}-${strategy}.smt2"
[ ! -f "$out_smt2" ] && { echo "Phase 2 not done: $out_smt2" >&2; exit 1; }

log_file="$out_dir/logs/solver-${strategy}.log"
# A log without the final exit_code line is from an interrupted run; redo it.
should_skip "$log_file" '^exit_code:' \
    && { echo "phase3 $input_base/$strategy: skipped (already done)" >&2; exit 0; }

if [ "$strategy" = opt ]; then
    solver_cmd=("$SOLVERS_DIR/run-solver.sh" "$SOLVER" "$out_smt2")
else
    solver_cmd=(python3 -u "$PARALLEL_SOLVER" --workers "$WORKERS" --solver "$SOLVER" "$out_smt2")
fi

printf "=== benchmark %s: %s ===\n" "$input_base" "$strategy" | tee "$log_file"
# A no-SAT/timeout benchmark exits non-zero; that must not abort this script
# (set -e) or the sweep driver above it — record it and move on.
status=0
"${solver_cmd[@]}" 2>&1 | tee -a "$log_file" || status=$?
printf "exit_code: %s\n\n" "$status" | tee -a "$log_file"
sleep "$COOLDOWN_SECONDS"
