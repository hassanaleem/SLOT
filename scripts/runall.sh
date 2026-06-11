#!/bin/bash
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

# "$script_dir/run-all-benchmarks.sh"
$script_dir/run-variant-all-benchmarks.sh chain "${script_dir}/../select-results-strategies"

python3 "$script_dir/make_time_breakdown_csv.py"
