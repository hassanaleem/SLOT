#!/bin/bash
set -euo pipefail

usage() {
    echo "Usage: $0 <file.smt2> [results-dir]" >&2
    exit 1
}
[ "$#" -lt 1 ] || [ "$#" -gt 2 ] && usage

input_file=$1
[[ "$input_file" != *.smt2 ]] && input_file="${input_file}.smt2"
[ ! -f "$input_file" ] && { echo "File not found: $input_file" >&2; exit 1; }

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
slot="$script_dir/../src/slot"
[ ! -x "$slot" ] && { echo "Missing executable: $slot" >&2; exit 1; }

input_base=$(basename "$input_file" .smt2)
results_root="${2:-$script_dir/../select-results-strategies}"
out_dir="$results_root/$input_base"
select_count=5
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
    local start_ns end_ns elapsed_ms
    start_ns=$(date +%s%N)
    if ! "$slot" "$@" -lo "$out_ll" -o "$out_smt2" -t "$stats_tmp" > /dev/null 2>"$out_dir/${name}.err"; then
        echo "  $name failed; see $out_dir/${name}.err" >&2
        rm -f "$stats_tmp"
        exit 1
    fi
    end_ns=$(date +%s%N)
    elapsed_ms=$(((end_ns - start_ns) / 1000000))
    printf "strategy=%s elapsed_ms=%d\n" "$name" "$elapsed_ms" >> "$time_file"
    printf "%s,%s\n" "$name" "$(tail -n 1 "$stats_tmp")" >> "$pass_timing_file"
    rm -f "$stats_tmp"
    printf "strategy=%s elapsed_ms=%d\n" "$name" "$elapsed_ms" >&2
    echo "$elapsed_ms"
}

# Phase 1: SMT -> simple LLVM IR
start_ns=$(date +%s%N)
timeout 300 "$slot" -s "$input_file" -lu "$simple_ll" -emit-ll-only > /dev/null
end_ns=$(date +%s%N)
smt_to_ll_ms=$(((end_ns - start_ns) / 1000000))
printf "smt_to_ll elapsed_ms=%d\n" "$smt_to_ll_ms" >> "$time_file"
printf "smt_to_ll_ms=%d\n" "$smt_to_ll_ms" >&2

num_selects=$(grep -c '= select ' "$simple_ll" || true)
max_paths=$((1 << select_count))
printf "num_selects=%d max_paths=%d\n" "$num_selects" "$max_paths" >> "$time_file"
printf "num_selects=%d max_paths=%d\n" "$num_selects" "$max_paths" >&2

# Phase 2: first / last / random / chain (n = select_count)
ll_to_opt_total_ms=0

for strategy in first last random chain; do
    elapsed=$(run_strategy "$strategy" -li "$simple_ll" -pall "-unmerge-${strategy}" "$select_count")
    ll_to_opt_total_ms=$((ll_to_opt_total_ms + elapsed))
done

# Phase 3: all with bfs and dfs (max-paths = 2^num_selects)
for path_strategy in bfs dfs; do
    elapsed=$(run_strategy "all-${path_strategy}" -li "$simple_ll" -pall -unmerge-all -max-paths "$max_paths" -path-strategy "$path_strategy")
    ll_to_opt_total_ms=$((ll_to_opt_total_ms + elapsed))
done

# Phase 4: slot-optimized baseline — all passes, no select lowering
elapsed=$(run_strategy "opt" -li "$simple_ll" -pall -nounmerge)
ll_to_opt_total_ms=$((ll_to_opt_total_ms + elapsed))

total_ms=$((smt_to_ll_ms + ll_to_opt_total_ms))
printf "total elapsed_ms=%d\n" "$total_ms" >> "$time_file"
printf "total_ms=%d\n" "$total_ms" >&2
