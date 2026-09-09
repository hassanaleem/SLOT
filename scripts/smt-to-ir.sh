#!/bin/bash
# Usage: run-phase1.sh <file.smt2> [results-dir]
# Phase 1: SMT -> simple LLVM IR. Skipped if IR already exists.
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ "$#" -lt 1 ] || [ "$#" -gt 2 ] && { echo "Usage: $0 <file.smt2> [results-dir]" >&2; exit 1; }
resolve_input "$1" "${2:-}"
[ ! -f "$input_file" ] && { echo "File not found: $input_file" >&2; exit 1; }

mkdir -p "$out_dir/logs"

simple_ll="$out_dir/${input_base}.ll"
should_skip "$simple_ll" && { echo "phase1 $input_base: skipped (already done)" >&2; exit 0; }

run_timed timeout 300 "$SLOT" -s "$input_file" -lu "$simple_ll" -emit-ll-only > /dev/null
printf "input=%s\nelapsed_ms=%d\n" "$input_file" "$elapsed_ms" \
    > "$out_dir/logs/smt-to-ll.txt"
printf "phase1 %s: elapsed_ms=%d\n" "$input_base" "$elapsed_ms" >&2
