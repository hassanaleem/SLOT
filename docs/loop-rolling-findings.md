# Loop-rolling semantics debugging — findings log

Status as of **2026-07-03**. Companion to
[loop-rolling-semantics-break.md](loop-rolling-semantics-break.md) (the
pass-by-pass proof) and [proofs.md](proofs.md) (unmerge/path-splitting theorem).

> **RESOLVED — root cause found (see §Root cause, end of file):** RoLAG's
> `match()` ignores the `icmp` predicate, so `icmp eq` and `icmp ult` lanes are
> merged into one MATCH node and codegen stamps lane 0's predicate onto every
> lane (`Sx < 10` becomes `Sx == 10`). Every benchmark's roll is corrupted;
> the "working" ones only pass because the corrupted formula happens to stay
> satisfiable (their sat models are spurious).

## Problem statement

With the `LOOP_OPT` blocks enabled in [main.cpp](../src/main.cpp) (RoLAG
`LoopRolling` forced via `loop-rolling-always`, then scalar passes, then
`LoopUnroll`→`SimplifyCFG`→`EarlyCSE`→`InstCombine`→`DCE`→`SROA`, then
unmerge), benchmarks that are known **SAT** produce all-UNSAT query sets.
Ground truth: every benchmark in `slot-benchmark-sat-with-select/QF_BV/mcm/`
was pre-measured SAT (re-confirmed for 18 directly with z3).

The intended design is sound *if* the round trip is faithful: roll → fully
unroll → SROA must restore a single-BB, memory-free, value-identical function
(the invariant the backend and proofs.md H4/H5 require).

## Fixes implemented (all in RoLAG `LoopRolling.cpp`)

File: `~/Desktop/RoLAG/cgo22-rolag-artifact/loop-rolling/llvm/lib/Transforms/Scalar/LoopRolling.cpp`.
Rebuilt into `libLLVMScalarOpts.a` and relinked `src/slot` (and RoLAG `opt`)
on 2026-07-03 ~15:29.

| # | Bug | Fix | Where |
|---|-----|-----|-------|
| 1 | Constant-array reuse scan had a no-op body (`if (mismatch) continue;` inside the element loop) — reused ANY same-shaped global, substituting wrong constants | `AllMatch` flag; reuse only when every element matches | `generateMismatchingCode`, ~2101 |
| 2 | Reduction rolling allowed non-associative FP (`fadd`/`fmul`) and `ReorderOperands` sorts operands → different rounded value | `isValidOperation` now requires `isAssociative() && isCommutative()` | ~618 |
| 3 | `i8` induction variable and array sizes truncate for width > 255 | widened to `i64` (4 sites) | 2038/2128/2157/2747 |
| 4 | **Reduction off-by-one**: chain of n binops has n+1 leaves; loop runs `Root->size()` = n iterations with a neutral-start accumulator → **last leaf silently dropped** (fires for every straight-line reduction, since PHI start is always null in SLOT IR) | accumulator seeded with one leaf operand (prefer Constant/Argument for dominance), `Vs` shrunk to n; shape guards bail otherwise; `ReductionNode` start param `PHINode*`→`Value*` | `buildReduction`, ~1236 |
| 5 | `And` neutral element was `1`; identity of AND is all-ones (`x & 1` clears bits above bit 0 for widths > i1) | `Constant::getAllOnesValue` in both spots | `getNeutralValue` ~595, `buildBinOpSequenceNode` ~1554 |
| 6 | `verifyFunction` failure only printed "Broken Function!!" and **continued** with invalid IR | now `report_fatal_error` (fails loudly) | `generate()`, ~2941 |

Also established (dead code, no fix needed): the ALTSEQ `IsNegatedInt` lambda
compares `V1.eq(V2)` (not the negation), but identical-value vectors are caught
by `IdenticalNode` before ALTSEQ is tried, so "Version 2" codegen is unreachable.

## Empirical results (after all fixes)

Per-benchmark artifacts in `reroll/<id>/`: `<id>.ll` (pre-opt `-lu` IR),
`<id>-chain.ll` (post-opt), `<id>-chain.smt2` (queries), `logs/chain.err`
(LoopRolling stderr), `logs/solver-chain.log` (z3 results). Invocation:
`slot -s <input> -pall -unmerge-chain 5`.

- Benchmarks **05, 12: now work** (SAT found) — fixed by the changes above.
- Benchmarks **14, 18: still fail** (all 32 queries UNSAT).
- **Bisection of 18** (decisive, with the fixed binary):
  - `slot -li reroll/18/18.ll` (no passes) → 1 query → z3 **sat** ✓
  - `slot -li reroll/18/18.ll -loopopt` → z3 **unsat** ✗
  - ⇒ the loop phase alone still flips SAT→UNSAT; scalar passes and unmerge are exonerated (again).
- **Roll profile of 18** (from `chain.err`, fixed binary): exactly one rolled
  loop, root **REDUCTION width 45**, children **BINOP: 922, MISMATCH: 924,
  MATCH: 1**; **no** "Found Array"; **no** "Broken Function". Post-opt IR is
  fully flat (0 allocas/loads/loops; only unmerge's select diamonds) — so the
  round trip flattens completely but computes the **wrong value** silently.

## Conclusion so far

At least one more silent value-changing defect remains in LoopRolling's
codegen, exercised by benchmark 18's (and presumably 14's) roll shape:
a REDUCTION root over ~922 BinOpSequence nodes and ~924 Mismatch nodes.
Since "Found Array" never fires and the IR verifies, the residual bug is in
one of these paths:

1. **BINOP codegen** (`cloneGraph` case `NodeType::BINOP`): `NewI` is a clone
   of `BinOpRef` (lane 0's operator incl. any flags) stamped onto all lanes;
   Left/Right operand-vector alignment per lane, and the commutative
   constant-swap in `buildBinOpSequenceNode` (swaps *some* lanes' operands but
   not others — the Left/Right arrays must stay per-lane consistent with the
   iteration order).
2. **Mismatch-lane neutral padding** in `buildBinOpSequenceNode`: a lane whose
   value is not a `MaxOpcode` binop is rebuilt as `value MaxOp Neutral` —
   correctness depends on which opcodes actually appear in mcm benchmarks
   (adds/subs/shifts/mults).
3. **INTSEQ codegen**: `start + indvar*step` reconstruction and the unsigned
   `IntCast` of the i64 induction variable to the sequence type.
4. **generateExtract / reduction special-case interplay** with the new
   start-operand handling (`Extracted[getBinaryOperator()] = NewI`).
5. **Scheduling/Exit-move** in `generate()` (`SchedulingOrder`, `dependsOn`,
   the move-to-Exit loop) — ordering is value-safe in SSA, but the
   *operand-vector-to-iteration* mapping is not verified.

## How to continue (recipe)

1. Isolate the roll step (no unroll/cleanup) with RoLAG's own opt:
   `~/Desktop/RoLAG/cgo22-rolag-artifact/loop-rolling/build/release/bin/opt
   -enable-new-pm=0 -loop-rolling -loop-rolling-always -S reroll/14/14.ll -o rolled.ll`
   then hand-check `rolled.pre`/`rolled.loop`/`rolled.exit` against the
   original straight-line chain (width×nodes is small enough to eyeball).
2. Differential model check: take z3's model of the no-pass query and
   assert its values onto the `-loopopt` query to see which assertion breaks.
3. Compare `chain.err` node profiles of the working (05, 12) vs failing
   (14, 18) benchmarks — the discriminating node type/codegen path is the bug.
   (Key control: check whether 05/12 actually rolled anything; if their roll
   was trivial/absent, "working" is vacuous.)
4. A background analysis agent was running exactly this classification +
   root-cause when the session ended; its partial work may exist in the
   session scratchpad.

## Fallback options (if the residual bug stays elusive)

- Restrict rolling to node kinds already validated (disable REDUCTION and/or
  BINOP/MISMATCH mismatch-padding paths) — conditions for the faithful round
  trip then hold by construction.
- Checkpoint + translation-validate: clone the function before the loop phase,
  emit SMT for both versions, assert inequivalence UNSAT in CI; fall back to
  the unrolled original when validation fails.

---

## Root cause (RESOLVED 2026-07-03, cross-benchmark analysis)

### Classification (all 12 reroll benchmarks, fixed binary)

Every benchmark rolls **exactly one loop**: root REDUCTION, hundreds of
BINOP/MISMATCH children, and exactly **one MATCH node** — the bug site.
No INTSEQ/ALTSEQ/GEPSEQ/RECURRENCE anywhere; no "Found Array"/"Broken
Function" anywhere.

| bench | result | width | | bench | result | width |
|---|---|---|---|---|---|---|
| 05 | works¹ | 42 | | 26 | works¹ | 42 |
| 113 | works¹ | 6 | | 33 | fails | 29 |
| 12 | works¹ | 10 | | 35 | fails | 37 |
| 14 | fails | 22 | | 37 | fails | 41 |
| 18 | fails | 45 | | 45 | works¹ | 10 |
| 22 | fails | 44 | | 54 | fails | 45 |

¹ **"Works" is coincidental** — see below.

### The defect

**`match()` ignores the `icmp` predicate; MATCH codegen stamps lane 0's
predicate onto all lanes.**

- `LoopRolling.cpp:156-206` — `match(V1,V2)` compares only `getOpcode()`
  (line 164) and operand types. For `icmp` it falls through to
  `default: return true;` (199-200). The precise check
  `I1->isSameOperationAs(I2)` — which compares `CmpInst` predicates — is
  **commented out** at line 163. Hence `icmp eq` and `icmp ult` "match".
- `createNode` (~1726-1745) then builds the single `MatchingNode` from the
  mixed-predicate lane vector.
- `cloneGraph` `case NodeType::MATCH` (~2248-2250):
  `NewI = I->clone()` of **lane 0** becomes the one shared loop instruction —
  lane 0's `icmp eq` replaces every other lane's comparison.

### Concrete effect (benchmark 14, mcm family)

The mcm benchmarks end in an AND-reduction whose leaves mix `icmp eq` lanes
(from or-trees) with 10-24 range guards `icmp ult i10 %Sx, 10`. After rolling:

```llvm
; original lane (reroll/14/14.ll):
%40237 = icmp ult i10 %S1, 10          ; true under the SAT model (S1=0)

; rolled loop body (isolated roll, 14-rolled.ll):
%55581 = load i10, i10* %55580          ; arr2[i] = 10 for the 12 ult lanes
%55582 = icmp eq i10 %55579, %55581     ; 'eq' stamped from lane 0 — was 'ult'
```

`Sx < 10` became `Sx == 10`; the per-lane conjunct is false at exactly the 12
`ult` lanes, the accumulator collapses to 0, ret = 0 → every query UNSAT.

Verified by bisection (`-li 14.ll` no-pass → sat; `-loopopt` → unsat), by an
isolated roll (`opt -enable-new-pm=0 -loop-rolling -loop-rolling-always`), and
by concrete interpretation of both IRs under a z3 model.

### "Working" benchmarks are also broken

Interpretation shows the same divergence in 05 and 12 (original ret=1, rolled
ret=0 under the no-pass model), and — decisive — the model returned by 05's
"sat" query evaluates the **original** `05.ll` to **0**: the sat answer is
spurious and only coincidentally agrees with ground truth. Works vs fails is
merely whether the *corrupted* formula stays satisfiable.

⇒ **All previously "passing" loop-rolled results are unsound.** Re-validate
any sat model against the pre-pass IR/SMT before trusting it.

### Also verified clean during this analysis

- BINOP And-neutral padding (fix #5) is value-correct in the rolled IR.
- Reduction seed/width accounting (fix #4) is consistent (leaves = width+1 in
  all 12 benchmarks).
- Operand/lane alignment of the mismatch arrays is correct.

### The fix (IMPLEMENTED 2026-07-06, fix #7)

Two additions to `match()` (`LoopRolling.cpp`, after the operand-type loop),
keeping the deliberate `MatchAlignment` load/store relaxation:

1. Poison/FMF flags must agree across lanes (they are cloned from lane 0):
   ```cpp
   if (I1->getRawSubclassOptionalData()!=I2->getRawSubclassOptionalData()) return false;
   ```
2. Explicit `ICmp`/`FCmp` case before `default: return true;`:
   ```cpp
   case Instruction::ICmp:
   case Instruction::FCmp:
     return cast<CmpInst>(I1)->getPredicate()==cast<CmpInst>(I2)->getPredicate();
   ```

Rebuilt `LLVMScalarOpts` + relinked `slot` on 2026-07-06.

### Verification (2026-07-06, fixed binary)

Benchmark 14 (previously all-32-queries UNSAT): full pipeline
(`slot -s ... -pall -unmerge-chain 5`) → query 16 **sat** in ~1 s. The rolled
IR retains the 36 `icmp ult` guards (previously stamped to `eq`). **Model
validated as genuine**: query 16's z3 model, asserted onto the *original*
`14.smt2`, yields **sat** — the round trip is now faithful for this benchmark,
not merely "happens to be satisfiable".

### Final results (2026-07-06, full re-run of all 12 benchmarks, fixed binary)

**All 12 benchmarks now SAT** through the full pipeline
(`slot -s ... -pall -unmerge-chain 5`), and every one **actually rolled a
loop**: each log ends with `Done Loop Roller: 1/1` (one attempt, one committed
roll), rooted at the final AND-REDUCTION. From `reroll/<id>/logs/chain.err`:

| id | roll width | MATCH | MISMATCH | verdict |
|----|-----------|-------|----------|---------|
| 05 | 42 | 0 | 774 | SAT (query 22) |
| 113 | 6 | 0 | 1852 | SAT (query 16) |
| 12 | 10 | 0 | 633 | SAT (query 12) |
| 14 | 22 | 0 | 771 | SAT (query 16) — model validated against original |
| 18 | 45 | 0 | 922 | SAT (query 15) |
| 22 | 44 | 0 | 923 | SAT (query 16) |
| 26 | 42 | 0 | 774 | SAT (query 28) |
| 33 | 29 | 0 | 774 | SAT (query 12) |
| 35 | 37 | 0 | 922 | SAT (query 16) |
| 37 | 41 | 0 | 923 | SAT (query 15) |
| 45 | 10 | 0 | 766 | SAT (query 12) |
| 54 | 45 | 0 | 922 | SAT (query 16) |

Reading the profile: with the strict `match()`, the previously-corrupting
mixed-predicate MATCH node is gone everywhere (**MATCH: 0**, was 1); the
eq/ult guard lanes now land in MISMATCH nodes, whose per-lane constant-table
codegen is value-correct. Every roll is reported "Reduction **Unprofitable**"
by RoLAG's size model (rolled form is far larger — hundreds of MISMATCH
constant tables), but `-loop-rolling-always` commits it anyway, which is the
intended SLOT design (roll → optimize → fully unroll → SROA back to one BB).
Note for the research goal: the node profile is ~50 % MISMATCH children,
i.e. almost nothing matches structurally across lanes in these mcm
benchmarks — the loops are mostly constant-table lookups.

## Do our own fixes preserve semantics?

Two independent verifications, one per direction of doubt.

### Code-level argument, fix by fix

| # | Fix | Why it cannot break semantics |
|---|-----|-------------------------------|
| 1 | Constant-array reuse guard | Strictly *narrows* the reuse condition: an existing global is reused only when **every** element matches (before: any same-shaped global). On mismatch a fresh, correct array is created — same values either way. |
| 2 | Reduction requires `isAssociative() && isCommutative()` | Pure **rejection**: non-associative ops simply don't roll. No transformation ⇒ trivially preserving. |
| 3 | `i8` → `i64` induction variable | Type widening applied consistently at all 4 sites (indvar, bound, trip count, index). Widening a counter that only counts 0…width−1 cannot change any computed value; it removes overflow at width > 255. |
| 4 | Reduction off-by-one (leaf-seeded accumulator) | The reduction is a fold of an **associative + commutative** op (guaranteed by fix 2) over the n+1 leaf multiset. Seeding the accumulator with one leaf and folding the remaining n computes the same value as the original chain, by associativity/commutativity — any leaf works as seed. Shape guards (`Vs.size() != BOs.size()+1` etc.) *reject* anything else. Dominance of the seed (preheader placement) is enforced by the verifier (fix 6). |
| 5 | `And` neutral = all-ones | `x & ~0 = x` is the definition of the AND identity; the old value `1` was simply the wrong constant (`x & 1 ≠ x` for widths > i1). Replacing a wrong constant with the mathematical identity is value-correct wherever a neutral element is required. |
| 6 | `verifyFunction` → `report_fatal_error` | Diagnostic only: no generated code changes. Silent miscompilation becomes a hard abort — defense in depth for every other fix. |
| 7 | Strict `match()` (flags + cmp predicate) | Pure **rejection**: a stricter equivalence can only *shrink* the set of lanes that merge into a MATCH node. Rejected lanes fall to MISMATCH (per-lane constant tables, value-faithful) or the roll is abandoned. No new rewrite is introduced. |

Fixes 2, 6, 7 are restrictions/diagnostics — semantics-preserving by
construction. Fixes 1, 3 are consistency repairs with no value change.
Fixes 4, 5 change generated values and rest on the identity-element /
associativity arguments above — these two are exactly what the empirical
check below targets.

### Empirical translation validation (z3, all inputs)

For each benchmark, emit the backend SMT formula of the *same* IR
(`reroll/<id>/<id>.ll`) twice — with **no passes** and **after the pass
pipeline** — and ask z3 for a counterexample to equivalence:

```
slot -li reroll/<id>/<id>.ll -o orig.smt2                 # no passes
slot -li reroll/<id>/<id>.ll -loopopt -o loopopt.smt2      # loop phase only
slot -li reroll/<id>/<id>.ll -pall -nounmerge -o pall.smt2 # full pipeline, no unmerge
# combine: shared decls + (assert (distinct F_orig F_variant)) + (check-sat)
```

`unsat` means the two formulas agree on **every** assignment to all input
bitvectors — a universal proof, far stronger than validating one sat model.
(Helper: scratchpad `equiv/mk_equiv.py` + `run_equiv_all.sh`.)

Results: see table below.
