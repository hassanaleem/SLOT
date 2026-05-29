#!/bin/bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

"$script_dir/run-select-strategies-all.sh"

"$script_dir/measure-slot-optimized-time.sh" &
"$script_dir/run-parallel-selected.sh" &
wait

python3 "$script_dir/make_time_breakdown_csv.py"
