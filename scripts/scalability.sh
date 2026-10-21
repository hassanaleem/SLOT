#!/usr/bin/env bash
# Usage: bash scripts/scalability.sh [results-dir] [benchmark-list]
# Same phase-by-phase composition as the other experiment drivers.
# Set SKIP_DONE=1 to reuse completed phases and solver logs.
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ "$#" -le 2 ] || { echo "Usage: $0 [results-dir] [benchmark-list]" >&2; exit 1; }
results_root="${1:-$script_dir/../scalability-log}"
BENCHMARK_LIST="${2:-$BENCHMARK_LIST}"
strategy=chain
solvers=(z3)
export SELECT_COUNT
export WORKERS=32

# Existing scripts name benchmark directories by basename. Validate inputs
# and directory names before starting any phases.
declare -A benchmark_names=()
check_benchmark() {
    local input_file input_base out_dir
    resolve_input "$1" "$2"
    [ -f "$input_file" ] || { echo "File not found: $input_file" >&2; return 1; }
    [ -z "${benchmark_names[$input_base]:-}" ] || { echo "Duplicate benchmark name: $input_base" >&2; return 1; }
    benchmark_names[$input_base]=1
}
foreach_benchmark "$results_root" check_benchmark
[ "${#benchmark_names[@]}" -gt 0 ] || { echo "Benchmark list is empty" >&2; exit 1; }
for solver in "${solvers[@]}"; do
    command -v "$solver" > /dev/null || { echo "Missing solver: $solver" >&2; exit 1; }
done
[ ! -f "$results_root/manifest.json" ] || {
    echo "This directory contains results from the old scalability runner. Choose a fresh results-dir." >&2
    exit 1
}
mkdir -p "$results_root"
cp "$BENCHMARK_LIST" "$results_root/torun.txt"

for SELECT_COUNT in 5 6 7 8; do
    for solver in "${solvers[@]}"; do
        export SOLVER="$solver"
        results_dir="$results_root/n${SELECT_COUNT}/$solver"
        printf '\n=== n=%d solver=%s ===\n' "$SELECT_COUNT" "$SOLVER"
        foreach_benchmark "$results_dir" "$script_dir/smt-to-ir.sh"
        foreach_benchmark "$results_dir" "$script_dir/smt-query-gen.sh" "$strategy"
        foreach_benchmark "$results_dir" "$script_dir/query-solver.sh" "$strategy"
        python3 "$script_dir/make_time_breakdown_csv.py" \
            "$results_dir" "$results_root/time-breakdown-n${SELECT_COUNT}-${solver}.csv"
    done
done

python3 "$script_dir/../graphs/scalability-cactus.py" --results-dir "$results_root"
