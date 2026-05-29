#include "LLVMNode.h"
#include "SLOTExceptions.h"
#include "llvm/IR/Instructions.h"
#include <deque>
#include <regex>
#include <set>

#ifndef LLMAPPING
#define LLMAPPING std::map<std::string, Value*>
#endif

namespace SLOT
{
    namespace
    {
        struct LoweredPhiInfo
        {
            PHINode* phi;
            BranchInst* branch;
            Value* trueValue;
            Value* falseValue;
        };

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

        bool GetLoweredPhiInfo(PHINode* phi, LoweredPhiInfo& info)
        {
            if (phi->getNumIncomingValues() != 2)
            {
                return false;
            }

            BasicBlock* firstPred = phi->getIncomingBlock(0);
            BasicBlock* secondPred = phi->getIncomingBlock(1);
            BasicBlock* commonPred = firstPred->getSinglePredecessor();

            if (commonPred == nullptr || commonPred != secondPred->getSinglePredecessor())
            {
                return false;
            }

            auto* branch = dyn_cast<BranchInst>(commonPred->getTerminator());
            if (branch == nullptr || !branch->isConditional())
            {
                return false;
            }

            info.phi = phi;
            info.branch = branch;

            if (branch->getSuccessor(0) == firstPred && branch->getSuccessor(1) == secondPred)
            {
                info.trueValue = phi->getIncomingValue(0);
                info.falseValue = phi->getIncomingValue(1);
                return true;
            }

            if (branch->getSuccessor(0) == secondPred && branch->getSuccessor(1) == firstPred)
            {
                info.trueValue = phi->getIncomingValue(1);
                info.falseValue = phi->getIncomingValue(0);
                return true;
            }

            return false;
        }

        expr EvaluateWithSelections(Value* value, bool shiftToMultiply, context& scx, Function* contents,
                                    const std::map<const Value *, const Value *>& phiSelections)
        {
            LLVMFunction evaluator(shiftToMultiply, scx, contents);
            evaluator.phiSelections = phiSelections;
            expr result = LLVMNode::MakeLLVMNode(shiftToMultiply, scx, evaluator, value)->ToSMT();
            return evaluator.hasExtraConstraints ? (evaluator.extraVariables && result) : result;
        }

        PHINode* FindNextLoweredPhi(Value* value, bool shiftToMultiply, context& scx, Function* contents,
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
                    return FindNextLoweredPhi(const_cast<Value*>(selected->second), shiftToMultiply, scx, contents, phiSelections, visited);
                }

                LoweredPhiInfo info;
                if (GetLoweredPhiInfo(phi, info))
                {
                    if (auto* nested = FindNextLoweredPhi(info.branch->getCondition(), shiftToMultiply, scx, contents, phiSelections, visited))
                    {
                        return nested;
                    }
                    if (auto* nested = FindNextLoweredPhi(info.trueValue, shiftToMultiply, scx, contents, phiSelections, visited))
                    {
                        return nested;
                    }
                    if (auto* nested = FindNextLoweredPhi(info.falseValue, shiftToMultiply, scx, contents, phiSelections, visited))
                    {
                        return nested;
                    }
                    return phi;
                }

                for (unsigned i = 0; i < phi->getNumIncomingValues(); ++i)
                {
                    if (auto* nested = FindNextLoweredPhi(phi->getIncomingValue(i), shiftToMultiply, scx, contents, phiSelections, visited))
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
                    if (auto* nested = FindNextLoweredPhi(operand, shiftToMultiply, scx, contents, phiSelections, visited))
                    {
                        return nested;
                    }
                }
            }

            return nullptr;
        }
    }

    LLVMFunction::LLVMFunction(bool t_shiftToMultiply, context& t_scx, Function* t_contents) : shiftToMultiply(t_shiftToMultiply), scx(t_scx), contents(t_contents), extraVariables(t_scx.bool_val(true)), hasExtraConstraints(false)
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

    std::vector<expr> LLVMFunction::ToSMTQueries(PathExplorationStrategy strategy, size_t maxPaths)
    {
        ReturnInst* ret = FindSingleReturn(contents);
        std::deque<PathState> worklist = {PathState{std::map<const Value *, const Value *>(), scx.bool_val(true)}};
        std::vector<expr> queries;

        auto makeQuery = [&](const PathState& state) {
            LLVMFunction evaluator(shiftToMultiply, scx, contents);
            evaluator.phiSelections = state.phiSelections;
            expr body = evaluator.ToSMT();
            return (state.condition && body).simplify();
        };

        auto splitState = [&](const PathState& state, std::vector<PathState>& out) {
            std::set<const Value *> visited;
            PHINode* phi = FindNextLoweredPhi(ret->getOperand(0), shiftToMultiply, scx, contents, state.phiSelections, visited);
            if (phi == nullptr)
            {
                return false;
            }

            LoweredPhiInfo info;
            if (!GetLoweredPhiInfo(phi, info))
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
