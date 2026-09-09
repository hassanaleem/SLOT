#!/bin/bash

set -euo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

SOLVER=cvc5 "$script_dir/run-all-benchmarks.sh" \
    "$script_dir/../select-results-strategies"
python3 "$script_dir/make_time_breakdown_csv.py" \
    "$script_dir/../select-results-strategies" \
    "$script_dir/time_breakdown-llvm22-cvc5.csv"

SOLVER=z3 "$script_dir/run-all-benchmarks.sh" \
    "$script_dir/../select-results-strategies-z3"
python3 "$script_dir/make_time_breakdown_csv.py" \
    "$script_dir/../select-results-strategies-z3" \
    "$script_dir/time_breakdown-llvm22-z3.csv"
