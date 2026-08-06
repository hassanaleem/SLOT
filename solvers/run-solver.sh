#!/bin/bash
# Usage: run-solver.sh <solver> <file.smt2>
# Runs a solver binary on a single-query .smt2 file and prints one line:
#   query=1 <solver>_result=<result> <solver>_time_seconds=<seconds>
# SLOT_SOLVER_TIMEOUT_SECONDS bounds the run (unset/0 = no timeout).
set -euo pipefail

solver=$1
input_file=$2

# Solvers may print warnings to stderr while still answering on stdout, so
# keep the streams separate and only fall back to stderr for the result.
stderr_file=$(mktemp)
trap 'rm -f "$stderr_file"' EXIT
# Signals must exit (running the EXIT trap), not resume the script.
trap 'exit 143' HUP INT TERM

start_ns=$(date +%s%N)
status=0
# --foreground keeps the solver in this script's process group; without it
# timeout moves it into a new group, where parallel_solver.py's killpg can
# never reach it.
stdout=$(timeout --foreground "${SLOT_SOLVER_TIMEOUT_SECONDS:-0}" "$solver" "$input_file" 2>"$stderr_file") || status=$?
end_ns=$(date +%s%N)

# First non-empty line, whitespace collapsed so the result stays one token.
result_line() { awk 'NF { gsub(/[[:space:]]+/, "_"); print; exit }' "$@"; }

if [ "$status" -eq 124 ]; then
    result=timeout
else
    result=$(result_line <<< "$stdout")
    [ -z "$result" ] && result=$(result_line "$stderr_file")
fi

elapsed_ns=$((end_ns - start_ns))
printf 'query=1 %s_result=%s %s_time_seconds=%d.%06d\n' \
    "$solver" "${result:-no-output}" "$solver" \
    "$((elapsed_ns / 1000000000))" "$((elapsed_ns % 1000000000 / 1000))"
