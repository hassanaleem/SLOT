#!/bin/bash
# Usage: run-all-unsat-solvers.sh
# Runs run-all-unsat.sh once per solver (cvc5, z3). Query generation
# (phase 1/2) is solver-independent, but query-solver.sh writes logs
# without a solver tag, so a second solver pass into the same results
# dir would overwrite the first solver's logs. This runs each solver
# into its own results dir/CSV instead:
#   - cvc5 -> ../unsat (existing tree; set SKIP_DONE=1 to skip
#     strategies you've already solved there rather than re-solving)
#   - z3   -> ../unsat-z3 (fresh tree)
set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

SOLVER=cvc5 "$script_dir/run-all-unsat.sh" \
    "$script_dir/../unsat" \
    "$script_dir/result-csv/time_breakdown_unsat.csv"

SOLVER=z3 "$script_dir/run-all-unsat.sh" \
    "$script_dir/../unsat-z3" \
    "$script_dir/result-csv/time_breakdown_unsat_z3.csv"
