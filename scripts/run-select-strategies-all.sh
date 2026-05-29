#!/bin/bash
set -euo pipefail

[ "$#" -gt 1 ] && { echo "Usage: $0 [results-dir]" >&2; exit 1; }

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
benchmark_dir="$script_dir/../slot-benchmark-sat-with-select"
benchmark_list="$script_dir/../torun.txt"
results_dir="${1:-$script_dir/../select-results-strategies}"

[ ! -d "$benchmark_dir" ] && { echo "Benchmark directory not found: $benchmark_dir" >&2; exit 1; }
[ ! -f "$benchmark_list" ] && { echo "Benchmark list not found: $benchmark_list" >&2; exit 1; }

while IFS= read -r benchmark || [ -n "$benchmark" ]; do
    [ -z "$benchmark" ] && continue
    [[ "$benchmark" == \#* ]] && continue

    [[ "$benchmark" = /* ]] && benchmark_path="$benchmark" || benchmark_path="$benchmark_dir/$benchmark"
    [[ "$benchmark_path" != *.smt2 ]] && benchmark_path="${benchmark_path}.smt2"
    [ ! -f "$benchmark_path" ] && { echo "Benchmark not found: $benchmark_path" >&2; exit 1; }

    name=$(basename "$benchmark" .smt2)
    [ -d "$results_dir/$name" ] && { echo "$name skipped (already done)"; continue; }

    echo "=== Running select strategies for $name ==="
    "$script_dir/run-select-strategies.sh" "$benchmark_path" "$results_dir"
done < "$benchmark_list"

echo "Results saved to $results_dir"
