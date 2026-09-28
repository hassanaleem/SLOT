#include "LLVMNode.h"
#include "SLOTExceptions.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/Transforms/InstCombine/InstCombine.h"
#include "llvm/Transforms/Scalar/DCE.h"
#include "llvm/Transforms/Scalar/EarlyCSE.h"
#include "llvm/Transforms/Scalar/SCCP.h"
#include <chrono>
#include <deque>
#include <functional>
#include <regex>
#include <set>

#ifndef LLMAPPING
#define LLMAPPING std::map<std::string, Value*>
#endif

namespace SLOT
{
    // Lowering only creates structured diamonds. The join's immediate dominator
    // is its controlling branch, even when an arm contains more diamonds.
    bool GetLoweredPhiInfo(PHINode* phi, LoweredPhiInfo& info, DominatorTree& dominators)
    {
        if (phi->getNumIncomingValues() != 2)
            return false;
        auto* node = dominators.getNode(phi->getParent());
        if (!node || !node->getIDom())
            return false;
        auto* branch = dyn_cast<BranchInst>(node->getIDom()->getBlock()->getTerminator());
        if (!branch || !branch->isConditional())
            return false;

        unsigned trueIndex = dominators.dominates(branch->getSuccessor(0),
                                                  phi->getIncomingBlock(0)) ? 0 : 1;
        if (!dominators.dominates(branch->getSuccessor(0), phi->getIncomingBlock(trueIndex)) ||
            !dominators.dominates(branch->getSuccessor(1), phi->getIncomingBlock(1 - trueIndex)))
            return false;
        info = {branch, phi->getIncomingValue(trueIndex), phi->getIncomingValue(1 - trueIndex)};
        return true;
    }

    namespace
    {
        struct PathState
        {
            std::map<const Value *, const Value *> phiSelections;
            expr condition;
        };

        ReturnInst* FindSingleReturn(Function* function)
        {
            ReturnInst* ret = nullptr;
            for (BasicBlock& bb : *function)
            {
                if (auto* candidate = dyn_cast<ReturnInst>(bb.getTerminator()))
                {
                    if (ret != nullptr)
                    {
                        throw UnsupportedLLVMOpException("multiple return blocks are unsupported", candidate);
                    }
                    ret = candidate;
                }
            }

            if (ret == nullptr)
            {
                throw UnsupportedLLVMOpException("function without a return is unsupported", function);
            }

            return ret;
        }

        expr OptimizePathBody(Function* original, DominatorTree& dominators, Value* result, const PathState& state,
                              bool shiftToMultiply, context& scx, PathOptimizationStats& stats)
        {
            const auto start = std::chrono::steady_clock::now();
            // Keep the original function and path-selection pointers intact. Only
            // clone the expression DAG needed by this path's return value.
            auto eraseFunction = [](Function* function) { function->eraseFromParent(); };
            std::unique_ptr<Function, decltype(eraseFunction)> path(
                Function::Create(original->getFunctionType(), GlobalValue::PrivateLinkage,
                                 "slot.path", original->getParent()), eraseFunction);
            BasicBlock* block = BasicBlock::Create(original->getContext(), "entry", path.get());
            IRBuilder<> builder(block);
            std::map<const Value*, Value*> values;
            for (Argument& arg : original->args())
            {
                Argument* copy = path->getArg(arg.getArgNo());
                copy->setName(arg.getName()); // SMT inputs must retain their names.
                values.emplace(&arg, copy);
            }

            std::set<const Value*> active;
            std::function<Value*(Value*)> materialize = [&](Value* value) -> Value* {
                auto cached = values.find(value);
                if (cached != values.end())
                    return cached->second;
                if (isa<Constant>(value))
                    return value;
                // Constrained FP intrinsics use immutable strings for rounding
                // and exception behavior; these are shared in the LLVM context.
                if (auto* metadata = dyn_cast<MetadataAsValue>(value))
                    if (isa<MDString>(metadata->getMetadata()))
                        return value;
                if (!active.insert(value).second)
                    throw UnsupportedLLVMOpException("cyclic path expression", value);

                Value* copy = nullptr;
                if (auto* phi = dyn_cast<PHINode>(value))
                {
                    auto selected = state.phiSelections.find(phi);
                    if (selected != state.phiSelections.end())
                    {
                        copy = materialize(const_cast<Value*>(selected->second));
                    }
                    else
                    {
                        // A capped path can still have unresolved choices. Preserve
                        // both arms as a select without creating further paths.
                        LoweredPhiInfo info;
                        if (!GetLoweredPhiInfo(phi, info, dominators))
                            throw UnsupportedLLVMOpException("unsupported path PHI", phi);
                        Value* condition = materialize(info.branch->getCondition());
                        Value* whenTrue = materialize(info.trueValue);
                        Value* whenFalse = materialize(info.falseValue);
                        copy = builder.CreateSelect(condition, whenTrue, whenFalse, phi->getName());
                    }
                }
                else if (auto* inst = dyn_cast<Instruction>(value))
                {
                    auto* constrained = dyn_cast<ConstrainedFPIntrinsic>(inst);
                    // LLVM models the FP environment as inaccessible memory.
                    // SLOT's fixed-rounding, exception-ignoring calls are pure
                    // expressions under the SMT semantics used by the frontend.
                    const bool pureConstrainedFP = constrained &&
                        constrained->getExceptionBehavior() == fp::ebIgnore &&
                        constrained->getRoundingMode() != RoundingMode::Dynamic;
                    if (inst->isTerminator() ||
                        ((inst->mayReadOrWriteMemory() || inst->mayHaveSideEffects()) && !pureConstrainedFP))
                        throw UnsupportedLLVMOpException("path optimization requires pure expressions", inst);
                    SmallVector<Value*, 4> operands;
                    for (Value* operand : inst->operands())
                        operands.push_back(materialize(operand));
                    Instruction* cloned = inst->clone();
                    // Metadata can refer to values or scopes in the source function.
                    cloned->dropUnknownNonDebugMetadata();
                    cloned->setDebugLoc(DebugLoc());
                    for (unsigned i = 0; i < operands.size(); ++i)
                        cloned->setOperand(i, operands[i]);
                    builder.Insert(cloned, inst->getName());
                    copy = cloned;
                }
                else
                {
                    throw UnsupportedLLVMOpException("unsupported path value", value);
                }
                active.erase(value);
                values.emplace(value, copy);
                return copy;
            };
            builder.CreateRet(materialize(result));
            if (verifyFunction(*path, &errs()))
                throw std::runtime_error("invalid materialized path function");
            const size_t before = block->size();

            LoopAnalysisManager lam;
            FunctionAnalysisManager fam;
            CGSCCAnalysisManager cgam;
            ModuleAnalysisManager mam;
            PassBuilder pb;
            pb.registerModuleAnalyses(mam);
            pb.registerCGSCCAnalyses(cgam);
            pb.registerFunctionAnalyses(fam);
            pb.registerLoopAnalyses(lam);
            pb.crossRegisterProxies(lam, fam, cgam, mam);
            FunctionPassManager passes;
            passes.addPass(InstCombinePass());
            passes.addPass(SCCPPass());
            passes.addPass(EarlyCSEPass());
            passes.addPass(InstCombinePass());
            passes.addPass(DCEPass());
            passes.run(*path, fam);
            if (verifyFunction(*path, &errs()))
                throw std::runtime_error("invalid optimized path function");

            ++stats.paths;
            stats.instructionsBefore += before;
            for (BasicBlock& bb : *path)
                stats.instructionsAfter += bb.size();
            stats.seconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
            LLVMFunction evaluator(shiftToMultiply, scx, path.get());
            return evaluator.ToSMT();
        }

        expr EvaluateWithSelections(Value* value, bool shiftToMultiply, context& scx, Function* contents,
                                    const std::map<const Value *, const Value *>& phiSelections)
        {
            LLVMFunction evaluator(shiftToMultiply, scx, contents);
            evaluator.phiSelections = phiSelections;
            expr result = LLVMNode::MakeLLVMNode(shiftToMultiply, scx, evaluator, value)->ToSMT();
            return evaluator.hasExtraConstraints ? (evaluator.extraVariables && result) : result;
        }

        PHINode* FindNextLoweredPhi(Value* value, DominatorTree& dominators,
                                    const std::map<const Value *, const Value *>& phiSelections,
                                    std::set<const Value *>& visited)
        {
            if (value == nullptr || !visited.insert(value).second)
            {
                return nullptr;
            }

            if (auto* phi = dyn_cast<PHINode>(value))
            {
                auto selected = phiSelections.find(phi);
                if (selected != phiSelections.end())
                {
                    return FindNextLoweredPhi(const_cast<Value*>(selected->second), dominators, phiSelections, visited);
                }

                LoweredPhiInfo info;
                if (GetLoweredPhiInfo(phi, info, dominators))
                {
                    if (auto* nested = FindNextLoweredPhi(info.branch->getCondition(), dominators, phiSelections, visited))
                    {
                        return nested;
                    }
                    // Choose the enclosing arm before exploring its operands.
                    return phi;
                }

                for (unsigned i = 0; i < phi->getNumIncomingValues(); ++i)
                {
                    if (auto* nested = FindNextLoweredPhi(phi->getIncomingValue(i), dominators, phiSelections, visited))
                    {
                        return nested;
                    }
                }

                return nullptr;
            }

            if (auto* inst = dyn_cast<Instruction>(value))
            {
                for (Value* operand : inst->operands())
                {
                    if (auto* nested = FindNextLoweredPhi(operand, dominators, phiSelections, visited))
                    {
                        return nested;
                    }
                }
            }

            return nullptr;
        }
    }

    LLVMFunction::LLVMFunction(bool t_shiftToMultiply, context& t_scx, Function* t_contents) : shiftToMultiply(t_shiftToMultiply), scx(t_scx), contents(t_contents), dominators(*t_contents), extraVariables(t_scx.bool_val(true)), hasExtraConstraints(false)
    {
        scx.set_rounding_mode(RNE);
        for (Argument* arg = contents->arg_begin(); arg < contents->arg_end(); arg++)
        {
            if (arg->getType()->isIntegerTy())
            {
                //1-wide integer --> boolean
                if (arg->getType()->getIntegerBitWidth() == 1)
                {
                    variables.insert(make_pair(arg->getName().str(), scx.bool_const(arg->getName().str().c_str())));
                }
                else
                {
                    //Regular bitvector case
                    variables.insert(make_pair(arg->getName().str(), scx.bv_const(arg->getName().str().c_str(),arg->getType()->getIntegerBitWidth())));
                }
            }
            else if (arg->getType()->isHalfTy())
            {
                variables.insert(make_pair(arg->getName().str(), scx.fpa_const(arg->getName().str().c_str(), 5, 11)));
            }
            else if (arg->getType()->isFloatTy())
            {
                variables.insert(make_pair(arg->getName().str(), scx.fpa_const(arg->getName().str().c_str(), 8, 24)));
            }
            else if (arg->getType()->isDoubleTy())
            {
                variables.insert(make_pair(arg->getName().str(), scx.fpa_const(arg->getName().str().c_str(), 11, 53)));
            }
            else if (arg->getType()->isFP128Ty())
            {
                variables.insert(make_pair(arg->getName().str(), scx.fpa_const(arg->getName().str().c_str(), 15, 113)));
            }
            else
            {
                std::string type_str;
                llvm::raw_string_ostream rso(type_str);
                arg->print(rso);
                throw UnsupportedTypeException("unsupported LLVM variable type", rso.str());
            }
        }
    }

    //For fp to bv bitcast, create a new variable and constraint it equal at the top level
    expr LLVMFunction::AddBCVariable(std::unique_ptr<LLVMNode> contents)
    {
        std::string name = "_slot_smtbc_" + std::to_string(LLVMFunction::varCounter) + "_";
        expr var = scx.bv_const(name.c_str(), contents->Width());
        variables.insert(make_pair(name, var));
        expr added = (var.mk_from_ieee_bv(contents->SMTSort()) == contents->ToSMT());
        AddConstraint(added);
        LLVMFunction::varCounter++;
        return var;
    }

    void LLVMFunction::AddConstraint(expr constraint)
    {
        extraVariables = hasExtraConstraints ? (extraVariables && constraint) : constraint;
        hasExtraConstraints = true;
    }

    expr LLVMFunction::ToSMT()
    {
        ReturnInst* ret = FindSingleReturn(contents);
        expr fromChildren = LLVMNode::MakeLLVMNode(shiftToMultiply, scx, *this, ret->getOperand(0))->ToSMT();
        return hasExtraConstraints ? (extraVariables && fromChildren) : fromChildren;
    }

    std::vector<expr> LLVMFunction::ToSMTQueries(PathExplorationStrategy strategy, size_t maxPaths,
                                               PathOptimizationStats* pathOptimization)
    {
        ReturnInst* ret = FindSingleReturn(contents);
        std::deque<PathState> worklist = {PathState{std::map<const Value *, const Value *>(), scx.bool_val(true)}};
        std::vector<expr> queries;

        auto makeQuery = [&](const PathState& state) {
            if (pathOptimization && !state.phiSelections.empty())
            {
                expr body = OptimizePathBody(contents, dominators, ret->getOperand(0), state,
                                             shiftToMultiply, scx, *pathOptimization);
                // The body is specialized to the selected operands. Its domain
                // restriction must survive even if the body becomes constant.
                return (state.condition && body).simplify();
            }
            LLVMFunction evaluator(shiftToMultiply, scx, contents);
            evaluator.phiSelections = state.phiSelections;
            expr body = evaluator.ToSMT();
            return (state.condition && body).simplify();
        };

        auto splitState = [&](const PathState& state, std::vector<PathState>& out) {
            std::set<const Value *> visited;
            PHINode* phi = FindNextLoweredPhi(ret->getOperand(0), dominators, state.phiSelections, visited);
            if (phi == nullptr)
            {
                return false;
            }

            LoweredPhiInfo info;
            if (!GetLoweredPhiInfo(phi, info, dominators))
            {
                return false;
            }

            expr condition = EvaluateWithSelections(info.branch->getCondition(), shiftToMultiply, scx, contents, state.phiSelections);

            PathState trueState = state;
            trueState.condition = trueState.condition && condition;
            trueState.phiSelections[phi] = info.trueValue;
            out.push_back(trueState);

            PathState falseState = state;
            falseState.condition = falseState.condition && !condition;
            falseState.phiSelections[phi] = info.falseValue;
            out.push_back(falseState);

            return true;
        };

        while (!worklist.empty())
        {
            PathState state = strategy == PathExplorationStrategy::DFS ? worklist.back() : worklist.front();
            if (strategy == PathExplorationStrategy::DFS)
            {
                worklist.pop_back();
            }
            else
            {
                worklist.pop_front();
            }

            std::vector<PathState> children;
            // Splitting adds 2 children: check that total live states stay within maxPaths.
            // After the pop, worklist.size() is the remaining count. Splitting would make it
            // worklist.size()+2, so total expected outputs would be queries.size()+worklist.size()+2.
            bool withinLimit = (maxPaths == 0) || (queries.size() + worklist.size() + 2 <= maxPaths);
            if (!withinLimit || !splitState(state, children))
            {
                queries.push_back(makeQuery(state));
                continue;
            }

            if (strategy == PathExplorationStrategy::DFS)
            {
                for (auto it = children.rbegin(); it != children.rend(); ++it)
                {
                    worklist.push_back(*it);
                }
            }
            else
            {
                for (const PathState& child : children)
                {
                    worklist.push_back(child);
                }
            }
        }

        return queries;
    }
}
