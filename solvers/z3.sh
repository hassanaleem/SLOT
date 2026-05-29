#!/bin/bash
set -euo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec env SLOT_SOLVER_TIMEOUT_SECONDS=500 "$script_dir/run-solver.sh" "z3" "z3" "$@"
