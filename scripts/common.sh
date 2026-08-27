# common.sh — source this file; script_dir is set here via the caller's path

script_dir=$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)

BENCHMARK_DIR="${script_dir}/../slot-benchmark-sat-with-select"
BENCHMARK_LIST="${script_dir}/../torun.txt"
DEFAULT_RESULTS_DIR="${script_dir}/../select-results-strategies"
DEFAULT_EXPERIMENTAL_DIR="${script_dir}/../reroll"
SLOT="${script_dir}/../src/slot"
SOLVERS_DIR="${script_dir}/../solvers"
PARALLEL_SOLVER="${script_dir}/parallel_solver.py"
# STRATEGIES=(first last random chain all-bfs all-dfs opt)
STRATEGIES=(chain opt first last random)

SELECT_COUNT=5
# Solver binary to use (z3, cvc5, mathsat, opensmt); must be on PATH.
SOLVER="${SOLVER:-z3}"
# Wall-clock budget for one benchmark solve: parallel_solver.py enforces it
# across the whole run, run-solver.sh per invocation (exported to reach both).
export SLOT_SOLVER_TIMEOUT_SECONDS="${SLOT_SOLVER_TIMEOUT_SECONDS:-650}"
WORKERS="${WORKERS:-16}"
# Cooldown between solver runs; set to 0 to disable.
COOLDOWN_SECONDS="${COOLDOWN_SECONDS:-5}"
# Skip phases whose outputs already exist (1 = skip, 0 = always rerun).
SKIP_DONE="${SKIP_DONE:-0}"

if [ ! -x "$SLOT" ]; then
    echo "Missing executable: $SLOT" >&2
    return 1
fi

# strategy_flags <strategy> — sets slot_flags with the slot arguments for the strategy
strategy_flags() {
    case "$1" in
        first|last|random|chain) slot_flags=("-unmerge-$1" "$SELECT_COUNT") ;;
        all-bfs|all-dfs)         slot_flags=(-unmerge-all -max-paths "$((1 << SELECT_COUNT))" -path-strategy "${1#all-}") ;;
        opt)                     slot_flags=(-nounmerge) ;;
        *)                       echo "Unknown strategy: $1" >&2; return 1 ;;
    esac
    if [ "${SLOT_DISJUNCTION:-0}" = 1 ]; then
        slot_flags+=(-disjunction)
    fi
}

# run_timed <cmd...> — runs the command, sets elapsed_ms, returns the command's status
run_timed() {
    local start_ns status=0
    start_ns=$(date +%s%N)
    "$@" || status=$?
    elapsed_ms=$((($(date +%s%N) - start_ns) / 1000000))
    return $status
}

# should_skip <file> [pattern]
# True when SKIP_DONE=1 and <file> exists (and contains <pattern>, if given).
should_skip() {
    [ "$SKIP_DONE" = 1 ] || return 1
    [ -f "$1" ] || return 1
    [ $# -lt 2 ] || grep -q -- "$2" "$1"
}

# resolve_input <file[.smt2]> [results_dir]
# Sets: input_file, input_base, out_dir
resolve_input() {
    input_file=$1
    [[ "$input_file" != *.smt2 ]] && input_file="${input_file}.smt2"
    input_base=$(basename "$input_file" .smt2)
    out_dir="${2:-$DEFAULT_RESULTS_DIR}/$input_base"
}

# foreach_benchmark <results_dir> <cmd> [args...]
# For each benchmark in BENCHMARK_LIST, calls: <cmd> [args...] <benchmark_path> <results_dir>
foreach_benchmark() {
    local results_dir=$1; shift
    local benchmark_path
    [ ! -f "$BENCHMARK_LIST" ] && { echo "Benchmark list not found: $BENCHMARK_LIST" >&2; return 1; }
    while IFS= read -r bm || [ -n "$bm" ]; do
        [ -z "$bm" ] && continue
        [[ "$bm" == \#* ]] && continue
        if [ "${ALLOW_ABSOLUTE_BENCHMARKS:-0}" = 1 ] && [[ "$bm" == /* ]]; then
            benchmark_path=$bm
        else
            benchmark_path="$BENCHMARK_DIR/$bm"
        fi
        "$@" "$benchmark_path" "$results_dir"
    done < "$BENCHMARK_LIST"
}
