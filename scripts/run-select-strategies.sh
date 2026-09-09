#!/bin/bash
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ "$#" -lt 1 ] || [ "$#" -gt 2 ] && { echo "Usage: $0 <file.smt2> [results-dir]" >&2; exit 1; }
resolve_input "$1" "${2:-}"
[ ! -f "$input_file" ] && { echo "File not found: $input_file" >&2; exit 1; }

mkdir -p "$out_dir"

simple_ll="$out_dir/${input_base}.ll"
time_file="$out_dir/time.txt"
pass_timing_file="$out_dir/pass-timings.csv"
: > "$time_file"
: > "$pass_timing_file"
printf "input=%s\n" "$input_file" >> "$time_file"
printf "%s\n" "strategy,input,shift_to_multiply,path_strategy,requested_loopopt,requested_instcombine,requested_ainstcombine,requested_reassociate,requested_sccp,requested_dce,requested_adce,requested_instsimplify,requested_gvn,requested_unmerge,frontend_seconds,opt_seconds,backend_seconds,used_loopopt,used_instcombine,used_ainstcombine,used_reassociate,used_sccp,used_dce,used_adce,used_instsimplify,used_gvn,used_unmerge,loopopt_seconds,instcombine_seconds,ainstcombine_seconds,earlycse_seconds,reassociate_seconds,sccp_seconds,dce_seconds,adce_seconds,instsimplify_seconds,gvn_seconds,unmerge_seconds" >> "$pass_timing_file"

run_strategy() {
    local name=$1; shift
    local out_ll="$out_dir/${input_base}-${name}.ll"
    local out_smt2="$out_dir/${input_base}-${name}.smt2"
    local stats_tmp; stats_tmp=$(mktemp)
    if ! run_timed "$SLOT" "$@" -lo "$out_ll" -o "$out_smt2" -t "$stats_tmp" > /dev/null 2>"$out_dir/${name}.err"; then
        echo "  $name failed; see $out_dir/${name}.err" >&2
        rm -f "$stats_tmp"
        exit 1
    fi
    printf "strategy=%s elapsed_ms=%d\n" "$name" "$elapsed_ms" >> "$time_file"
    printf "%s,%s\n" "$name" "$(tail -n 1 "$stats_tmp")" >> "$pass_timing_file"
    rm -f "$stats_tmp"
    printf "strategy=%s elapsed_ms=%d\n" "$name" "$elapsed_ms" >&2
    echo "$elapsed_ms"
}

# Phase 1: SMT -> simple LLVM IR
run_timed timeout 300 "$SLOT" -s "$input_file" -lu "$simple_ll" -emit-ll-only > /dev/null
smt_to_ll_ms=$elapsed_ms
printf "smt_to_ll elapsed_ms=%d\n" "$smt_to_ll_ms" >> "$time_file"
printf "smt_to_ll_ms=%d\n" "$smt_to_ll_ms" >&2

# Phase 2: every unmerge strategy plus the opt baseline
ll_to_opt_total_ms=0
for strategy in "${STRATEGIES[@]}"; do
    strategy_flags "$strategy"
    elapsed=$(run_strategy "$strategy" -li "$simple_ll" -pall "${slot_flags[@]}")
    ll_to_opt_total_ms=$((ll_to_opt_total_ms + elapsed))
done

total_ms=$((smt_to_ll_ms + ll_to_opt_total_ms))
printf "total elapsed_ms=%d\n" "$total_ms" >> "$time_file"
printf "total_ms=%d\n" "$total_ms" >&2
