// C++17/Linux counterpart of parallel_solver.py. Build with:
//   make -C scripts parallel_solver
// Keep the executable in scripts/: run-solver.sh is resolved relative to it.
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <list>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include <fcntl.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;
using namespace std::chrono_literals;

namespace {
volatile sig_atomic_t interrupted = 0;
void on_signal(int signal) { if (!interrupted) interrupted = signal; }
struct Interrupted {};
void check_signal() { if (interrupted) throw Interrupted{}; }

std::runtime_error system_error(const std::string &what) {
    return std::runtime_error(what + ": " + std::strerror(errno));
}

class Fd {
public:
    int value = -1;
    explicit Fd(int fd = -1) : value(fd) {}
    ~Fd() { close(); }
    Fd(const Fd &) = delete;
    Fd &operator=(const Fd &) = delete;
    Fd(Fd &&other) noexcept : value(other.value) { other.value = -1; }
    Fd &operator=(Fd &&other) noexcept {
        if (this != &other) { close(); value = other.value; other.value = -1; }
        return *this;
    }
    void close() { if (value >= 0) { ::close(value); value = -1; } }
};

struct Pipe {
    Fd read, write;
    Pipe() {
        int descriptors[2];
        if (pipe2(descriptors, O_CLOEXEC) < 0) throw system_error("pipe2");
        read.value = descriptors[0];
        write.value = descriptors[1];
    }
};

void nonblocking(const Fd &fd) {
    int flags = fcntl(fd.value, F_GETFL);
    if (flags < 0 || fcntl(fd.value, F_SETFL, flags | O_NONBLOCK) < 0)
        throw system_error("fcntl");
}

class TemporaryDirectory {
public:
    fs::path path;
    TemporaryDirectory() {
        std::vector<fs::path> candidates;
        for (const auto *name : {"TMPDIR", "TEMP", "TMP"})
            if (const char *value = std::getenv(name)) candidates.emplace_back(value);
        candidates.insert(candidates.end(), {"/tmp", "/var/tmp", "/usr/tmp", fs::current_path()});
        for (const auto &directory : candidates) {
            std::string pattern = (directory / "tmpXXXXXX").string();
            if (mkdtemp(pattern.data())) { path = fs::absolute(pattern); return; }
        }
        throw system_error("create temporary directory");
    }
    ~TemporaryDirectory() { std::error_code error; fs::remove_all(path, error); }
};

// Match Python text-mode universal newlines, retaining each line's newline
// in the accumulated declarations/assertions, including a final unterminated line.
bool read_line(std::istream &input, std::string &line) {
    line.clear();
    char ch;
    while (input.get(ch)) {
        if (ch == '\r') {
            if (input.peek() == '\n') input.get();
            line += '\n';
            return true;
        }
        line += ch;
        if (ch == '\n') return true;
    }
    return !line.empty();
}

std::vector<fs::path> extract_queries(const fs::path &input_path, const fs::path &directory) {
    std::ifstream input(input_path, std::ios::binary);
    if (!input) throw std::runtime_error("Cannot open " + input_path.string());
    std::vector<fs::path> queries;
    std::string state, line;
    while (read_line(input, line)) {
        check_signal();
        std::string stripped = line;
        if (!stripped.empty() && stripped.back() == '\n') stripped.pop_back();
        if (stripped == "(check-sat)") {
            fs::path file = directory / ("query_" + std::to_string(queries.size() + 1) + ".smt2");
            std::ofstream query(file);
            query << state << stripped << '\n';
            query.close();
            if (!query) throw std::runtime_error("Cannot write " + file.string());
            queries.push_back(file);
        } else if (stripped == "(reset)") {
            state.clear();
        } else {
            state += line;
        }
    }
    if (input.bad()) throw std::runtime_error("Cannot read " + input_path.string());
    return queries;
}

struct Worker {
    pid_t pid;
    std::size_t index;
    fs::path file;
    Fd stdout_fd, stderr_fd;
    std::string output;
    bool reaped = false;
};

// SIGKILL sweeps the entire session's process group even if the wrapper has
// already exited, so a TERM-resistant solver cannot outlive the scheduler.
void kill_all(std::list<Worker> &workers) noexcept {
    for (auto &worker : workers) kill(-worker.pid, SIGTERM);
    for (auto &worker : workers) {
        const auto deadline = Clock::now() + 5s;
        while (!worker.reaped) {
            pid_t result = waitpid(worker.pid, nullptr, WNOHANG);
            if (result == worker.pid || (result < 0 && errno == ECHILD)) {
                worker.reaped = true;
                break;
            }
            if (Clock::now() >= deadline) break;
            std::this_thread::sleep_for(10ms);
        }
        kill(-worker.pid, SIGKILL);
        if (!worker.reaped) {
            while (waitpid(worker.pid, nullptr, 0) < 0 && errno == EINTR) {}
            worker.reaped = true;
        }
    }
}

struct Workers {
    std::list<Worker> active;  // insertion order, like Python's active dict
    ~Workers() { kill_all(active); }
};

[[noreturn]] void child_error(int fd) {
    int error = errno;
    // Only async-signal-safe operations between fork and exec.
    while (::write(fd, &error, sizeof(error)) < 0 && errno == EINTR) {}
    _exit(127);
}

void start_worker(Workers &workers, std::size_t index, const fs::path &file,
                  const std::string &solver, const fs::path &wrapper) {
    Pipe output, errors, exec_errors;
    nonblocking(output.read);
    nonblocking(errors.read);
    const std::string command = wrapper.string(), input = file.string();
    // Allocate the list node before fork, so allocation failure cannot orphan a child.
    workers.active.push_back({-1, index, file, Fd(), Fd(), {}, false});
    Worker &worker = workers.active.back();
    pid_t pid = fork();
    if (pid < 0) { workers.active.pop_back(); throw system_error("fork"); }
    if (pid == 0) {
        if (setsid() < 0) child_error(exec_errors.write.value);
        if (dup2(output.write.value, STDOUT_FILENO) < 0 ||
            dup2(errors.write.value, STDERR_FILENO) < 0) child_error(exec_errors.write.value);
        execl(command.c_str(), command.c_str(), solver.c_str(), input.c_str(), nullptr);
        child_error(exec_errors.write.value);
    }
    worker.pid = pid;
    worker.stdout_fd = std::move(output.read);
    worker.stderr_fd = std::move(errors.read);
    output.write.close();
    errors.write.close();
    exec_errors.write.close();
    int error = 0;
    ssize_t count;
    do { count = ::read(exec_errors.read.value, &error, sizeof(error)); }
    while (count < 0 && errno == EINTR);
    if (count > 0) {
        errno = error;
        throw system_error("execute " + command);
    }
    if (count < 0) throw system_error("read exec status");
    check_signal();
}

void drain(Fd &fd, std::string *output) {
    char buffer[8192];
    while (fd.value >= 0) {
        check_signal();
        ssize_t count = ::read(fd.value, buffer, sizeof(buffer));
        if (count > 0) { if (output) output->append(buffer, static_cast<std::size_t>(count)); }
        else if (count == 0) { fd.close(); }
        else if (errno == EINTR) { continue; }
        else if (errno == EAGAIN || errno == EWOULDBLOCK) { break; }
        else { throw system_error("read worker output"); }
    }
}

std::string parse_result(const std::string &output, const std::string &solver) {
    std::istringstream tokens(output);
    std::string token, prefix = solver + "_result=";
    while (tokens >> token)
        if (token.compare(0, prefix.size(), prefix) == 0) return token.substr(prefix.size());
    return "unknown";
}

int run(const fs::path &file, const std::string &solver, std::size_t max_workers, double timeout) {
    TemporaryDirectory temporary;
    const auto start = Clock::now();
    const auto elapsed = [&] { return std::chrono::duration<double>(Clock::now() - start).count(); };
    std::cout << "Extracting queries from " << file.string() << " …\n";
    auto queries = extract_queries(file, temporary.path);
    if (queries.empty()) { std::cerr << "No (check-sat) queries found.\n"; return 1; }
    const auto n = queries.size();
    const int width = static_cast<int>(std::to_string(n).size());
    std::cout << "  " << n << " queries, max " << max_workers << " workers, solver=" << solver << '\n'
              << "  extraction took " << std::fixed << std::setprecision(3) << elapsed() << "s\n";
    const fs::path wrapper = fs::canonical("/proc/self/exe").parent_path().parent_path() / "solvers/run-solver.sh";
    Workers workers;
    std::size_t next = 0;
    const auto fill_slots = [&] {
        while (next < n && workers.active.size() < max_workers) {
            check_signal();
            start_worker(workers, next + 1, queries[next], solver, wrapper);
            ++next;
            std::cout << "  [+] query " << std::right << std::setw(width) << next << '/' << n
                      << "  pid=" << workers.active.back().pid << '\n';
        }
    };
    fill_slots();
    while (!workers.active.empty()) {
        check_signal();
        const double seconds = elapsed();
        if (timeout != 0.0 && seconds > timeout) {
            std::cout << "\nTimeout after " << std::setprecision(1) << seconds << "s — killing "
                      << workers.active.size() << " running queries.\nTotal time: "
                      << std::setprecision(6) << timeout << "s\n";
            return 1;
        }
        std::vector<pid_t> done;
        for (auto &worker : workers.active) {
            // Drain both streams while running; the wrapper's stderr stays suppressed.
            drain(worker.stdout_fd, &worker.output);
            drain(worker.stderr_fd, nullptr);
            pid_t result = waitpid(worker.pid, nullptr, WNOHANG);
            if (result == worker.pid) { worker.reaped = true; done.push_back(worker.pid); }
            else if (result < 0 && errno != EINTR) { throw system_error("waitpid"); }
        }
        if (done.empty()) { std::this_thread::sleep_for(50ms); continue; }
        for (pid_t pid : done) {
            auto iterator = std::find_if(workers.active.begin(), workers.active.end(),
                                        [pid](const Worker &worker) { return worker.pid == pid; });
            Worker &worker = *iterator;
            // Match communicate(): collect any last output before interpreting the result.
            while (worker.stdout_fd.value >= 0 || worker.stderr_fd.value >= 0) {
                drain(worker.stdout_fd, &worker.output);
                drain(worker.stderr_fd, nullptr);
                if (worker.stdout_fd.value >= 0 || worker.stderr_fd.value >= 0)
                    std::this_thread::sleep_for(10ms);
            }
            const std::string result = parse_result(worker.output, solver);
            const double seconds = elapsed();
            std::cout << "  [-] query " << std::right << std::setw(width) << worker.index << '/' << n
                      << "  result=" << std::left << std::setw(7) << result
                      << "  elapsed=" << std::fixed << std::setprecision(3) << seconds << "s\n";
            const auto index = worker.index;
            const auto name = worker.file.filename().string();
            workers.active.erase(iterator);
            if (result == "sat") {
                std::cout << "\nSAT — query " << index << " (" << name << ")\nTotal time: "
                          << std::setprecision(6) << seconds << "s\n";
                return 0;
            }
            fill_slots();
        }
    }
    std::cout << "\nNo satisfying query found among " << n << " queries.\nTotal time: "
              << std::fixed << std::setprecision(6) << elapsed() << "s\n";
    return 1;
}

struct Options {
    fs::path file;
    std::string solver = "z3";
    long long workers = 10;
    double timeout = 0.0;
};
struct ArgumentError : std::runtime_error { using std::runtime_error::runtime_error; };
void usage(std::ostream &out, const char *program) {
    out << "usage: " << program << " [-h] [--solver {z3,cvc5,mathsat,opensmt}] [--workers N]"
        << " [--timeout SECONDS] FILE.smt2\n";
}

Options parse_arguments(int argc, char **argv) {
    Options options;
    bool positional_only = false;
    for (int i = 1; i < argc; ++i) {
        std::string argument = argv[i];
        if (!positional_only && (argument == "-h" || argument == "--help")) {
            usage(std::cout, argv[0]);
            std::cout << "\nBounded-parallel SMT solver with sliding-window scheduling\n\n"
                      << "  --solver {z3,cvc5,mathsat,opensmt}  Solver (default: z3)\n"
                      << "  --workers N                       Concurrent workers (default: 10)\n"
                      << "  --timeout SECONDS                 Wall-clock budget for the whole run; 0 = no limit\n";
            std::exit(0);
        }
        if (!positional_only && argument == "--") { positional_only = true; continue; }
        if (!positional_only && argument.size() > 1 && argument.front() == '-') {
            const auto equals = argument.find('=');
            std::string option = argument.substr(0, equals), value;
            if (option != "--solver" && option != "--workers" && option != "--timeout")
                throw ArgumentError("unrecognized argument: " + argument);
            if (equals != std::string::npos) value = argument.substr(equals + 1);
            else if (++i < argc) value = argv[i];
            else throw ArgumentError("argument " + option + ": expected one argument");
            if (option == "--solver") {
                if (value != "z3" && value != "cvc5" && value != "mathsat" && value != "opensmt")
                    throw ArgumentError("argument --solver: invalid choice: " + value);
                options.solver = value;
            } else {
                try {
                    std::size_t end;
                    if (option == "--workers") options.workers = std::stoll(value, &end);
                    else options.timeout = std::stod(value, &end);
                    if (end != value.size()) throw std::invalid_argument("trailing characters");
                } catch (const std::exception &) {
                    throw ArgumentError("argument " + option + ": invalid numeric value: " + value);
                }
            }
        } else {
            if (!options.file.empty()) throw ArgumentError("unrecognized argument: " + argument);
            options.file = argument;
        }
    }
    if (options.file.empty()) throw ArgumentError("the following arguments are required: FILE.smt2");
    return options;
}
} // namespace

int main(int argc, char **argv) {
    // Python is invoked with -u by query-solver.sh; keep logs promptly visible too.
    std::cout << std::unitbuf;
    struct sigaction action {};
    action.sa_handler = on_signal;
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, nullptr);
    sigaction(SIGINT, &action, nullptr);
    try {
        Options options = parse_arguments(argc, argv);
        if (!fs::exists(options.file)) {
            std::cerr << "Error: " << options.file.string() << " not found\n";
            return 1;
        }
        if (options.workers < 1) { std::cerr << "Error: --workers must be >= 1\n"; return 1; }
        return run(options.file, options.solver, static_cast<std::size_t>(options.workers), options.timeout);
    } catch (const ArgumentError &error) {
        usage(std::cerr, argv[0]);
        std::cerr << argv[0] << ": error: " << error.what() << '\n';
        return 2;
    } catch (const Interrupted &) {
        return 128 + interrupted;
    } catch (const std::exception &error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }
}
