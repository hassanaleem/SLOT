#!/bin/bash
# Temporary: run every experiment in parallel.
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

bash "$script_dir/run-all-benchmarks-solvers.sh" &
bash "$script_dir/../solvers/z3-variants.sh" &
bash "$script_dir/../solvers/cvc5-variants.sh" &
wait
