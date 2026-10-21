CXX ?= g++
CXXFLAGS ?= -O2 -Wall -Wextra -Wpedantic

.PHONY: all
all: parallel_solver

parallel_solver: parallel_solver.cpp
	@temporary="$@.tmp.$$$$"; trap 'rm -f "$$temporary"' EXIT; \
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -std=c++17 $< -o "$$temporary" $(LDFLAGS) && \
	mv -f "$$temporary" "$@"

