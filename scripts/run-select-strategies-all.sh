#!/bin/bash
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

results_dir="${1:-$DEFAULT_RESULTS_DIR}"

foreach_benchmark "$results_dir" "$script_dir/run-select-strategies.sh"
