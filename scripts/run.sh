#!/bin/bash
set -e

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

strategy=$1
benchmark=$2
name=$(basename "$benchmark" .smt2)
out_dir="$DEFAULT_RESULTS_DIR/$name"
strategy_flags "$strategy"

mkdir -p "$out_dir"
"$SLOT" -s "$benchmark" -pall "${slot_flags[@]}" -lu "$out_dir/$name.ll" -lo "$out_dir/$name-$strategy.ll" -o "$out_dir/$name-$strategy.smt2" > tmp.txt
