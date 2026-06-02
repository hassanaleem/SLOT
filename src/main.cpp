#include "SMTFormula.h"
#include "LLVMNode.h"
#include <fstream>
#include <streambuf>
#include <sstream>
#include <chrono>
#include <vector>

#include "llvm/IRReader/IRReader.h"
#include "llvm/Support/SourceMgr.h"
#include "llvm/Transforms/InstCombine/InstCombine.h"
#include "llvm/Transforms/AggressiveInstCombine/AggressiveInstCombine.h"
#include "llvm/Transforms/Scalar/Reassociate.h"
#include "llvm/Transforms/Scalar/SCCP.h"
#include "llvm/Transforms/Scalar/DCE.h"
#include "llvm/Transforms/Scalar/ADCE.h"
#include "llvm/Transforms/Scalar/InstSimplifyPass.h"
#include "llvm/Transforms/Scalar/GVN.h"
#include "llvm/Transforms/Scalar/EarlyCSE.h"
#include "llvm/Transforms/Scalar/LoopRolling.h"
#include "llvm/Transforms/Utils/LoopSimplify.h"
#include "llvm/Transforms/Utils/LCSSA.h"
#include "llvm/Transforms/Scalar/IndVarSimplify.h"
#include "llvm/Transforms/Scalar/LICM.h"
#include "llvm/Transforms/Scalar/LoopUnrollPass.h"
#include "llvm/Transforms/Scalar/LoopPassManager.h"
#include "llvm/Transforms/Scalar/SROA.h"
#include "llvm/Transforms/Scalar/SimplifyCFG.h"
#include "llvm/Support/CommandLine.h"

#include "Unmerging-llvm/lower-select.h"

#ifndef LLMAPPING
#define LLMAPPING std::map<std::string, Value *> &
#endif

#ifndef LLVM_FUNCTION_NAME
#define LLVM_FUNCTION_NAME "SMT"
#endif

using namespace SLOT;
using namespace std::chrono;

void Help()
{
  std::cout << "SLOT arguments:\n";
  std::cout << "   -h             : See help menu\n";
  std::cout << "   -s <file>      : The input SMTLIB2 format file (required)\n";
  std::cout << "   -o <file>      : The output file. If not provided, output is sent to stdout\n";
  std::cout << "   -lu <file>     : Output intermediate LLVM IR before optimization (optional)\n";
  std::cout << "   -emit-ll-only  : With -s and -lu, stop after writing the pre-optimization LLVM IR\n";
  std::cout << "   -lo <file>     : Output intermediate LLVM IR after optimization (optional)\n";
  std::cout << "   -m             : Convert constant shifts to multiplication\n";
  std::cout << "   -t <file>      : Output statistics file. If not provided, output is sent to stdout\n";
  std::cout << "   -pall          : Run all relevant passes (roughly equivalent to -O3 in LLVM). By default, no passes are run\n";
  std::cout << "   -loopopt       : Run loop optimization passes (loop-rolling in always mode, indvars)\n";
  std::cout << "   -instcombine   : Run instcombine pass\n";
  std::cout << "   -ainstcombine  : Run aggressive instcombine pass\n";
  std::cout << "   -reassociate   : Run reassociate pass\n";
  std::cout << "   -sccp          : Run sparse conditional constant propagation (SCCP) pass\n";
  std::cout << "   -dce           : Run dead code elimination (DCE) pass\n";
  std::cout << "   -adce          : Run aggressive dead code elimination (ADCE) pass\n";
  std::cout << "   -instsimplify  : Run instsimplify pass\n";
  std::cout << "   -gvn           : Run global value numbering (GVN) pass\n";
  std::cout << "   -unmerge       : Run the unmerge/lower-select pass\n";
  std::cout << "   -nounmerge     : Disable unmerge/lower-select and loop optimizations (-loopopt), including when -pall is used\n";
  std::cout << "   -unmerge-first <n>  : Lower only the first n select instructions\n";
  std::cout << "   -unmerge-last <n>   : Lower only the last n select instructions\n";
  std::cout << "   -unmerge-random <n> : Lower n randomly chosen select instructions\n";
  std::cout << "   -unmerge-chain <n>  : Lower the n select instructions with the deepest condition chains\n";
  std::cout << "   -unmerge-all        : Lower all select instructions (no filtering)\n";
  std::cout << "   -li <file>     : Load LLVM IR directly (skip SMT2 frontend). Requires a function named '" << LLVM_FUNCTION_NAME << "'\n";
  std::cout << "   -single-query  : Produce one SMT query using implies-based encoding (no path splitting). Avoids exponential blowup on large inputs\n";
  std::cout << "   -max-paths <n>  : Cap the number of queries produced by path splitting. When the limit is\n";
  std::cout << "                     reached, unresolved selects in remaining paths use implies-based encoding.\n";
  std::cout << "                     Default: 0 (unlimited, may OOM on inputs with many selects)\n";
  std::cout << "   -path-strategy <bfs|dfs> : Control SMT path splitting strategy. Default: bfs\n";
  std::cout << "   -bfs|-dfs      : Short aliases for -path-strategy bfs|dfs\n";
}

// Not safe: assumes HasFlag returned true and that there is an argument after the flag of interest
char *GetFlag(int argc, char *argv[], const std::string &flag)
{
  for (int i = 1; i < argc - 1; i++)
  {
    if (flag.compare(argv[i]) == 0)
    {
      return argv[i + 1];
    }
  }
  return 0;
}

bool HasFlag(int argc, char *argv[], const std::string &flag)
{
  for (int i = 1; i < argc; i++)
  {
    if (flag.compare(argv[i]) == 0)
    {
      return true;
    }
  }
  return false;
}

PathExplorationStrategy ParsePathStrategy(int argc, char *argv[])
{
  if (HasFlag(argc, argv, "-bfs") && HasFlag(argc, argv, "-dfs"))
  {
    std::cerr << "Cannot specify both -bfs and -dfs.\n";
    exit(1);
  }

  if (HasFlag(argc, argv, "-bfs"))
  {
    return PathExplorationStrategy::BFS;
  }

  if (HasFlag(argc, argv, "-dfs"))
  {
    return PathExplorationStrategy::DFS;
  }

  if (!HasFlag(argc, argv, "-path-strategy"))
  {
    return PathExplorationStrategy::BFS;
  }

  char *strategy = GetFlag(argc, argv, "-path-strategy");
  if (strategy == nullptr)
  {
    std::cerr << "Missing value for -path-strategy. Expected bfs or dfs.\n";
    exit(1);
  }

  std::string value(strategy);
  if (value == "bfs")
  {
    return PathExplorationStrategy::BFS;
  }
  if (value == "dfs")
  {
    return PathExplorationStrategy::DFS;
  }

  std::cerr << "Invalid -path-strategy '" << value << "'. Expected bfs or dfs.\n";
  exit(1);
}

std::string PrintPathStrategy(PathExplorationStrategy strategy)
{
  switch (strategy)
  {
  case PathExplorationStrategy::BFS:
    return "bfs";
  case PathExplorationStrategy::DFS:
    return "dfs";
  }

  return "unknown";
}

#define LOOP_OPT 1
#define INST_COMBINE 2
#define AG_INST_COMBINE 4
#define REASSOCIATE 8
#define SCCP 16
#define DCE 32
#define ADCE 64
#define INST_SIMPLIFY 128
#define GVN_FLAG 256
#define UNMERGE 512
#define ALL_PASSES (LOOP_OPT | INST_COMBINE | AG_INST_COMBINE | REASSOCIATE | SCCP | DCE | ADCE | INST_SIMPLIFY | GVN_FLAG | UNMERGE)

unsigned short ParsePasses(int argc, char *argv[])
{
  unsigned short toReturn = 0;
  if (HasFlag(argc, argv, "-pall"))
  {
    toReturn = ALL_PASSES;
  }
  else
  {
    if (HasFlag(argc, argv, "-loopopt"))
    {
      toReturn |= LOOP_OPT;
    }
    if (HasFlag(argc, argv, "-instcombine"))
    {
      toReturn |= INST_COMBINE;
    }
    if (HasFlag(argc, argv, "-ainstcombine"))
    {
      toReturn |= AG_INST_COMBINE;
    }
    if (HasFlag(argc, argv, "-reassociate"))
    {
      toReturn |= REASSOCIATE;
    }
    if (HasFlag(argc, argv, "-sccp"))
    {
      toReturn |= SCCP;
    }
    if (HasFlag(argc, argv, "-dce"))
    {
      toReturn |= DCE;
    }
    if (HasFlag(argc, argv, "-adce"))
    {
      toReturn |= ADCE;
    }
    if (HasFlag(argc, argv, "-instsimplify"))
    {
      toReturn |= INST_SIMPLIFY;
    }
    if (HasFlag(argc, argv, "-gvn"))
    {
      toReturn |= GVN_FLAG;
    }
    if (HasFlag(argc, argv, "-unmerge"))
    {
      toReturn |= UNMERGE;
    }
  }

  if (HasFlag(argc, argv, "-nounmerge"))
  {
    toReturn &= ~(UNMERGE | LOOP_OPT);
  }
  return toReturn;
}

std::string PrintPasses(unsigned short flags)
{
  return ((flags & LOOP_OPT) ? "1" : "0") + ((std::string) ",") +
         ((flags & INST_COMBINE) ? "1" : "0") + "," +
         ((flags & AG_INST_COMBINE) ? "1" : "0") + "," +
         ((flags & REASSOCIATE) ? "1" : "0") + "," +
         ((flags & SCCP) ? "1" : "0") + "," +
         ((flags & DCE) ? "1" : "0") + "," +
         ((flags & ADCE) ? "1" : "0") + "," +
         ((flags & INST_SIMPLIFY) ? "1" : "0") + "," +
         ((flags & GVN_FLAG) ? "1" : "0") + "," +
         ((flags & UNMERGE) ? "1" : "0");
}

struct PassTimings
{
  duration<double> loopOpt{};
  duration<double> instCombine{};
  duration<double> agInstCombine{};
  duration<double> earlyCSE{};
  duration<double> reassociate{};
  duration<double> sccp{};
  duration<double> dce{};
  duration<double> adce{};
  duration<double> instSimplify{};
  duration<double> gvn{};
  duration<double> unmerge{};
};

std::string PrintPassTimings(const PassTimings &timings)
{
  return std::to_string(timings.loopOpt.count()) + "," +
         std::to_string(timings.instCombine.count()) + "," +
         std::to_string(timings.agInstCombine.count()) + "," +
         std::to_string(timings.earlyCSE.count()) + "," +
         std::to_string(timings.reassociate.count()) + "," +
         std::to_string(timings.sccp.count()) + "," +
         std::to_string(timings.dce.count()) + "," +
         std::to_string(timings.adce.count()) + "," +
         std::to_string(timings.instSimplify.count()) + "," +
         std::to_string(timings.gvn.count()) + "," +
         std::to_string(timings.unmerge.count());
}

LowerSelectConfig ParseUnmergeConfig(int argc, char *argv[], unsigned short &passes)
{
  bool hasFirst = HasFlag(argc, argv, "-unmerge-first");
  bool hasLast = HasFlag(argc, argv, "-unmerge-last");
  bool hasRandom = HasFlag(argc, argv, "-unmerge-random");
  bool hasChain = HasFlag(argc, argv, "-unmerge-chain");
  bool hasAll = HasFlag(argc, argv, "-unmerge-all");

  if ((int)hasFirst + (int)hasLast + (int)hasRandom + (int)hasChain + (int)hasAll > 1)
  {
    std::cerr << "Cannot specify more than one of -unmerge-first, -unmerge-last, -unmerge-random, -unmerge-chain, -unmerge-all.\n";
    exit(1);
  }

  LowerSelectConfig cfg;

  if (hasFirst || hasLast || hasRandom || hasChain || hasAll)
  {
    if (!HasFlag(argc, argv, "-nounmerge"))
      passes |= UNMERGE;
  }

  if (hasAll)
  {
    cfg.strategy = SelectionStrategy::All;
  }
  else if (hasFirst)
  {
    char *n = GetFlag(argc, argv, "-unmerge-first");
    if (!n)
    {
      std::cerr << "Missing count for -unmerge-first.\n";
      exit(1);
    }
    cfg.strategy = SelectionStrategy::First;
    cfg.count = std::stoul(n);
  }
  else if (hasLast)
  {
    char *n = GetFlag(argc, argv, "-unmerge-last");
    if (!n)
    {
      std::cerr << "Missing count for -unmerge-last.\n";
      exit(1);
    }
    cfg.strategy = SelectionStrategy::Last;
    cfg.count = std::stoul(n);
  }
  else if (hasRandom)
  {
    char *n = GetFlag(argc, argv, "-unmerge-random");
    if (!n)
    {
      std::cerr << "Missing count for -unmerge-random.\n";
      exit(1);
    }
    cfg.strategy = SelectionStrategy::Random;
    cfg.count = std::stoul(n);
  }
  else if (hasChain)
  {
    char *n = GetFlag(argc, argv, "-unmerge-chain");
    if (!n)
    {
      std::cerr << "Missing count for -unmerge-chain.\n";
      exit(1);
    }
    cfg.strategy = SelectionStrategy::Chain;
    cfg.count = std::stoul(n);
  }

  return cfg;
}

unsigned short RunPasses(unsigned short flags, Function &fun, PassTimings &timings, const LowerSelectConfig &unmergeConfig)
{
  // instcombine and aggressive instcombine are run twice, according to the -O3 optimization pass sequence
  LoopAnalysisManager LAM;
  FunctionAnalysisManager FAM;
  CGSCCAnalysisManager CGAM;
  ModuleAnalysisManager MAM;

  PassBuilder PB;

  PB.registerModuleAnalyses(MAM);
  PB.registerCGSCCAnalyses(CGAM);
  PB.registerFunctionAnalyses(FAM);
  PB.registerLoopAnalyses(LAM);
  PB.crossRegisterProxies(LAM, FAM, CGAM, MAM);

  int count = fun.getEntryBlock().sizeWithoutDebug();
  unsigned short used = 0;

  // if (flags & LOOP_OPT)
  // {
  //   // recover possible loop structures
  //   auto passStart = high_resolution_clock::now();

  //   // RoLAG's LoopRolling pass exposes AlwaysRoll only as a hidden cl::opt.
  //   // Force it while the pass runs so profitability never suppresses rolling.
  //   {
  //     auto &clOpts = cl::getRegisteredOptions();
  //     auto it = clOpts.find("loop-rolling-always");

  //     if (it == clOpts.end())
  //     {
  //       std::cerr << "Missing RoLAG loop-rolling option: loop-rolling-always.\n";
  //       exit(1);
  //     }

  //     auto *alwaysRoll = static_cast<cl::opt<bool> *>(it->second);
  //     bool savedAlwaysRoll = alwaysRoll->getValue();
  //     *alwaysRoll = true;

  //     LoopRolling().run(fun, FAM);
  //     FAM.invalidate(fun, PreservedAnalyses::none());

  //     *alwaysRoll = savedAlwaysRoll;
  //   }

  //   // Canonicalize the loop produced by loop rolling.

  //   // Simplify induction variables so later unrolling can analyze the loop.
  //   // createFunctionToLoopPassAdaptor(IndVarSimplifyPass()).run(fun, FAM);
  //   // FAM.invalidate(fun, PreservedAnalyses::none());

  //   timings.loopOpt += high_resolution_clock::now() - passStart;

  //   if (fun.getEntryBlock().sizeWithoutDebug() != count)
  //   {
  //     count = fun.getEntryBlock().sizeWithoutDebug();
  //     used |= LOOP_OPT;
  //   }
  // }
  if (flags & INST_COMBINE)
  {
    auto passStart = high_resolution_clock::now();
    InstCombinePass().run(fun, FAM);
    timings.instCombine += high_resolution_clock::now() - passStart;
    if (fun.getEntryBlock().sizeWithoutDebug() != count)
    {
      count = fun.getEntryBlock().sizeWithoutDebug();
      used |= INST_COMBINE;
    }
  }

  if (flags & AG_INST_COMBINE)
  {
    auto passStart = high_resolution_clock::now();
    AggressiveInstCombinePass().run(fun, FAM);
    timings.agInstCombine += high_resolution_clock::now() - passStart;
    if (fun.getEntryBlock().sizeWithoutDebug() != count)
    {
      count = fun.getEntryBlock().sizeWithoutDebug();
      used |= AG_INST_COMBINE;
    }
  }

  auto earlyCSEStart = high_resolution_clock::now();
  EarlyCSEPass().run(fun, FAM);
  timings.earlyCSE += high_resolution_clock::now() - earlyCSEStart;

  if (flags & REASSOCIATE)
  {
    auto passStart = high_resolution_clock::now();
    ReassociatePass().run(fun, FAM);
    timings.reassociate += high_resolution_clock::now() - passStart;
    if (fun.getEntryBlock().sizeWithoutDebug() != count)
    {
      count = fun.getEntryBlock().sizeWithoutDebug();
      used |= REASSOCIATE;
    }
  }

  if (flags & SCCP)
  {
    auto passStart = high_resolution_clock::now();
    SCCPPass().run(fun, FAM);
    timings.sccp += high_resolution_clock::now() - passStart;
    if (fun.getEntryBlock().sizeWithoutDebug() != count)
    {
      count = fun.getEntryBlock().sizeWithoutDebug();
      used |= SCCP;
    }
  }

  if (flags & DCE)
  {
    auto passStart = high_resolution_clock::now();
    DCEPass().run(fun, FAM);
    timings.dce += high_resolution_clock::now() - passStart;
    if (fun.getEntryBlock().sizeWithoutDebug() != count)
    {
      count = fun.getEntryBlock().sizeWithoutDebug();
      used |= DCE;
    }
  }

  if (flags & ADCE)
  {
    auto passStart = high_resolution_clock::now();
    ADCEPass().run(fun, FAM);
    timings.adce += high_resolution_clock::now() - passStart;
    if (fun.getEntryBlock().sizeWithoutDebug() != count)
    {
      count = fun.getEntryBlock().sizeWithoutDebug();
      used |= ADCE;
    }
  }

  if (flags & INST_SIMPLIFY)
  {
    auto passStart = high_resolution_clock::now();
    InstSimplifyPass().run(fun, FAM);
    timings.instSimplify += high_resolution_clock::now() - passStart;
    if (fun.getEntryBlock().sizeWithoutDebug() != count)
    {
      count = fun.getEntryBlock().sizeWithoutDebug();
      used |= INST_SIMPLIFY;
    }
  }

  if (flags & GVN_FLAG)
  {
    auto passStart = high_resolution_clock::now();
    llvm::GVN().run(fun, FAM);
    timings.gvn += high_resolution_clock::now() - passStart;
    if (fun.getEntryBlock().sizeWithoutDebug() != count)
    {
      count = fun.getEntryBlock().sizeWithoutDebug();
      used |= GVN_FLAG;
    }
  }

  if (flags & INST_COMBINE)
  {
    auto passStart = high_resolution_clock::now();
    InstCombinePass().run(fun, FAM);
    timings.instCombine += high_resolution_clock::now() - passStart;
    if (fun.getEntryBlock().sizeWithoutDebug() != count)
    {
      count = fun.getEntryBlock().sizeWithoutDebug();
      used |= INST_COMBINE;
    }
  }

  if (flags & AG_INST_COMBINE)
  {
    auto passStart = high_resolution_clock::now();
    AggressiveInstCombinePass().run(fun, FAM);
    timings.agInstCombine += high_resolution_clock::now() - passStart;
    if (fun.getEntryBlock().sizeWithoutDebug() != count)
    {
      count = fun.getEntryBlock().sizeWithoutDebug();
      used |= AG_INST_COMBINE;
    }
  }

  // if (flags & LOOP_OPT)
  // {
  //   // Re-canonicalize rolled loops so the unroller can analyse them
  //   // LoopSimplifyPass().run(fun, FAM);

  //   // LCSSAPass().run(fun, FAM);
  //   // createFunctionToLoopPassAdaptor(IndVarSimplifyPass()).run(fun, FAM);
  //   // FAM.invalidate(fun, PreservedAnalyses::none());

  //   {
  //     auto &clOpts = cl::getRegisteredOptions();

  //     auto *thresh = static_cast<cl::opt<unsigned> *>(
  //         clOpts.lookup("unroll-threshold"));
  //     auto *partialThresh = static_cast<cl::opt<unsigned> *>(
  //         clOpts.lookup("unroll-partial-threshold"));
  //     auto *aggThresh = static_cast<cl::opt<unsigned> *>(
  //         clOpts.lookup("unroll-threshold-aggressive"));
  //     auto *maxCount = static_cast<cl::opt<unsigned> *>(
  //         clOpts.lookup("unroll-max-count"));
  //     auto *fullMax = static_cast<cl::opt<unsigned> *>(
  //         clOpts.lookup("unroll-full-max-count"));

  //     unsigned savedThresh = thresh ? (unsigned)*thresh : 150u;
  //     unsigned savedPartial = partialThresh ? (unsigned)*partialThresh : 150u;
  //     unsigned savedAgg = aggThresh ? (unsigned)*aggThresh : 300u;
  //     unsigned savedMaxCount = maxCount ? (unsigned)*maxCount : UINT_MAX;
  //     unsigned savedMax = fullMax ? (unsigned)*fullMax : UINT_MAX;

  //     if (thresh)
  //     {
  //       thresh->reset();
  //       thresh->addOccurrence(0, "unroll-threshold", "1000000");
  //     }
  //     if (partialThresh)
  //     {
  //       partialThresh->reset();
  //       partialThresh->addOccurrence(0, "unroll-partial-threshold", "1000000");
  //     }
  //     if (aggThresh)
  //     {
  //       aggThresh->reset();
  //       aggThresh->addOccurrence(0, "unroll-threshold-aggressive", "1000000");
  //     }
  //     if (maxCount)
  //     {
  //       maxCount->reset();
  //       maxCount->addOccurrence(0, "unroll-max-count", "1000");
  //     }
  //     if (fullMax)
  //     {
  //       fullMax->reset();
  //       fullMax->addOccurrence(0, "unroll-full-max-count", "1000");
  //     }

  //     LoopUnrollPass(LoopUnrollOptions(/*OptLevel=*/3).setPartial(true).setFullUnrollMaxCount(1000u)).run(fun, FAM);
  //     FAM.invalidate(fun, PreservedAnalyses::none());
  //   }

  //   SimplifyCFGPass().run(fun, FAM);
  //   FAM.invalidate(fun, PreservedAnalyses::none());

  //   EarlyCSEPass().run(fun, FAM);
  //   FAM.invalidate(fun, PreservedAnalyses::none());

  //   InstCombinePass().run(fun, FAM);
  //   FAM.invalidate(fun, PreservedAnalyses::none());

  //   DCEPass().run(fun, FAM);
  //   FAM.invalidate(fun, PreservedAnalyses::none());

  //   SROA().run(fun, FAM);
  //   FAM.invalidate(fun, PreservedAnalyses::none());

  //   if (fun.getEntryBlock().sizeWithoutDebug() != count)
  //   {
  //     count = fun.getEntryBlock().sizeWithoutDebug();
  //     used |= LOOP_OPT;
  //   }
  // }

  if (flags & UNMERGE)
  {
    auto passStart = high_resolution_clock::now();
    RunLowerSelectPass(fun, unmergeConfig);
    timings.unmerge += high_resolution_clock::now() - passStart;
    if (fun.getEntryBlock().sizeWithoutDebug() != count)
    {
      count = fun.getEntryBlock().sizeWithoutDebug();
      used |= UNMERGE;
    }
  }

  return used;
}

int LLVMFunction::varCounter = 0;

int main(int argc, char *argv[])
{
  bool shiftToMultiply = false;
  if (HasFlag(argc, argv, "-h"))
  {
    Help();
    exit(0);
  }
  if (HasFlag(argc, argv, "-m"))
  {
    shiftToMultiply = true;
  }

  bool hasInputSMT = HasFlag(argc, argv, "-s");
  bool emitLLOnly = HasFlag(argc, argv, "-emit-ll-only");
  bool hasInputLL = HasFlag(argc, argv, "-li");

  if (!hasInputSMT && !hasInputLL)
  {
    std::cout << "Must specify input file with -s or -li.\n";
    return 1;
  }
  if (hasInputSMT && hasInputLL)
  {
    std::cout << "Cannot specify both -s and -li.\n";
    return 1;
  }

  if (emitLLOnly && hasInputLL)
  {
    std::cout << "-emit-ll-only only applies when reading SMT with -s.\n";
    return 1;
  }
  if (emitLLOnly && !HasFlag(argc, argv, "-lu"))
  {
    std::cout << "-emit-ll-only requires -lu <file>.\n";
    return 1;
  }

  unsigned short parsedPasses = ParsePasses(argc, argv);
  LowerSelectConfig unmergeConfig = ParseUnmergeConfig(argc, argv, parsedPasses);
  PathExplorationStrategy pathStrategy = ParsePathStrategy(argc, argv);
  bool singleQuery = HasFlag(argc, argv, "-single-query");

  size_t maxPaths = 0;
  if (HasFlag(argc, argv, "-max-paths"))
  {
    char *maxPathsStr = GetFlag(argc, argv, "-max-paths");
    if (!maxPathsStr)
    {
      std::cerr << "Missing value for -max-paths.\n";
      return 1;
    }
    maxPaths = std::stoul(maxPathsStr);
  }

  LLVMContext lcx;
  std::unique_ptr<Module> lmodule;
  Function *fun = nullptr;
  duration<double> frontTime{}, optTime{};
  unsigned short usedPasses = 0;
  PassTimings passTimings;
  const char *statsInputName = nullptr;

  if (hasInputLL)
  {
    char *liFilename = GetFlag(argc, argv, "-li");
    if (!liFilename)
    {
      std::cerr << "Invalid -li file name.\n";
      return 1;
    }
    statsInputName = liFilename;

    SMDiagnostic err;
    lmodule = parseIRFile(liFilename, err, lcx);
    if (!lmodule)
    {
      err.print(argv[0], llvm::errs());
      return 1;
    }
    fun = lmodule->getFunction(LLVM_FUNCTION_NAME);
    if (!fun)
    {
      std::cerr << "No function named '" << LLVM_FUNCTION_NAME << "' found in " << liFilename << "\n";
      return 1;
    }

    auto optStart = high_resolution_clock::now();
    usedPasses = RunPasses(parsedPasses, *fun, passTimings, unmergeConfig);
    auto optEnd = high_resolution_clock::now();
    optTime = optEnd - optStart;

    char *loFilename;
    if (HasFlag(argc, argv, "-lo") && (loFilename = GetFlag(argc, argv, "-lo")))
    {
      std::error_code ec;
      raw_fd_ostream file(loFilename, ec);
      if (ec)
      {
        std::cerr << "Error opening -lo file: " << ec.message() << "\n";
        return 1;
      }
      lmodule->print(file, nullptr);
    }
  }
  else
  {
    char *inputFilename = GetFlag(argc, argv, "-s");
    if (!inputFilename)
    {
      std::cout << "Invalid input file name.\n";
      return 1;
    }
    statsInputName = inputFilename;

    lmodule = std::make_unique<Module>(inputFilename, lcx);
    IRBuilder<> builder(lcx);

    std::ifstream t(inputFilename);
    std::stringstream buffer;
    buffer << t.rdbuf();
    std::string smt_str = buffer.str();

    // Frontend translation
    auto frontStart = high_resolution_clock::now();
    SMTFormula a = SMTFormula(lcx, lmodule.get(), builder, smt_str, LLVM_FUNCTION_NAME);
    a.ToLLVM();
    auto frontEnd = high_resolution_clock::now();
    frontTime = frontEnd - frontStart;

    fun = lmodule->getFunction(LLVM_FUNCTION_NAME);

    char *luFilename;
    if (HasFlag(argc, argv, "-lu") && (luFilename = GetFlag(argc, argv, "-lu")))
    {
      std::error_code ec;
      raw_fd_ostream file(luFilename, ec);
      if (ec)
      {
        std::cerr << "Error opening -lu file: " << ec.message() << "\n";
        return 1;
      }
      lmodule->print(file, nullptr);
    }
    if (emitLLOnly)
    {
      return 0;
    }

    // Optimization
    auto optStart = high_resolution_clock::now();
    usedPasses = RunPasses(parsedPasses, *fun, passTimings, unmergeConfig);
    auto optEnd = high_resolution_clock::now();
    optTime = optEnd - optStart;

    char *loFilename;
    if (HasFlag(argc, argv, "-lo") && (loFilename = GetFlag(argc, argv, "-lo")))
    {
      std::error_code ec;
      raw_fd_ostream file(loFilename, ec);
      if (ec)
      {
        std::cerr << "Error opening -lo file: " << ec.message() << "\n";
        return 1;
      }
      lmodule->print(file, nullptr);
    }
  }

  context c;

  // Backend translation
  auto backStart = high_resolution_clock::now();
  LLVMFunction f = LLVMFunction(shiftToMultiply, c, fun);
  std::stringstream smtOut;

  if (singleQuery)
  {
    solver querySolver(c);
    querySolver.add(f.ToSMT());
    smtOut << "; query 1\n";
    smtOut << querySolver.to_smt2();
  }
  else
  {
    std::vector<expr> smtQueries = f.ToSMTQueries(pathStrategy, maxPaths);
    for (size_t i = 0; i < smtQueries.size(); ++i)
    {
      solver querySolver(c);
      querySolver.add(smtQueries[i]);
      if (i > 0)
      {
        smtOut << "\n(reset)\n";
      }
      smtOut << "; query " << (i + 1) << "\n";
      smtOut << querySolver.to_smt2();
    }
  }

  auto backEnd = high_resolution_clock::now();
  duration<double> backTime = backEnd - backStart;

  // Print output constraint
  char *outputFilename;
  if (HasFlag(argc, argv, "-o") && (outputFilename = GetFlag(argc, argv, "-o")))
  {
    std::ofstream out(outputFilename);
    out << smtOut.str();
  }
  else
  {
    std::cout << smtOut.str();
  }

  // Print statistics
  char *statsFilename;
  if (HasFlag(argc, argv, "-t") && (statsFilename = GetFlag(argc, argv, "-t")))
  {
    std::ofstream out;
    out.open(statsFilename, std::ios_base::app);
    out << statsInputName << "," << (shiftToMultiply ? "true" : "false") << "," << PrintPathStrategy(pathStrategy) << "," << PrintPasses(parsedPasses) << "," << frontTime.count() << "," << optTime.count() << "," << backTime.count() << "," << PrintPasses(usedPasses) << "," << PrintPassTimings(passTimings) << "\n";
  }
  else
  {
    std::cout << statsInputName << "," << (shiftToMultiply ? "true" : "false") << "," << PrintPathStrategy(pathStrategy) << "," << PrintPasses(parsedPasses) << "," << frontTime.count() << "," << optTime.count() << "," << backTime.count() << "," << PrintPasses(usedPasses) << "," << PrintPassTimings(passTimings) << "\n";
  }
}
