#!/bin/bash

cd "$(dirname "$0")/.."

benchmarks=$(cat torun.txt)
echo "benchmark,time-z3,result-z3,time-simplify-split-clause,result-simplify-split-clause" > z3-variants.csv

for benchmark in $benchmarks; do
    benchmark=${benchmark#/}

    start=$(date +%s.%N)
    z3_result=$(timeout 600s z3 \
        "slot-benchmark-sat-with-select/$benchmark.smt2" 2> /dev/null)
    z3_status=$?
    end=$(date +%s.%N)

    [ "$z3_status" -eq 124 ] && z3_result="timeout"
    z3_time=$(awk -v start="$start" -v end="$end" 'BEGIN { printf "%.2f", end - start }')

    start=$(date +%s.%N)
    split_result=$(timeout 600s z3 'tactic.default_tactic=(then simplify split-clause smt)' \
        "slot-benchmark-sat-with-select/$benchmark.smt2" 2> /dev/null)
    split_status=$?
    end=$(date +%s.%N)

    [ "$split_status" -eq 124 ] && split_result="timeout"
    split_time=$(awk -v start="$start" -v end="$end" 'BEGIN { printf "%.2f", end - start }')

    echo "$benchmark,$z3_time,$z3_result,$split_time,$split_result" >> z3-variants.csv
done
