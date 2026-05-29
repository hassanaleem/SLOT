#!/bin/bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <file.smt2>" >&2
    exit 1
fi

if [ ! -f "$1" ]; then
    echo "File not found: $1" >&2
    exit 1
fi

if ! command -v z3 >/dev/null 2>&1; then
    echo "z3 not found in PATH" >&2
    exit 1
fi

input_file=$1
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT HUP INT TERM

first_nonempty_line() {
    awk 'NF { print; exit }' "$1"
}

compact_result() {
    printf '%s' "$1" | tr '\n' ' ' | sed 's/[[:space:]]\+/_/g'
}

run_solver_on_query() {
    local solver_name=$1
    local query_file=$2
    shift 2

    local stdout_file="$tmpdir/${solver_name}_stdout.txt"
    local stderr_file="$tmpdir/${solver_name}_stderr.txt"
    local result=""
    local time_seconds=""
    local start_ns=""
    local end_ns=""

    start_ns=$(date +%s%N)
    if "$@" "$query_file" >"$stdout_file" 2>"$stderr_file"; then
        end_ns=$(date +%s%N)
        result=$(first_nonempty_line "$stdout_file")
        if [ -z "$result" ]; then
            result=$(first_nonempty_line "$stderr_file")
        fi
    else
        end_ns=$(date +%s%N)
        result=$(first_nonempty_line "$stderr_file")
        if [ -z "$result" ]; then
            result=$(first_nonempty_line "$stdout_file")
        fi
    fi

    if [ -z "$result" ]; then
        result="no-output"
    fi

    time_seconds=$(awk -v start="$start_ns" -v end="$end_ns" 'BEGIN { printf "%.6f", (end - start) / 1000000000 }')
    printf '%s,%s\n' "$(compact_result "$result")" "$time_seconds"
}

state_file="$tmpdir/state.smt2"
: > "$state_file"

query_count=0
line=""

while IFS= read -r line || [ -n "$line" ]; do
    if [ "$line" = "(check-sat)" ]; then
        query_count=$((query_count + 1))
        query_file="$tmpdir/query_${query_count}.smt2"
        cp "$state_file" "$query_file"
        printf '%s\n' "$line" >> "$query_file"

        z3_data=$(run_solver_on_query z3 "$query_file" z3)

        z3_result=${z3_data%,*}
        z3_time=${z3_data#*,}

        printf 'query=%s z3_result=%s z3_time_seconds=%s\n' \
            "$query_count" "$z3_result" "$z3_time"
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
