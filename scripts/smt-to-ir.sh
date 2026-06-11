#!/bin/bash
# Usage: run-phase1.sh <file.smt2> [results-dir]
# Phase 1: SMT -> simple LLVM IR. Skipped if IR already exists.
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ "$#" -lt 1 ] || [ "$#" -gt 2 ] && { echo "Usage: $0 <file.smt2> [results-dir]" >&2; exit 1; }
input_file=$1
[[ "$input_file" != *.smt2 ]] && input_file="${input_file}.smt2"
[ ! -f "$input_file" ] && { echo "File not found: $input_file" >&2; exit 1; }

slot="$script_dir/../src/slot"
[ ! -x "$slot" ] && { echo "Missing executable: $slot" >&2; exit 1; }

input_base=$(basename "$input_file" .smt2)
out_dir="${2:-$DEFAULT_RESULTS_DIR}/$input_base"
mkdir -p "$out_dir/logs"

simple_ll="$out_dir/${input_base}.ll"
# [ -f "$simple_ll" ] && exit 0

start_ns=$(date +%s%N)
timeout 300 "$slot" -s "$input_file" -lu "$simple_ll" -emit-ll-only > /dev/null
end_ns=$(date +%s%N)
elapsed_ms=$(((end_ns - start_ns) / 1000000))
num_selects=$(grep -c '= select ' "$simple_ll" || true)
printf "input=%s\nelapsed_ms=%d\nnum_selects=%d\n" "$input_file" "$elapsed_ms" "$num_selects" \
    > "$out_dir/logs/smt-to-ll.txt"
printf "phase1 %s: elapsed_ms=%d num_selects=%d\n" "$input_base" "$elapsed_ms" "$num_selects" >&2
