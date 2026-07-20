#!/bin/bash
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

"$script_dir/run-all-benchmarks.sh"
# "$script_dir/run-variant-all-benchmarks.sh" chain "$DEFAULT_RESULTS_DIR"

# "$script_dir/run-variant-all-benchmarks.sh" chain "$DEFAULT_EXPERIMENTAL_DIR"

python3 "$script_dir/make_time_breakdown_csv.py"
