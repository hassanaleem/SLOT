#!/bin/bash
set -e

strategy=$1
benchmark=$2
script_dir=$(cd "$(dirname "$0")" && pwd)
slot="$script_dir/../src/slot"
name=$(basename "$benchmark" .smt2)
out_dir="$script_dir/../select-results-strategies/$name"

mkdir -p "$out_dir"
"$slot" -s "$benchmark" -pall "-unmerge-$strategy" 5 -lu "$out_dir/$name.ll" -lo "$out_dir/$name-$strategy.ll" -o "$out_dir/$name-$strategy.smt2" > tmp.txt
