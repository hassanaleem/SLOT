#!/bin/bash
set -e

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

strategy=$1
benchmark=$2
name=$(basename "$benchmark" .smt2)
out_dir="$DEFAULT_RESULTS_DIR/$name"

mkdir -p "$out_dir"
"$SLOT" -s "$benchmark" -pall "-unmerge-$strategy" "$SELECT_COUNT" -lu "$out_dir/$name.ll" -lo "$out_dir/$name-$strategy.ll" -o "$out_dir/$name-$strategy.smt2" > tmp.txt
