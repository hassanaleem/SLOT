#!/bin/bash

cd "$(dirname "$0")/.."

benchmarks=$(cat torun.txt)
echo "benchmark,time-cvc5,result-cvc5,time-cvc5-ite,result-cvc5-ite,time-cvc5-ite-heuristics,result-cvc5-ite-heuristics" > cvc5-variants.csv

for benchmark in $benchmarks; do
    benchmark=${benchmark#/}

    start=$(date +%s.%N)
    cvc5_result=$(timeout 600s cvc5 \
        "slot-benchmark-sat-with-select/$benchmark.smt2" 2> /dev/null)
    cvc5_status=$?
    end=$(date +%s.%N)

    [ "$cvc5_status" -eq 124 ] && cvc5_result="timeout"
    cvc5_time=$(awk -v start="$start" -v end="$end" 'BEGIN { printf "%.2f", end - start }')

    start=$(date +%s.%N)
    ite_result=$(timeout 600s cvc5 \
        --early-ite-removal \
        --ite-simp \
        "slot-benchmark-sat-with-select/$benchmark.smt2" 2> /dev/null)
    ite_status=$?
    end=$(date +%s.%N)

    [ "$ite_status" -eq 124 ] && ite_result="timeout"
    ite_time=$(awk -v start="$start" -v end="$end" 'BEGIN { printf "%.2f", end - start }')

    start=$(date +%s.%N)
    justification_result=$(timeout 600s cvc5 \
        --ite-simp \
        --early-ite-removal \
        --decision=justification \
        "slot-benchmark-sat-with-select/$benchmark.smt2" 2> /dev/null)
    justification_status=$?
    end=$(date +%s.%N)

    [ "$justification_status" -eq 124 ] && justification_result="timeout"
    justification_time=$(awk -v start="$start" -v end="$end" 'BEGIN { printf "%.2f", end - start }')

    echo "$benchmark,$cvc5_time,$cvc5_result,$ite_time,$ite_result,$justification_time,$justification_result" >> cvc5-variants.csv
done
