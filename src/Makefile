CC= g++

LLVM_BUILD_DIR := /home/hassan/Desktop/RoLAG/cgo22-rolag-artifact/loop-rolling/build/release
LLVM_CONFIG ?= $(LLVM_BUILD_DIR)/bin/llvm-config

CPPFLAGS= -I/usr/include -I$(shell $(LLVM_CONFIG) --includedir) -I$(LLVM_BUILD_DIR)/include -std=c++17 -fno-rtti -D_GNU_SOURCE -D_DEBUG -D_GLIBCXX_ASSERTIONS -D_LIBCPP_ENABLE_ASSERTIONS -D__STDC_CONSTANT_MACROS -D__STDC_FORMAT_MACROS -D__STDC_LIMIT_MACROS -g -O3 -fexceptions

# Add z3 library flags
Z3_LDFLAGS=-L/usr/lib/x86_64-linux-gnu -lz3

# Use llvm-config to get the necessary flags and libraries
LLVM_LDFLAGS=$(shell $(LLVM_CONFIG) --ldflags)
LLVM_LIBS=$(shell $(LLVM_CONFIG) --system-libs --libs core passes irreader)

LDLIBS=$(Z3_LDFLAGS) $(LLVM_LDFLAGS) $(LLVM_LIBS)  -lrt -ldl -lpthread -lm -lz -ltinfo

main: main.o SMTFormula.o SMTNode.o LLVMFunction.o LLVMNode.o Unmerging-llvm/lower-select.o
	$(CC) $(CPPFLAGS) -o slot main.o SMTFormula.o SMTNode.o LLVMFunction.o LLVMNode.o Unmerging-llvm/lower-select.o $(LDLIBS)
 
main.o: main.cpp SMTFormula.h SMTNode.h LLVMNode.h SLOTExceptions.h #LLVMFunction.h 
	$(CC) $(CPPFLAGS) -c main.cpp
 
SMTNode.o: SMTNode.cpp SMTNode.h SLOTExceptions.h
	$(CC) $(CPPFLAGS) -c SMTNode.cpp

LLVMNode.o: LLVMNode.cpp LLVMNode.h SLOTExceptions.h
	$(CC) $(CPPFLAGS) -c LLVMNode.cpp
 
SMTFormula.o: SMTFormula.cpp SMTFormula.h SLOTExceptions.h
	$(CC) $(CPPFLAGS) -c SMTFormula.cpp

LLVMFunction.o: LLVMFunction.cpp LLVMNode.h SLOTExceptions.h
	$(CC) $(CPPFLAGS) -c LLVMFunction.cpp

Unmerging-llvm/lower-select.o: Unmerging-llvm/lower-select.cpp Unmerging-llvm/lower-select.h
	$(CC) $(CPPFLAGS) -c Unmerging-llvm/lower-select.cpp -o Unmerging-llvm/lower-select.o

clean:
	rm *.o
