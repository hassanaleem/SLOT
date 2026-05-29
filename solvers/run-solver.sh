#!/bin/bash
# Generic query runner. Called by each solver wrapper.
# Usage: run-solver.sh <solver-name> <solver-binary> <file.smt2>
set -euo pipefail

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <solver-name> <solver-binary> <file.smt2>" >&2
    exit 1
fi

solver_name=$1
solver_bin=$2
input_file=$3
solver_timeout_seconds="${SLOT_SOLVER_TIMEOUT_SECONDS:-}"

if [ ! -f "$input_file" ]; then
    echo "File not found: $input_file" >&2
    exit 1
fi

if ! command -v "$solver_bin" >/dev/null 2>&1; then
    echo "$solver_bin not found in PATH" >&2
    exit 1
fi

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT HUP INT TERM

first_nonempty_line() {
    awk 'NF { print; exit }' "$1"
}

compact_result() {
    printf '%s' "$1" | tr '\n' ' ' | sed 's/[[:space:]]\+/_/g'
}

run_solver_on_query() {
    local query_file=$1
    local stdout_file="$tmpdir/stdout.txt"
    local stderr_file="$tmpdir/stderr.txt"
    local result=""

    local start_ns end_ns
    start_ns=$(date +%s%N)
    local solver_cmd=("$solver_bin" "$query_file")
    if [ -n "$solver_timeout_seconds" ]; then
        solver_cmd=(timeout "$solver_timeout_seconds" "${solver_cmd[@]}")
    fi

    if "${solver_cmd[@]}" >"$stdout_file" 2>"$stderr_file"; then
        end_ns=$(date +%s%N)
        result=$(first_nonempty_line "$stdout_file")
        [ -z "$result" ] && result=$(first_nonempty_line "$stderr_file")
    else
        local status=$?
        end_ns=$(date +%s%N)
        if [ "$status" -eq 124 ]; then
            result="timeout"
        else
            result=$(first_nonempty_line "$stderr_file")
            [ -z "$result" ] && result=$(first_nonempty_line "$stdout_file")
        fi
    fi

    [ -z "$result" ] && result="no-output"

    local time_seconds
    time_seconds=$(awk -v start="$start_ns" -v end="$end_ns" \
        'BEGIN { printf "%.6f", (end - start) / 1000000000 }')
    printf '%s,%s\n' "$(compact_result "$result")" "$time_seconds"
}

state_file="$tmpdir/state.smt2"
: > "$state_file"

query_count=0

while IFS= read -r line || [ -n "$line" ]; do
    if [ "$line" = "(check-sat)" ]; then
        query_count=$((query_count + 1))
        query_file="$tmpdir/query_${query_count}.smt2"
        cp "$state_file" "$query_file"
        printf '%s\n' "$line" >> "$query_file"

        data=$(run_solver_on_query "$query_file")
        result=${data%,*}
        time=${data#*,}

        printf 'query=%s %s_result=%s %s_time_seconds=%s\n' \
            "$query_count" "$solver_name" "$result" "$solver_name" "$time"
    elif [ "$line" = "(reset)" ]; then
        : > "$state_file"
    else
        printf '%s\n' "$line" >> "$state_file"
    fi
done < "$input_file"

if [ "$query_count" -eq 0 ]; then
    echo "No check-sat commands found in $input_file" >&2
    exit 1
fi
