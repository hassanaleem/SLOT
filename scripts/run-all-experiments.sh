#!/bin/bash
# Temporary: run every experiment in parallel.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh" || exit $?

bash "$script_dir/run-all-benchmarks-solvers.sh" &
bash "$script_dir/../solvers/z3-variants.sh" &
bash "$script_dir/../solvers/cvc5-variants.sh" &
wait
