#!/bin/bash
set -euo pipefail

usage() {
	echo "Usage: $0 <file.smt2|file>" >&2
	exit 1
}

if [ "$#" -ne 1 ]; then
	usage
fi

input_file=$1
if [[ "$input_file" != *.smt2 ]]; then
	input_file="${input_file}.smt2"
fi

if [ ! -f "$input_file" ]; then
	echo "File not found: $input_file" >&2
	exit 1
fi

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
input_dir=$(dirname "$input_file")
input_base=$(basename "$input_file" .smt2)

run_slot() {
	local label=$1
	shift

	local input_ll="$input_dir/$input_base-${label}.ll"
	local output_ll="$input_dir/$input_base-${label}-opt.ll"
	local output_smt2="$input_dir/$input_base-${label}.smt2"
	local start_ns end_ns elapsed_ns elapsed_ms

	start_ns=$(date +%s%N)
	"$script_dir/src/slot" -pall "$@" -dfs -m -max-paths 10 -s "$input_file" \
		-lu "$input_ll" -lo "$output_ll" -o "$output_smt2"
	end_ns=$(date +%s%N)
	elapsed_ns=$((end_ns - start_ns))
	elapsed_ms=$((elapsed_ns / 1000000))

	printf 'SLOT %s elapsed time: %d.%03d seconds\n' \
		"$label" \
		$((elapsed_ms / 1000)) \
		$((elapsed_ms % 1000))

	"$script_dir/time_z3.sh" "$output_smt2"
}

run_unmerge() {
	local ir_input=$1

	local output_ll="$input_dir/$input_base-unmerged-opt.ll"
	local output_smt2="$input_dir/$input_base-unmerged.smt2"
	local start_ns end_ns elapsed_ns elapsed_ms

	start_ns=$(date +%s%N)
	"$script_dir/src/slot" -unmerge -dfs -m -max-paths 10 \
		-li "$ir_input" -lo "$output_ll" -o "$output_smt2"
	end_ns=$(date +%s%N)
	elapsed_ns=$((end_ns - start_ns))
	elapsed_ms=$((elapsed_ns / 1000000))

	printf 'SLOT unmerged elapsed time: %d.%03d seconds\n' \
		$((elapsed_ms / 1000)) \
		$((elapsed_ms % 1000))

	"$script_dir/time_z3.sh" "$output_smt2"
}

"$script_dir/time_z3.sh" "$input_file"
run_slot "slot" -nounmerge
run_unmerge "$input_dir/$input_base-slot-opt.ll"
