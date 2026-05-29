#!/bin/bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
smt_dir="$script_dir/slow-benchmarks/needed_qf_bv_slow_sat_queries_smallest20/mcm"
results_dir="${1:-$script_dir/select_results}"
max_paths=30

[ ! -x "$script_dir/src/slot" ] && { echo "Missing executable: $script_dir/src/slot" >&2; exit 1; }

mkdir -p "$results_dir"

run() {
	local prefix=$1; shift
	local start end elapsed status
	start=$(date +%s%N)
	if timeout 300 "$script_dir/src/slot" "$@" >"${prefix}.out" 2>"${prefix}.err"; then status=0; else status=$?; fi
	end=$(date +%s%N)
	elapsed=$(( (end - start) / 1000000 ))
	printf '%s  status=%d  elapsed=%d.%03ds\n' \
		"$(basename "$prefix")" "$status" $((elapsed / 1000)) $((elapsed % 1000))
}

for smt in "$smt_dir/24.smt2" "$smt_dir/85.smt2"; do
	name=$(basename "$smt" .smt2)
	bench_dir="$results_dir/$name"
	mkdir -p "$bench_dir"

	slot="$bench_dir/slot"
	run "$slot" -pall -nounmerge -m \
		-s "$smt" -lu "${slot}.ll" -lo "${slot}-opt.ll" -o "${slot}-opt.smt2"

	for mode in bfs dfs; do
		run "$bench_dir/${mode}-unmerged" \
			-pall -"$mode" -m -max-paths "$max_paths" \
			-s "$smt" -lo "$bench_dir/${mode}-unmerged-opt.ll" -o "$bench_dir/${mode}-unmerged.smt2"
	done
done
