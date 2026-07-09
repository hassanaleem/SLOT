#!/bin/bash
# Usage: run-phase2.sh <strategy> <file.smt2> [results-dir]
# Phase 2: simple IR -> strategy-specific LLVM IR + SMT2 variant.
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ "$#" -lt 2 ] || [ "$#" -gt 3 ] && { echo "Usage: $0 <strategy> <file.smt2> [results-dir]" >&2; exit 1; }
strategy=$1
resolve_input "$2" "${3:-}"

simple_ll="$out_dir/${input_base}.ll"
[ ! -f "$simple_ll" ] && { echo "Phase 1 not done: $simple_ll" >&2; exit 1; }

out_ll="$out_dir/${input_base}-${strategy}.ll"
out_smt2="$out_dir/${input_base}-${strategy}.smt2"
should_skip "$out_smt2" && should_skip "$out_ll" \
    && { echo "phase2 $input_base/$strategy: skipped (already done)" >&2; exit 0; }

strategy_flags "$strategy"

run_timed "$SLOT" -li "$simple_ll" -pall "${slot_flags[@]}" \
    -lo "$out_ll" \
    -o "$out_smt2" > /dev/null 2>"$out_dir/logs/${strategy}.err"
printf "elapsed_ms=%d\n" "$elapsed_ms" > "$out_dir/logs/time-${strategy}.txt"
printf "phase2 %s/%s: elapsed_ms=%d\n" "$input_base" "$strategy" "$elapsed_ms" >&2
