#!/bin/bash
# Usage: run-all-unsat.sh [results-dir] [output-csv]
# Runs all strategies for all UNSAT benchmarks, phase-by-phase.
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

BENCHMARK_DIR="${script_dir}/../unsat-benchmarks"
BENCHMARK_LIST="${script_dir}/../torun-unsat.txt"
DEFAULT_RESULTS_DIR="${script_dir}/../unsat"
ALLOW_ABSOLUTE_BENCHMARKS=1
export SLOT_DISJUNCTION=1

[ "$#" -le 2 ] || { echo "Usage: $0 [results-dir] [output-csv]" >&2; exit 1; }
results_dir="${1:-$DEFAULT_RESULTS_DIR}"
output_csv="${2:-$script_dir/time_breakdown_unsat.csv}"
declare -A phase1_failures=()
declare -A generation_failures=()

# run_phase1_or_continue <phase_script> <benchmark_path> <results_dir>
# A single bad benchmark must not prevent later benchmarks or phases from running.
run_phase1_or_continue() {
    local phase_script=$1
    local benchmark_path=$2
    local benchmark_results_dir=$3
    local input_file input_base out_dir status=0

    resolve_input "$benchmark_path" "$benchmark_results_dir"
    "$phase_script" "$benchmark_path" "$benchmark_results_dir" || status=$?
    if [ "$status" -ne 0 ]; then
        phase1_failures["$out_dir"]=$status
        printf "skip %s: %s failed (exit_status=%d)\n" \
            "$input_base" "$(basename "$phase_script")" "$status" >&2
    else
        phase1_failures["$out_dir"]=
    fi
    return 0
}

# run_strategy_phase_if_has_selects <phase_script> <strategy> <benchmark_path> <results_dir>
# The unfiltered phase-1 sweep runs first, so this log reflects the current IR.
run_strategy_phase_if_has_selects() {
    local phase_script=$1
    local strategy=$2
    local benchmark_path=$3
    local benchmark_results_dir=$4
    local input_file input_base out_dir phase1_log phase_name strategy_key status=0

    resolve_input "$benchmark_path" "$benchmark_results_dir"
    phase1_log="$out_dir/logs/smt-to-ll.txt"
    phase_name=$(basename "$phase_script")
    strategy_key="$out_dir/$strategy"

    if [ -n "${phase1_failures[$out_dir]:-}" ]; then
        printf "skip %s/%s: phase 1 failed with exit status %s (%s)\n" \
            "$input_base" "$strategy" "${phase1_failures[$out_dir]}" "$phase_name" >&2
        return 0
    fi

    if [ ! -f "$phase1_log" ]; then
        printf "skip %s/%s: phase 1 did not complete (%s)\n" \
            "$input_base" "$strategy" "$phase_name" >&2
        return 0
    fi

    if ! grep -Eq '^num_selects=[0-9]+$' "$phase1_log"; then
        printf "skip %s/%s: phase-1 log has no valid select count (%s)\n" \
            "$input_base" "$strategy" "$phase_name" >&2
        return 0
    fi

    if grep -Fxq 'num_selects=0' "$phase1_log"; then
        printf "skip %s/%s: num_selects=0 (%s)\n" \
            "$input_base" "$strategy" "$phase_name" >&2
        return 0
    fi

    if [ "$phase_name" = query-solver.sh ] \
        && [ -n "${generation_failures[$strategy_key]:-}" ]; then
        printf "skip %s/%s: query generation failed with exit status %s (%s)\n" \
            "$input_base" "$strategy" "${generation_failures[$strategy_key]}" "$phase_name" >&2
        return 0
    fi

    "$phase_script" "$strategy" "$benchmark_path" "$benchmark_results_dir" || status=$?
    if [ "$status" -ne 0 ]; then
        if [ "$phase_name" = smt-query-gen.sh ]; then
            generation_failures["$strategy_key"]=$status
        fi
        printf "skip %s/%s: %s failed (exit_status=%d)\n" \
            "$input_base" "$strategy" "$phase_name" "$status" >&2
    elif [ "$phase_name" = smt-query-gen.sh ]; then
        generation_failures["$strategy_key"]=
    fi
    return 0
}

foreach_benchmark "$results_dir" run_phase1_or_continue "$script_dir/smt-to-ir.sh"

for strategy in "${STRATEGIES[@]}"; do
    foreach_benchmark "$results_dir" run_strategy_phase_if_has_selects \
        "$script_dir/smt-query-gen.sh" "$strategy"
done

for strategy in "${STRATEGIES[@]}"; do
    foreach_benchmark "$results_dir" run_strategy_phase_if_has_selects \
        "$script_dir/query-solver.sh" "$strategy"
done

python3 "$script_dir/make_unsat_time_breakdown_csv.py" \
    "$results_dir" "$output_csv" \
    --benchmark-list "$BENCHMARK_LIST"
