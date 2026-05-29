#!/bin/bash
set -uo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
strategy_root="$script_dir/../select-results-strategies"
benchmark_list="$script_dir/../torun.txt"
solver="$script_dir/../solvers/z3.sh"

[ ! -f "$benchmark_list" ] && { echo "Benchmark list not found: $benchmark_list" >&2; exit 1; }
[ ! -x "$solver" ] && { echo "Missing executable: $solver" >&2; exit 1; }

while IFS= read -r benchmark_path || [ -n "$benchmark_path" ]; do
    [ -z "$benchmark_path" ] && continue
    [[ "$benchmark_path" == \#* ]] && continue

    benchmark=$(basename "$benchmark_path" .smt2)
    bench_dir="$strategy_root/$benchmark"
    target_smt="$bench_dir/$benchmark-opt.smt2"
    log_file="$bench_dir/slot-optimized-time.log"

    [ ! -f "$target_smt" ] && { echo "Missing file: $target_smt" >&2; exit 1; }
    : > "$log_file"

    { printf "=== benchmark %s: slot-opt ===\nfile: %s\n" "$benchmark" "$target_smt"; } | tee -a "$log_file"
    "$solver" "$target_smt" 2>&1 | tee -a "$log_file"
    printf "exit_code: %s\n\n" "${PIPESTATUS[0]}" | tee -a "$log_file"

    printf "Log saved to %s\n" "$log_file"
done < "$benchmark_list"
