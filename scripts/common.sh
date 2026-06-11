# common.sh — source this file; script_dir is set here via the caller's path

script_dir=$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)

BENCHMARK_DIR="${script_dir}/../slot-benchmark-sat-with-select"
BENCHMARK_LIST="${script_dir}/../torun.txt"
DEFAULT_RESULTS_DIR="${script_dir}/../select-results-strategies"
STRATEGIES=(first last random chain all-bfs all-dfs opt)
SELECT_COUNT=5

# foreach_benchmark <results_dir> <cmd> [args...]
# For each benchmark in BENCHMARK_LIST, calls: <cmd> [args...] <benchmark_path> <results_dir>
foreach_benchmark() {
    local results_dir=$1; shift
    [ ! -f "$BENCHMARK_LIST" ] && { echo "Benchmark list not found: $BENCHMARK_LIST" >&2; return 1; }
    while IFS= read -r bm || [ -n "$bm" ]; do
        [ -z "$bm" ] && continue
        [[ "$bm" == \#* ]] && continue
        "$@" "$BENCHMARK_DIR/$bm" "$results_dir"
    done < "$BENCHMARK_LIST"
}
