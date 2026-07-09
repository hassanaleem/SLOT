# Where SLOT's semantics break: a pass-by-pass proof

This document identifies the pipeline phase at which SLOT's SMT-preserving
round trip (`SMT2 → LLVM IR → passes → SMT query`) stops being semantics
preserving. The symptom is that, with the loop passes enabled, an input whose
original query is **SAT** produces a modified query that is **UNSAT**.

The analysis is by inspection only (no runs). It complements
[proofs.md](proofs.md), which proves the unmerge + path-splitting backend is
satisfiability preserving **under** hypotheses H4 (single return) and H5
(acyclic / no loops / no φ-cycles). The loop passes violate exactly those
hypotheses, which is why they fall outside the existing theorem.

Pass order audited (the two `LOOP_OPT` blocks in
[main.cpp](../src/main.cpp) are currently commented out; they are treated here
as **enabled**, since those are the passes under which semantics break):

1. `LoopRolling` (RoLAG) with `loop-rolling-always` forced `true` (profitability skipped) — [main.cpp:370-410](../src/main.cpp#L370)
2. `IndVarSimplify` (commented even within the block) — [main.cpp:400](../src/main.cpp#L400)
3. Standard scalar passes: `InstCombine`, `AggressiveInstCombine`, `EarlyCSE`, `Reassociate`, `SCCP`, `DCE`, `ADCE`, `InstSimplify`, `GVN`, `InstCombine`, `AggressiveInstCombine` — [main.cpp:411-533](../src/main.cpp#L411)
4. Second `LOOP_OPT` block: `LoopUnroll` (thresholds/counts forced huge), `SimplifyCFG`, `EarlyCSE`, `InstCombine`, `DCE`, `SROA` — [main.cpp:535-614](../src/main.cpp#L535)
5. `unmerge` / lower-select — [main.cpp:616-626](../src/main.cpp#L616)

RoLAG source paths below are absolute because they live outside this repo:
`~/Desktop/RoLAG/cgo22-rolag-artifact/loop-rolling/llvm/lib/Transforms/Scalar/LoopRolling.cpp`.

---

## Setup: the pipeline invariant

SLOT's frontend (`SMTFormula::ToLLVM`) emits a **single-basic-block, acyclic,
memory-free, straight-line SSA** function with exactly one `ret`, and the
backend **requires** that shape:

- **Single return.** `FindSingleReturn` throws `UnsupportedLLVMOpException` on
  zero or multiple returns — [LLVMFunction.cpp:30-51](../src/LLVMFunction.cpp#L30). (`proofs.md` H4.)
- **Only select-shaped 2-input phis.** `LowerSelectLikePHI` throws unless the phi
  has exactly 2 incoming values ([LLVMNode.cpp:65-68](../src/LLVMNode.cpp#L65))
  whose two predecessor blocks share a *single* common predecessor ending in a
  *conditional* branch ([LLVMNode.cpp:70-83](../src/LLVMNode.cpp#L70)) whose
  successors match the incoming blocks ([LLVMNode.cpp:92-106](../src/LLVMNode.cpp#L92)).
  An induction-variable phi, a reduction/recurrence accumulator phi, or a
  loop-header phi does not match this shape and throws. (`proofs.md` H5.)
- **No memory / control opcodes.** The instruction dispatch
  `LLVMExpression::ToSMT` ([LLVMNode.cpp:609-791](../src/LLVMNode.cpp#L609)) is a
  closed `switch` over arithmetic/cast/compare/select/phi. It has **no** case for
  `Alloca`, `Load`, `Store`, `GetElementPtr`, or `Br`; all fall to `default` →
  `throw UnsupportedLLVMOpException` ([LLVMNode.cpp:787-788](../src/LLVMNode.cpp#L787)).
  A `GlobalVariable` is an LLVM `Constant`, routed to `LLVMConstant::ToSMT`
  ([LLVMNode.cpp:230-249](../src/LLVMNode.cpp#L230)), which calls `SMTSort()` on
  the global's array/pointer type and throws `UnsupportedTypeException`
  ([LLVMNode.cpp:182-188](../src/LLVMNode.cpp#L182)).

**Consequence.** When the backend meets a back-edge or a non-select phi, it does
not mistranslate silently — it **throws**. When it meets `alloca/load/store/gep`,
it **throws**. The only way the backend can silently emit a *wrong* query is if a
later pass collapses a rolled loop back into plain, backend-legal arithmetic over
the **wrong** operands (see mechanisms 1 and 5).

---

## Per-pass correctness

### Standard scalar passes — semantics-preserving on straight-line input (brief)

`InstCombine`, `AggressiveInstCombine`, `EarlyCSE`, `Reassociate`, `SCCP`, `DCE`,
`ADCE`, `InstSimplify`, `GVN` ([main.cpp:411-533](../src/main.cpp#L411)) are stock
LLVM passes. On a single acyclic BB with no memory and no UB (the frontend emits
poison-free code; the backend even treats `freeze` as identity,
[LLVMNode.cpp:728-730](../src/LLVMNode.cpp#L728)), each only re-expresses the same
SSA value. They neither introduce loops nor non-select phis, so they preserve the
H4/H5 invariant and the denoted function. These are not where SAT flips.

### Unmerge / lower-select — semantics-preserving (already proved)

`RunLowerSelectPass` ([lower-select.cpp:393](../src/Unmerging-llvm/lower-select.cpp#L393))
replaces each scalar-`i1` `select` with a diamond + 2-input phi
([lower-select.cpp:324-380](../src/Unmerging-llvm/lower-select.cpp#L324)) of exactly
the shape the backend accepts. [proofs.md](proofs.md) proves this is
satisfiability preserving (Lemma 1′, Lemma 2, Main Theorem). It runs last and only
produces select-shaped phis, keeping the invariant. Not the break.

### LoopRolling (RoLAG) — the pass that breaks semantics (detailed)

LoopRolling is the first enabled pass ([main.cpp:370-410](../src/main.cpp#L370))
with `loop-rolling-always` forced `true` so profitability is skipped
([main.cpp:387-394](../src/main.cpp#L387); the flag gates the emit at
`LoopRolling.cpp:2803`). It rewrites a straight-line run of similar instructions
into a **counted loop** with an `i8` induction variable
(`LoopRolling.cpp:2719-2721`), step `+1` (`:2759`), exit
`icmp ne (indvar+1), G.getWidth()` (`:2767`), reconstructing per-iteration
differing operands via constant global arrays + gep/load, preheader alloca +
stores + gep/load, or arithmetic-sequence nodes. Each is analysed below.

---

## The break: pass = LoopRolling, five distinct mechanisms

The earliest phase at which semantics break is **LoopRolling** (phase 1). Every
mechanism originates there; the later `LoopUnroll → SimplifyCFG → EarlyCSE →
InstCombine → DCE → SROA` block ([main.cpp:535-614](../src/main.cpp#L535)) merely
decides whether the damage becomes a *silent wrong answer* (loop fully eliminated
over wrong data) or an *exception* (loop survives, backend throws).

### The round-trip question

If LoopRolling were value-preserving, `roll → full-unroll → SROA → InstCombine`
would restore the original straight-line function and the whole loop phase would
be a no-op modulo a correct round trip. It is **not** value-preserving. Two
failure modes result:

- **Loop fully unrolled** (width ≤ 255, unroll succeeds): SROA promotes the
  alloca/global loads back to scalars and the function is backend-legal again —
  but now over whatever operands LoopRolling substituted. If those are wrong
  (mechanism 1) or reordered (mechanism 5), the restored function denotes a
  different SMT term, and its query can be **UNSAT** where the original was SAT.
  This is the silent, dangerous case.
- **Loop not fully eliminated** (width > 255 wrapping the `i8` bound — mechanism 2;
  a residual induction/recurrence phi; or SROA failing to promote a
  counter-indexed gep): the backend meets a back-edge, an `i8` IV phi, or a
  surviving `load`/`gep`/`alloca` and **throws** `UnsupportedLLVMOpException`.
  Not "UNSAT" per se, but equally a wrong pipeline result vs. the original SAT.

### Mechanism 1 (primary): constant-array reuse ignores the actual constants

`generateMismatchingCode`, constant branch (`LoopRolling.cpp:2084-2101`):

```cpp
2093:  for (unsigned i = 0; i<Consts.size(); i++) {
2094:    if (C->getAggregateElement(i)!=Consts[i]) continue;
2095:  }
2096:  //Found Array
2097:  errs() << "Found Array: "; GA->dump();
2098:  IndexedValue = Pair.second;
2099:  break;
```

The loop body at `:2093-2095` is a **no-op**: `continue` only advances `i`;
nothing tests the result of the element comparison. So after the loop, for **any**
previously created private global of the same `ArrayType` and element count
(`:2089-2092`), it unconditionally does `IndexedValue = Pair.second` (`:2098`) and
reuses that array's load — **substituting the wrong constants**. The intended
guard (skip the candidate unless *all* elements match) is missing; correct code
would be `if (C->getAggregateElement(i)!=Consts[i]) { match=false; break; }`
guarding the reuse. `allConstant` excludes globals/constexprs (`:64-71`), so this
fires precisely on ordinary integer/FP constant vectors — exactly what SMT
bit-vector inputs produce.

**Before/after IR sketch (SAT → UNSAT).** For input variable `x`, suppose a prior
rolled group already created `@g0 = private constant [2 x i32] [i32 3, i32 4]`
with `GlobalLoad[@g0]` recorded, and the current group needs constants
`{10, 20}` (`add x,10` / `add x,20`) with a query `icmp eq (add x,20), 24` that is
SAT at `x = 4`. Since `[2 x i32]` matches `@g0`'s type and length, the buggy scan
"finds" `@g0` and reuses its load of `[3,4]`. After unroll+SROA the restored code
computes `add x,3` / `add x,4`, so the constraint becomes `icmp eq (add x,4), 24`,
requiring `x = 20`. If the query also bounds `x` (e.g. `x <u 8`), the original
witness `x = 4` is destroyed and no model remains → **UNSAT**. The satisfying
assignment was tied to the constant `20`; replacing it with `4` removes every
model.

### Mechanism 2: `i8` induction variable / bound overflow for width > 255

The IV type is hard-coded `i8` (`LoopRolling.cpp:2719`), the exit bound is
`ConstantInt::get(i8, G.getWidth())` (`:2767`) with `getWidth()` a `size_t`
(`:818-826`), and array lengths are `ConstantInt::get(i8, N->size())`
(`:2030`, `:2134`). For rolled width `W`:

- `W = 256` → `get(i8, 256)` truncates to `0`; the exit test `(indvar+1) != 0`
  iterates `0..255` then wraps to `0` — it does not match the 256 original terms.
- `W ∈ (256, 511]` → truncated bound in `1..255`, so the loop runs a different,
  smaller iteration count than the original term count.

Long rolled sequences from SMT are plausible (wide `bvand`/`concat`/reduction
chains, big nested booleans). When the trip count no longer statically equals the
original term count, `LoopUnroll` cannot fully peel the loop; the residual
back-edge + `i8` phi reach the backend and **throw**. Even if fully unrolled, the
wrong iteration count materialises a different function → possible SAT→UNSAT.

### Mechanism 3: memory-op reconstruction that survives SROA → backend exception

Non-constant mismatch reconstruction (`LoopRolling.cpp:2124-2154`: preheader
`alloca` + per-index `store`, in-loop `gep IndVar` + `load`) and
`generateExtract` (`:2026-2046`) introduce `alloca/store/gep/load` indexed by the
loop counter. SROA/mem2reg can only promote these if the loop is first fully
unrolled to constant indices. Whenever unrolling is incomplete (mechanism 2, or an
unroller heuristic miss), a `gep`/`load`/`alloca` reaches
`LLVMExpression::ToSMT` and throws `UnsupportedLLVMOpException`
([LLVMNode.cpp:787](../src/LLVMNode.cpp#L787)).

### Mechanism 4: reduction/recurrence phis are not select-shaped

REDUCTION builds an accumulator `phi` with incoming `(NewI from Header,
StartValue from PreHeader)` (`LoopRolling.cpp:2451-2462`) and RECURRENCE builds a
loop-carried `phi` (`:2400-2409`). These are induction/loop-carried phis, not the
2-input shared-conditional-predecessor shape the backend accepts. If any survives
unrolling, `LowerSelectLikePHI` throws
([LLVMNode.cpp:70-83](../src/LLVMNode.cpp#L70)).

### Mechanism 5: reduction operand reordering breaks FP

`isValidOperation` returns `true` for `FAdd`/`FMul` (and `Add/Mul/Or/And/Xor`)
with the associativity/commutativity check commented out:

```cpp
603:  static bool isValidOperation(BinaryOperator *BO) {
604:    switch(BO->getOpcode()) {
605:    case Instruction::Add:
606:    case Instruction::FAdd:
607:    case Instruction::Mul:
608:    case Instruction::FMul:
...
612:      //return (BO->isAssociative() && BO->isCommutative());
613:      return true;
```

(`LoopRolling.cpp:603-613`.) `collectValues` flattens the operand chain
(`:619-629`) and `buildReduction` calls `ReorderOperands(Vs, BB)` (`:1221`), which
**sorts** operands by block position (or constant value) (`:1176-1178`), so
evaluation order is not preserved.

The backend models `FAdd/FMul` as genuine IEEE FP with a fixed rounding mode
(`set_rounding_mode(RNE)`, [LLVMFunction.cpp:167](../src/LLVMFunction.cpp#L167);
`FAdd → +`, `FMul → *` at [LLVMNode.cpp:770-777](../src/LLVMNode.cpp#L770), on
`fpa` sorts). FP `+`/`*` are non-associative, so `((a ⊕ b) ⊕ c)` and a reordered
`((b ⊕ c) ⊕ a)` are different rounded values. When the reduction is unrolled back
to straight-line FP arithmetic it computes the reordered result, and a query
`fp.eq (reduction) K` that was SAT for a witness giving the original rounded sum
can become UNSAT — a SAT→UNSAT flip with no exception. Additionally, with no PHI
start, `getStartValue()` injects a neutral element (`0.0`/`1.0`, `:565`,
`:589-597`); `x + 0.0` is not identity in FP when `x = -0.0` (yields `+0.0`),
another latent value change. Integer `Add/Mul/Or/And/Xor` reordering is value-safe,
and `Sub` is excluded (`:614`), so non-commutative integer subtraction is not
mis-rolled here.

---

## Conclusion

The semantics break at the **first loop-phase pass, LoopRolling (RoLAG), run in
forced `loop-rolling-always` mode** ([main.cpp:387-394](../src/main.cpp#L387)). It
converts SLOT's straight-line, single-BB, memory-free, single-return input — the
exact invariant the backend and the [proofs.md](proofs.md) theorem depend on
(H4/H5) — into a counted `i8`-induction loop with memory-materialised operands,
**non-faithfully** in five confirmed ways: (1) the no-op comparison loop at
`LoopRolling.cpp:2093-2095` reuses an existing constant global array *ignoring its
actual values*, substituting wrong constants; (2) the `i8` counter and bound
(`:2719`, `:2767`) overflow/truncate for widths > 255; (3) memory ops that survive
incomplete unrolling; (4) reduction/recurrence phis that are not select-shaped;
and (5) FP reduction operand reordering (`:1176`) enabled by the disabled
associativity check (`:612-613`). The `roll → full-unroll → SROA` round trip is
therefore **not** the identity: when the loop fully unrolls it silently restores a
straight-line function over the wrong constants / reordered FP (SAT→UNSAT with no
error); when it does not, surviving loop/phi/memory ops make the backend throw
`UnsupportedLLVMOpException`. The standard scalar passes and the unmerge pass are
value-preserving on straight-line input and are not implicated.

**The break is LoopRolling, and mechanism (1) — the constant-array reuse bug — is
the cleanest reproducible SAT-to-UNSAT flip.**
