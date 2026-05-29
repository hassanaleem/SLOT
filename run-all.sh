#!/bin/bash
set -euo pipefail

if [ "$#" -gt 1 ]; then
	echo "Usage: $0 [results-dir]" >&2
	exit 1
fi

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
benchmark_dir="$script_dir/slow-benchmarks/needed_qf_bv_slow_sat_queries"
results_dir="${1:-$script_dir/qf_bv_results}"
max_paths=30

[ ! -x "$script_dir/src/slot" ] && { echo "Missing executable: $script_dir/src/slot" >&2; exit 1; }
[ ! -d "$benchmark_dir" ]       && { echo "Benchmark directory not found: $benchmark_dir" >&2; exit 1; }

mkdir -p "$results_dir"

run() {
	local prefix=$1; shift
	local start end elapsed status
	start=$(date +%s%N)
	if timeout 500 "$script_dir/src/slot" "$@" >"${prefix}.out" 2>"${prefix}.err"; then status=0; else status=$?; fi
	end=$(date +%s%N)
	elapsed=$(( (end - start) / 1000000 ))
	printf '%s  status=%d  elapsed=%d.%03ds\n' \
		"$(basename "$prefix")" "$status" $((elapsed / 1000)) $((elapsed % 1000))
}

while IFS= read -r benchmark; do
	name=$(basename "$benchmark" .smt2)
	bench_results="$results_dir/$name"

	if [ -d "$bench_results" ]; then
		echo "$name  skipped (already done)"
		continue
	fi

	mkdir -p "$bench_results"

	slot="$bench_results/slot"
	run "$slot" -pall -nounmerge -m \
		-s "$benchmark" -lu "${slot}.ll" -lo "${slot}-opt.ll" -o "${slot}-opt.smt2"

	# unmerged_ir="$bench_results/unmerged.ll"

	# run "$bench_results/bfs-unmerged" \
	# 	-unmerge -bfs -m -max-paths "$max_paths" \
	# 	-li "${slot}-opt.ll" -lo "$unmerged_ir" -o "$bench_results/bfs-unmerged.smt2"

	# run "$bench_results/dfs-unmerged" \
	# 	-dfs -m -max-paths "$max_paths" \
	# 	-li "$unmerged_ir" -o "$bench_results/dfs-unmerged.smt2"
done < <(find "$benchmark_dir" -type f -name '*.smt2' -printf '%s %p\n' | sort -n | cut -d' ' -f2-)
