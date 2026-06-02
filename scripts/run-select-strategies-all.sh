#!/bin/bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
benchmark_dir="$script_dir/../slot-benchmark-sat-with-select"
benchmark_list="$script_dir/../torun.txt"
results_dir="${1:-$script_dir/../select-results-strategies}"

while IFS= read -r benchmark || [ -n "$benchmark" ]; do
    [ -z "$benchmark" ] && continue
    [[ "$benchmark" == \#* ]] && continue

    name=$(basename "$benchmark" .smt2)
    # [ -d "$results_dir/$name" ] && { echo "$name skipped (already done)"; continue; }

    "$script_dir/run-select-strategies.sh" "$benchmark_dir/$benchmark" "$results_dir"
done < "$benchmark_list"
