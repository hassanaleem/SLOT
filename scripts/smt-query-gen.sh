#!/bin/bash
# Usage: run-phase2.sh <strategy> <file.smt2> [results-dir]
# Phase 2: simple IR -> strategy-specific LLVM IR + SMT2 variant.
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ "$#" -lt 2 ] || [ "$#" -gt 3 ] && { echo "Usage: $0 <strategy> <file.smt2> [results-dir]" >&2; exit 1; }
strategy=$1
input_file=$2
[[ "$input_file" != *.smt2 ]] && input_file="${input_file}.smt2"

slot="$script_dir/../src/slot"
[ ! -x "$slot" ] && { echo "Missing executable: $slot" >&2; exit 1; }

input_base=$(basename "$input_file" .smt2)
out_dir="${3:-$DEFAULT_RESULTS_DIR}/$input_base"

simple_ll="$out_dir/${input_base}.ll"
[ ! -f "$simple_ll" ] && { echo "Phase 1 not done: $simple_ll" >&2; exit 1; }

case "$strategy" in
    first|last|random|chain) slot_flags=("-unmerge-${strategy}" "$SELECT_COUNT") ;;
    all-bfs|all-dfs)         slot_flags=(-unmerge-all -max-paths "$((1 << SELECT_COUNT))" -path-strategy "${strategy#all-}") ;;
    opt)                     slot_flags=(-nounmerge) ;;
    *)                       echo "Unknown strategy: $strategy" >&2; exit 1 ;;
esac

start_ns=$(date +%s%N)
"$slot" -li "$simple_ll" -pall "${slot_flags[@]}" \
    -lo "$out_dir/${input_base}-${strategy}.ll" \
    -o "$out_dir/${input_base}-${strategy}.smt2" > /dev/null 2>"$out_dir/logs/${strategy}.err"
end_ns=$(date +%s%N)
elapsed_ms=$(((end_ns - start_ns) / 1000000))
printf "elapsed_ms=%d\n" "$elapsed_ms" > "$out_dir/logs/time-${strategy}.txt"
printf "phase2 %s/%s: elapsed_ms=%d\n" "$input_base" "$strategy" "$elapsed_ms" >&2
