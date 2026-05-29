#!/bin/bash
set -uo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
solver="$script_dir/parallel_solver.py"
workers="${WORKERS:-16}"
strategy_root="$script_dir/../select-results-strategies"
benchmark_list="$script_dir/../torun.txt"

[ ! -f "$benchmark_list" ] && { echo "Benchmark list not found: $benchmark_list" >&2; exit 1; }

run_solver() {
    local benchmark=$1 label=$2 smt_file=$3 log_file=$4 rc=0
    printf "=== benchmark %s: %s ===\n" "$benchmark" "$label" | tee -a "$log_file"
    if [ ! -f "$smt_file" ]; then
        printf "missing file, skipped: %s\n\n" "$smt_file" | tee -a "$log_file"
        return 0
    fi
    python3 -u "$solver" --workers "$workers" --solver z3 "$smt_file" 2>&1 | tee -a "$log_file"
    rc=${PIPESTATUS[0]}
    printf "exit_code: %s\n\n" "$rc" | tee -a "$log_file"
}

while IFS= read -r benchmark_path || [ -n "$benchmark_path" ]; do
    [ -z "$benchmark_path" ] && continue
    [[ "$benchmark_path" == \#* ]] && continue

    benchmark=$(basename "$benchmark_path" .smt2)
    strategy_dir="$strategy_root/$benchmark"
    log_file="$strategy_dir/parallel_solver_selected.log"

    [ ! -d "$strategy_dir" ] && { echo "Strategy directory not found: $strategy_dir" >&2; exit 1; }
    : > "$log_file"

    for strategy in first last random all-bfs all-dfs; do
        run_solver "$benchmark" "$strategy" "$strategy_dir/$benchmark-${strategy}.smt2" "$log_file"
    done

    printf "Log saved to %s\n" "$log_file"
done < "$benchmark_list"
