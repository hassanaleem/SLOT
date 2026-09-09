#!/bin/bash
# Usage: run-all-unsat.sh [results-dir] [output-csv]
# Runs STRATEGIES_UNSAT for all UNSAT benchmarks, phase-by-phase.
# A benchmark whose selects don't survive LLVM's -pall optimization pipeline
# is skipped uniformly for every strategy, opt included (see
# determine_post_opt_eligibility) — unmerging has nothing to split there,
# so solving it for any strategy would just reproduce the same single-path
# query solved N times over.
# Set SKIP_DONE=1 to avoid re-solving strategies from a prior run whose
# logs are already present (e.g. rerunning just to add chained-single-query).
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

BENCHMARK_DIR="${script_dir}/../unsat-benchmarks"
BENCHMARK_LIST="${script_dir}/../torun-unsat.txt"
DEFAULT_RESULTS_DIR="${script_dir}/../unsat"
ALLOW_ABSOLUTE_BENCHMARKS=1

[ "$#" -le 2 ] || { echo "Usage: $0 [results-dir] [output-csv]" >&2; exit 1; }
results_dir="${1:-$DEFAULT_RESULTS_DIR}"
output_csv="${2:-$script_dir/time_breakdown_unsat.csv}"
declare -A phase1_failures=()
declare -A generation_failures=()
declare -A post_opt_ineligible=()

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

# run_opt_generation <benchmark_path> <results_dir>
# opt's generation runs for every benchmark that got through phase 1. Its
# -opt.ll is the sole source of select eligibility for everything below,
# including opt's own solving.
run_opt_generation() {
    local benchmark_path=$1
    local benchmark_results_dir=$2
    local input_file input_base out_dir phase1_log strategy_key status=0

    resolve_input "$benchmark_path" "$benchmark_results_dir"
    phase1_log="$out_dir/logs/smt-to-ll.txt"
    strategy_key="$out_dir/opt"

    if [ -n "${phase1_failures[$out_dir]:-}" ]; then
        printf "skip %s/opt: phase 1 failed with exit status %s (smt-query-gen.sh)\n" \
            "$input_base" "${phase1_failures[$out_dir]}" >&2
        return 0
    fi

    if [ ! -f "$phase1_log" ]; then
        printf "skip %s/opt: phase 1 did not complete (smt-query-gen.sh)\n" "$input_base" >&2
        generation_failures["$strategy_key"]=1
        return 0
    fi

    "$script_dir/smt-query-gen.sh" opt "$benchmark_path" "$benchmark_results_dir" || status=$?
    if [ "$status" -ne 0 ]; then
        generation_failures["$strategy_key"]=$status
        printf "skip %s/opt: smt-query-gen.sh failed (exit_status=%d)\n" "$input_base" "$status" >&2
    else
        generation_failures["$strategy_key"]=
    fi
    return 0
}

# determine_post_opt_eligibility <benchmark_path> <results_dir>
# Populates post_opt_ineligible[$out_dir]=1 for benchmarks where 0 selects
# survive LLVM's -pall optimization pipeline (per -opt.ll), or where opt's
# own generation didn't run/succeed. This is the single source of truth
# used to gate both solving (every strategy, opt included) and generation
# (every non-opt strategy) below — a benchmark skipped for having no
# selects is skipped the same way everywhere, not solved for opt and
# skipped for the rest.
determine_post_opt_eligibility() {
    local benchmark_path=$1
    local benchmark_results_dir=$2
    local input_file input_base out_dir opt_ll post_opt_selects

    resolve_input "$benchmark_path" "$benchmark_results_dir"
    opt_ll="$out_dir/${input_base}-opt.ll"

    if [ -n "${phase1_failures[$out_dir]:-}" ] \
        || [ -n "${generation_failures[$out_dir/opt]:-}" ] \
        || [ ! -f "$opt_ll" ]; then
        post_opt_ineligible["$out_dir"]=1
        return 0
    fi

    post_opt_selects=$(grep -c '= select ' "$opt_ll" || true)
    if [ "$post_opt_selects" -eq 0 ]; then
        post_opt_ineligible["$out_dir"]=1
    else
        post_opt_ineligible["$out_dir"]=
    fi
    return 0
}

# run_generation_if_post_opt_has_selects <strategy> <benchmark_path> <results_dir>
# Gates smt-query-gen.sh for every non-opt strategy on post_opt_ineligible.
run_generation_if_post_opt_has_selects() {
    local strategy=$1
    local benchmark_path=$2
    local benchmark_results_dir=$3
    local input_file input_base out_dir strategy_key status=0

    resolve_input "$benchmark_path" "$benchmark_results_dir"
    strategy_key="$out_dir/$strategy"

    if [ -n "${post_opt_ineligible[$out_dir]:-}" ]; then
        printf "skip %s/%s: 0 selects survive optimization (smt-query-gen.sh)\n" \
            "$input_base" "$strategy" >&2
        generation_failures["$strategy_key"]=1
        return 0
    fi

    "$script_dir/smt-query-gen.sh" "$strategy" "$benchmark_path" "$benchmark_results_dir" || status=$?
    if [ "$status" -ne 0 ]; then
        generation_failures["$strategy_key"]=$status
        printf "skip %s/%s: smt-query-gen.sh failed (exit_status=%d)\n" \
            "$input_base" "$strategy" "$status" >&2
    else
        generation_failures["$strategy_key"]=
    fi
    return 0
}

# run_solve_if_post_opt_has_selects <strategy> <benchmark_path> <results_dir>
# Gates query-solver.sh on post_opt_ineligible for every strategy, opt
# included — the same eligibility generation was gated on above.
run_solve_if_post_opt_has_selects() {
    local strategy=$1
    local benchmark_path=$2
    local benchmark_results_dir=$3
    local input_file input_base out_dir strategy_key status=0

    resolve_input "$benchmark_path" "$benchmark_results_dir"
    strategy_key="$out_dir/$strategy"

    if [ -n "${post_opt_ineligible[$out_dir]:-}" ]; then
        printf "skip %s/%s: 0 selects survive optimization (query-solver.sh)\n" \
            "$input_base" "$strategy" >&2
        return 0
    fi

    if [ -n "${generation_failures[$strategy_key]:-}" ]; then
        printf "skip %s/%s: query generation failed with exit status %s (query-solver.sh)\n" \
            "$input_base" "$strategy" "${generation_failures[$strategy_key]}" >&2
        return 0
    fi

    "$script_dir/query-solver.sh" "$strategy" "$benchmark_path" "$benchmark_results_dir" || status=$?
    if [ "$status" -ne 0 ]; then
        printf "skip %s/%s: query-solver.sh failed (exit_status=%d)\n" \
            "$input_base" "$strategy" "$status" >&2
    fi
    return 0
}

foreach_benchmark "$results_dir" run_phase1_or_continue "$script_dir/smt-to-ir.sh"

foreach_benchmark "$results_dir" run_opt_generation

foreach_benchmark "$results_dir" determine_post_opt_eligibility

for strategy in "${STRATEGIES_UNSAT[@]}"; do
    [ "$strategy" = opt ] && continue
    foreach_benchmark "$results_dir" run_generation_if_post_opt_has_selects "$strategy"
done

for strategy in "${STRATEGIES_UNSAT[@]}"; do
    foreach_benchmark "$results_dir" run_solve_if_post_opt_has_selects "$strategy"
done

python3 "$script_dir/make_unsat_time_breakdown_csv.py" \
    "$results_dir" "$output_csv" \
    --benchmark-list "$BENCHMARK_LIST"
