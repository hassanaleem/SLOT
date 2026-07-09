# Satisfiability Equivalence of Select-Unmerging with Path Splitting

This document formalizes the correctness of SLOT's *path-splitting* backend: the
claim that unmerging `select` instructions and emitting `2^x` per-path SMT queries
is **satisfiability-equivalent** to the original SMT query, so that the original
formula is satisfiable iff *some* single path query is satisfiable.

It is written as an extension of the already-established single-query result
(round-tripping SMT → IR → optimize → SMT with one query). That result is taken
as a hypothesis (H1) and is not re-proved here.

The statements below have been cross-checked against the implementation; relevant
code anchors are cited as `file:line`.

---

## 0. Hypotheses

Throughout, `F(X)` is the input quantifier-free SMT formula with input variables
`X = (x_1, …, x_n)`.

- **H1 (established single-query round trip).** Let `T` be the SMT→IR frontend and
  `O` any sequence of semantics-preserving IR passes that do **not** lower selects.
  The single SMT query produced from `T;O` — in which every `select` is encoded as
  a strict `ite` — is equisatisfiable with `F`, and a model of either yields a model
  of the other over the base variables `Y` (see H2). *This is the existing result.*

- **H2 (faithful total encoding).** The backend translation `⟦·⟧` is homomorphic on
  every **supported** non-`phi` IR operator into quantifier-free bit-vector / floating
  point SMT. These theories are **total** and their predicates **two-valued**
  (`bvudiv`/`bvurem` by zero are defined; FP `NaN` is an ordinary value; comparisons
  return a definite Boolean). A few operators introduce **auxiliary** fresh SMT
  variables together with a **functional** defining constraint that is conjoined into
  the query — concretely the fp↔bv reinterpretation variable
  ([LLVMFunction.cpp:210-219](../src/LLVMFunction.cpp#L210-L219), via
  `mk_from_ieee_bv`, [LLVMNode.cpp:698](../src/LLVMNode.cpp#L698)); collect these into
  the variable set `Aux` and the conjunction `AuxDefs`. There is no poison/undef
  notion at the SMT level. Write `Y = X ∪ Aux`; every translated term denotes a total
  function of `Y`.
  *Scope:* unsupported opcodes throw `UnsupportedLLVMOpException`
  ([LLVMNode.cpp:787-788](../src/LLVMNode.cpp#L787-L788), and similar) and are outside
  the theorem; H2 ranges over the supported subset only.

- **H3 (shape of lowered selects).** Every lowered `select` has a scalar `i1` flag
  (non-`i1`, including vector-of-`i1`, is rejected by abort,
  [lower-select.cpp:57-62](../src/Unmerging-llvm/lower-select.cpp#L57-L62)) and is
  replaced by a **2-input phi** whose incoming values are the select's true operand
  (`getOperand(1)`) and false operand (`getOperand(2)`), fed from the two arms of a
  conditional branch on the flag with a shared predecessor
  ([lower-select.cpp:339-380](../src/Unmerging-llvm/lower-select.cpp#L339-L380)). The
  encoder independently rejects any phi that is not exactly 2-input with a shared
  conditional-branch predecessor ([LLVMNode.cpp:65-106](../src/LLVMNode.cpp#L65-L106)).
  *Note:* this encoder check is generic over all phis the backend visits, not only
  those produced by select-lowering; any equally-shaped control-flow phi is encoded
  the same way, which is harmless for the theorem.

- **H4 (single return).** The function has exactly one return instruction; otherwise
  `FindSingleReturn` throws ([LLVMFunction.cpp:30-51](../src/LLVMFunction.cpp#L30-L51)).
  This is what makes "the returned Boolean `R`" well-defined.

- **H5 (acyclicity).** The use-def graph among lowered phis, their guards, and their
  value operands is acyclic (straight-line code; no loops or φ-cycles). Hence all
  `ite`-nodes admit a topological order.
  *Code note:* acyclicity is **assumed**, not enforced for arbitrary `-li` input — the
  general `ToSMT` operand recursion has no cycle guard. It is, however, guaranteed for
  IR produced by the SMT frontend, and the shared-single-predecessor phi requirement
  ([LLVMNode.cpp:70-83](../src/LLVMNode.cpp#L70-L83)) implicitly excludes loop-header
  phis (which would otherwise throw).

- **H6 (splitter discipline).** The path splitter splits exactly the lowered phis that
  are reachable from the return value under the current selections, visiting a branch
  **condition before its arms**, and never splits a phi that occurs in neither the
  residual body nor a retained guard ([LLVMFunction.cpp:247-274](../src/LLVMFunction.cpp#L247-L274),
  `FindNextLoweredPhi`). This is a property of the implementation, stated as a
  hypothesis here.

---

## 1. Objects and the two encodings

Let `L*` be the unmerged IR. It contains lowered phis `φ_1, …, φ_x` listed in a
topological (def-before-use) order. Each `φ_i` carries a guard `g_i` (the original
select flag), a true value `t_i`, and a false value `f_i`; by H3 it denotes
`ite(g_i, t_i, f_i)`. Let `R` be the returned Boolean of `L*` (well-defined by H4),
and set

```
R^ = ⟦R⟧,    C_i = ⟦g_i⟧,    A_i = ⟦t_i⟧,    B_i = ⟦f_i⟧.
```

`C_i, A_i, B_i` are terms over `Y` and possibly over the variables of earlier phis.

### 1.1 Single-query encoding `S1`  ([LLVMFunction.cpp:227-232](../src/LLVMFunction.cpp#L227-L232))

For each lowered phi a **fresh** variable `v_i` is allocated and **cached**, so a phi
used multiple times yields exactly one variable and one constraint pair
([LLVMNode.cpp:59-86](../src/LLVMNode.cpp#L59-L86)). The encoder asserts

```
D_i  :=  (C_i → v_i = A_i)  ∧  (¬C_i → v_i = B_i)
```

with the correct polarity for both branch-successor orderings
([LLVMNode.cpp:94-103](../src/LLVMNode.cpp#L94-L103)). The single query is the
conjunction (accumulated via `AddConstraint`,
[LLVMFunction.cpp:221-225](../src/LLVMFunction.cpp#L221-L225)):

```
Φ  :=  R^  ∧  AuxDefs  ∧  ⋀_{i=1}^{x} D_i ,
```

with each `φ_i` occurring in `R^` as `v_i`. A **non-lowered** select is encoded
directly as `ite(cond, true, false)` ([LLVMNode.cpp:785-786](../src/LLVMNode.cpp#L785-L786)).

### 1.2 Path-split encoding `S_P`  ([LLVMFunction.cpp:234-316](../src/LLVMFunction.cpp#L234-L316))

A **selection** `σ` assigns `T`/`F` to (reachable) lowered phis. Recursively in
topological order:

- the σ-value of `φ_i` is `A_i^σ` if `σ(i)=T`, else `B_i^σ`, where `A_i^σ, B_i^σ, C_i^σ`
  are `⟦t_i⟧, ⟦f_i⟧, ⟦g_i⟧` with each inner phi replaced by its σ-value — a **direct
  substitution** with no fresh variable ([LLVMNode.cpp:53-57](../src/LLVMNode.cpp#L53-L57));
- the **path condition** `cond_σ = ⋀_i ℓ_i^σ`, where `ℓ_i^σ = C_i^σ` if `σ(i)=T` else
  `¬C_i^σ`, with `C_i^σ = EvaluateWithSelections(g_i)`
  ([LLVMFunction.cpp:261-271](../src/LLVMFunction.cpp#L261-L271));
- the **path body** `body_σ = R^` with each selected `φ_i` replaced by its σ-value.

The query is `Q_σ := (cond_σ ∧ body_σ).simplify()`
([LLVMFunction.cpp:240-245](../src/LLVMFunction.cpp#L240-L245)). The emitted set `Σ`
is the set of leaves of the **lazy** split tree (H6); `-max-paths` may **cap**
splitting, leaving the remaining lowered phis of a path in the `S1` implies-encoding
([LLVMFunction.cpp:292-297](../src/LLVMFunction.cpp#L292-L297)). Hence `|Σ| ≤ 2^x`.

The driver emits each `Q_σ` as an independent query, separated by `(reset)`
([main.cpp:818-831](../src/main.cpp#L818-L831)). The disjunction `⋁_{σ∈Σ} Q_σ` is
never materialized as one formula; instead it is decided **existentially** by
[parallel_solver.py](../scripts/parallel_solver.py), which splits the file at each
`(check-sat)`, runs the queries concurrently, and **stops at the first `sat`** —
reporting UNSAT only if every query is UNSAT. The point of the theorem below is
exactly that this is sound: although up to `2^x` queries are produced, deciding the
original formula reduces to solving the individual queries and accepting the **first
satisfiable one** — a single query suffices.

---

## 2. Lemmas

### Lemma 2 (implies-pair = functional `ite` naming)

For each `i`, a case split on `C_i` (total and two-valued by H2) gives

```
D_i   ⟺   v_i = ite(C_i, A_i, B_i).
```

If `C_i` holds, `D_i` forces `v_i = A_i` and its second conjunct is vacuous;
symmetrically if `¬C_i`. ∎

This is the exact bridge "select = strict `ite`".

### Lemma 1′ (unmerge-then-encode preserves satisfiability)

Let `Φ_sel` be `S1` of the **same** IR with the lowered selects **not** lowered (each
encoded as `ite`). By H1, `Φ_sel` is equisatisfiable with `F`, with model transfer
over `Y`. By H3 the lowered phi's `(g_i, t_i, f_i)` are exactly the original select's
`(flag, true, false)`, so `(C_i, A_i, B_i)` equal that select's `ite` arguments.

Hence `Φ` is obtained from `Φ_sel` by replacing, for each lowered select, its
`ite`-subterm by a fresh variable `v_i` and conjoining `D_i`, which by Lemma 2 is
exactly `v_i = ite(C_i, A_i, B_i)`. Naming a subterm by a fresh variable constrained
equal to it is a Tseitin-style definitional extension: it preserves
equisatisfiability and transfers models (in both directions). This holds regardless
of multiplicity or nesting — a single cached `v_i` per phi, and one lowered phi
feeding another's guard or arm, are handled because each `v_i` is pinned to its
defining term by its own `D_i`. Therefore `Φ` is equisatisfiable with `F`. ∎

This makes "unmerge is correct" an SMT-term identity; no appeal to poison/undef-level
IR semantics is required.

### Existential normal form

Reading `Φ` for satisfiability, the fresh `v_i` are existentially quantified:

```
Φ is SAT   ⟺   ∃Y ∃v_1…v_x.  R^ ∧ AuxDefs ∧ ⋀_i ( v_i = ite(C_i, A_i, B_i) ).
```

By H5 each `v_i` is functionally determined by `Y` and the `v_j` it depends on, in
topological order. Applying the one-point rule `∃v. (v = e ∧ M) ≡ M[v := e]`
repeatedly (innermost-last) eliminates all `v_i`:

```
Φ is SAT   ⟺   ∃Y.  Φ*(Y),
```

where `Φ*` is `R^` with every lowered phi unfolded to its `ite`-term over `Y`
(`AuxDefs` retained; `Aux ⊆ Y`). Residual non-lowered selects remain as `ite`-subterms
of `R^`. No variable capture occurs since each `v_i` is named exactly once. ∎

### Lemma 3 (guard case-split / DNF over **all** `ite`-nodes)

Let `G(Y)` be a quantifier-free SMT formula, and let `τ_1, …, τ_m` be **all** of its
`ite`-node occurrences — value-position, guard-position, and residual-select `ite`s
alike — listed in topological order, so the guard and arms of `τ_k` contain only
`τ_j` with `j < k` (well-defined by H5). A **full selection** `ρ : {1,…,m} → {T,F}`
chooses each `ite`'s branch. Define `G_ρ` = `G` with each `τ_k` replaced by its
`ρ(k)`-arm; `guard_k^ρ` = the guard of `τ_k` with inner `ite`s resolved by `ρ`; and
`cond_ρ = ⋀_k ℓ_k^ρ` with `ℓ_k^ρ = guard_k^ρ` if `ρ(k)=T` else `¬guard_k^ρ`. Then

```
G   ⟺   ⋁_{ρ ∈ {T,F}^m} ( cond_ρ ∧ G_ρ ),
```

and the `cond_ρ` are pairwise contradictory with `⋁_ρ cond_ρ ≡ ⊤`; the disjuncts thus
partition the models of `Y` into pairwise-disjoint cells whose union is everything
(some cells may be infeasible/empty).

**Proof (pointwise).** Fix an assignment `α` to `Y`. Evaluating `ite`-nodes
bottom-up, each guard takes a definite value `b_k(α)` (totality, H2). Let
`ρ*(k) = b_k(α)`.

- *Satisfied condition is unique.* For `ρ*`: by induction on `k`, `ρ*` agrees with `α`
  on all `j < k`, so the inner `ite`s of `guard_k` resolve under `ρ*` exactly as they
  evaluate under `α`, giving `guard_k^{ρ*}(α) = guard_k(α) = b_k`; the chosen literal
  matches, so `cond_{ρ*}(α) = ⊤`. For any `ρ ≠ ρ*`, let `k_0` be the least index with
  `ρ(k_0) ≠ b_{k_0}`. On `j < k_0`, `ρ` agrees with `α`, hence
  `guard_{k_0}^ρ(α) = b_{k_0}`; but `ρ(k_0) ≠ b_{k_0}`, so `ℓ_{k_0}^ρ(α)` is false and
  `cond_ρ(α) = ⊥`.
- *Body agreement.* Under `ρ*` every `ite` resolves to the branch `α` takes, so
  `G_{ρ*}(α) = G(α)`.

Thus the right side at `α` equals `cond_{ρ*}(α) ∧ G_{ρ*}(α) = G(α)`, and exactly one
condition holds. ∎

### Corollary 3a (partial DNF over a subset)

Let `S` be any subset of `ite`-nodes. Then

```
G   ⟺   ⋁_{ρ over S} ( cond_ρ ∧ G_ρ ),
```

where only the `S`-nodes are resolved and non-`S` `ite`s remain symbolic inside both
`cond_ρ` and `G_ρ`; the `cond_ρ` partition the models of `Y` into pairwise-disjoint,
possibly-empty cells covering `⊤`.

**Proof.** Marginalize Lemma 3 over the non-`S` nodes: for any non-`S` node `τ`,
`(P ∧ guard_τ ∧ …) ∨ (P ∧ ¬guard_τ ∧ …)` collapses since `guard_τ ∨ ¬guard_τ ≡ ⊤`
and `τ` stays symbolic in the body. The pointwise argument of Lemma 3 is unchanged:
at each `α`, the non-`S` `ite`s evaluate directly, and the `S`-restricted `cond_ρ`
still pick out exactly one cell. ∎

### Lemma 4 (laziness + capping faithfulness)

```
⋁_{σ∈Σ} Q_σ   is equisatisfiable with   Φ*.
```

**Proof.** Induct on the split tree, whose nodes carry an accumulated condition `P`
and a residual body `H` (`= Φ*` with the already-chosen phis resolved); the root has
`P = ⊤`, `H = Φ*`.

- *(a) Split step.* When the splitter picks the next reachable lowered-phi `ite` `τ`
  with guard `guard_τ = EvaluateWithSelections(g)` (prior selections resolved):

  ```
  P ∧ H  ⟺  ( P ∧ guard_τ ∧ H[τ:=T] )  ∨  ( P ∧ ¬guard_τ ∧ H[τ:=F] ),
  ```

  which is the single-`ite` case split (Lemma 3 with one node), valid because
  `guard_τ` is two-valued (H2). If `guard_τ` itself contains an *unsplit* lowered phi
  left in the implies-encoding — the **mixed-condition** case that
  `EvaluateWithSelections` actually produces
  ([LLVMFunction.cpp:95-102](../src/LLVMFunction.cpp#L95-L102), confirmed) — first
  rewrite that `v_j` by `ite(C_j, A_j, B_j)` using Lemma 2 (legitimate under the
  retained `∃v_j` with `D_j` pinning it), restoring a `Y`-definite guard; the split
  then applies and equisatisfiability is preserved (`∃` distributes over `∨`).

- *(b) Leaf step.* At a leaf, any remaining unsplit lowered phis are `S1`-encoded
  (fresh `v_i` with `D_i`,
  [LLVMFunction.cpp:292-297](../src/LLVMFunction.cpp#L292-L297)); by Lemma 2 this only
  names `ite`-subterms by fresh equal variables, so the leaf query is equisatisfiable
  with `P ∧ H`. Residual non-lowered selects remain as the identical `ite` on both
  sides ([LLVMNode.cpp:785-786](../src/LLVMNode.cpp#L785-L786)).

By H6 the splitter splits exactly the lowered phis occurring in the residual body or a
retained guard, so a phi affecting neither stays in `H` unchanged on both sides and
contributes nothing. Propagating the equivalences of (a) and the equisatisfiabilities
of (b) from the root downward, `Φ*` equals — up to equisatisfiability — the
disjunction of leaf queries. ∎

---

## 3. Main theorem

**Theorem (satisfiability equivalence of unmerge + path splitting).**

```
F is SAT
   ⟺  Φ is SAT                      (Lemma 1′)
   ⟺  ∃Y. Φ*(Y)                     (existential normal form)
   ⟺  ( ⋁_{σ∈Σ} Q_σ ) is SAT        (Lemma 4)
   ⟺  ∃ σ ∈ Σ.  Q_σ is SAT.
```

Every step is a genuine equisatisfiability with a consistent existential prefix
(`∃Y`, with the `v_i` eliminated in the normal form and reintroduced only as
definitional names in the capped leaves of Lemma 4). ∎

The headline consequence is that the rightmost equivalence,
`(⋁_σ Q_σ) SAT ⟺ ∃σ. Q_σ SAT`, lets us decide `F` **one query at a time**: the
disjunction is never built as a formula, and we never need all `2^x` answers.

### 3.1 Decision procedure — a single satisfiable query suffices

This is what [parallel_solver.py](../scripts/parallel_solver.py) realizes (run the
`Q_σ` concurrently, stop at the first `sat`).

**Theorem (single-query reduction).** Let `R` be any procedure that searches `Σ` and
returns `SAT` upon discovering one `σ` with `Q_σ` SAT, and `UNSAT` only after every
`σ ∈ Σ` has returned UNSAT (order, batching, and parallelism arbitrary). Then `R`
decides the satisfiability of `F`.

**Proof.**

- *Soundness (early stop is valid).* If `R` finds any `Q_σ` SAT, then `⋁_σ Q_σ` is SAT,
  so by the Main Theorem `F` is SAT. Thus the **first** satisfiable query already
  certifies `F` SAT and the remaining queries can be abandoned — no later query can
  overturn the verdict. A model of `F` over `X` is read directly off the model of
  `Q_σ` (the phi/select values are the derived branch values; no extra witnesses are
  needed), recovered over the original variables via H1.
- *Completeness (UNSAT needs all).* If no `Q_σ` is SAT, then `⋁_σ Q_σ` is UNSAT, so by
  the Main Theorem `F` is UNSAT. Establishing this requires every query to be
  refuted — hence UNSAT, and only UNSAT, is an "all paths" verdict. ∎

**Why the search space is clean (no redundant work in principle).** In the *uncapped*
expansion the `cond_σ` partition the models of `Y` into pairwise-disjoint,
possibly-empty cells covering `⊤` (Corollary 3a). So every model of `F` lies on
**exactly one** emitted path: the paths carve the search space without overlap, and a
satisfying assignment cannot be "split" across queries. In the *capped* expansion the
conditions still cover `⊤` (disjointness may be lost where leaves retain the
implies-encoding), and "`F` SAT iff some `Q_σ` SAT" still holds by Lemma 4 — so the
single-query reduction is unaffected by capping; only the disjointness guarantee
weakens.

---

## 4. Scope and remarks

- **Where `2^x` comes from / why disjunction.** Each unmerged select contributes one
  binary guard; the queries are the leaves of the binary case-split tree, and `SAT`
  distributes over the disjunction of leaves — so checking queries independently and
  OR-ing the verdicts is exactly correct.
- **The disjunction is decided, not built.** The driver only serializes each `Q_σ`
  ([main.cpp:818-831](../src/main.cpp#L818-L831));
  [parallel_solver.py](../scripts/parallel_solver.py) then solves the queries
  concurrently and returns SAT on the first satisfiable one (killing the rest), UNSAT
  only if all fail. By §3.1 this is exactly a sound decision procedure for `F`: a
  single satisfiable query suffices, and no disjunction formula is ever constructed.
- **Mixed conditions under capping** are handled by Lemma 4(a) (rewrite the unsplit
  `v_j` via Lemma 2 before splitting); they are why the path condition is not always a
  pure `c`/`¬c` literal.
- **`simplify()`** is applied to each path query
  ([LLVMFunction.cpp:244](../src/LLVMFunction.cpp#L244)) and preserves equivalence; the
  single query is not simplified — immaterial to the theorem.
- **Partial unmerging** (`-unmerge-first/-last/-random/-chain/-all`) is the same
  theorem with `x` = number of *lowered* selects; un-lowered selects stay as `ite` in
  both `Φ` and every `body_σ` and are simply never case-split.
- **Out of scope by hypothesis:** unsupported opcodes (H2), loops / φ-cycles (H5),
  non-`i1` or vector-of-`i1` flags (H3), and functions without a single return (H4).
  Each is rejected or assumed away by the implementation.
