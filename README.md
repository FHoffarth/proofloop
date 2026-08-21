# ProofLoop

**Evidence-aware multi-model engineering for software changes you can actually verify.**

ProofLoop is a small, deterministic orchestration layer for AI-assisted software engineering.

It is built around one core rule:

> **Agent reports are claims. Git, tests, files and artifacts are evidence.**

Most multi-agent coding systems optimize for conversation, autonomy and task completion.
ProofLoop optimizes for something else:

**Can the system prove what it says happened?**

---

## Why ProofLoop exists

AI coding tools are useful, fast and increasingly autonomous.
They also have a recurring failure mode:

- an agent says a bug is fixed
- another agent agrees
- a judge model approves
- the repository tells a different story

ProofLoop treats that gap as an engineering problem.

Instead of allowing model confidence to become truth, ProofLoop separates:

- **reasoning**
- **claims**
- **evidence**
- **verification**
- **judgment**
- **final disposition**

LLMs may propose, critique and judge.
They may not manufacture proof.

---

## The core law

> **LLM verdicts cannot override deterministic proof gates.**

A model can say:

- "the fix looks correct"
- "this should be safe to merge"
- "the architecture is sound"

Those are evaluative claims.
They can inform a decision, but they do not become `PROVEN` merely because multiple models agree.

Only deterministic evidence can establish deterministic facts.

Examples:

- commit exists
- commit touches expected files
- file contains expected content
- test command passed
- working tree is clean
- branch points at expected SHA

---

## Pipeline

```text
Problem
  ↓
Planner
  ↓
Critic
  ↓
Claims
  ↓
Evidence Verifier
  ↓
Pre-Gate
  ├─ BLOCKED → stop
  ↓
Judge
  ↓
Final Proof Gate
  ↓
PASS / REVIEW_REQUIRED / BLOCKED
```

ProofLoop deliberately short-circuits expensive model reasoning when deterministic evidence has already failed.

> **Deterministic blockers stop expensive reasoning early.**

---

## Verification model

ProofLoop distinguishes between deterministic and evaluative claims.

### Deterministic claims

These can become `PROVEN` when the referenced evidence verifies them:

* `COMMIT_EXISTS`
* `COMMIT_TOUCHES_FILES`
* `FILE_CONTAINS`
* `TEST_PASSED`
* `WORKTREE_CLEAN`
* `BRANCH_AT_SHA`

### Evaluative claims

These can never become automatically proven:

* `BUG_FIXED`
* `SAFE_TO_MERGE`
* `NO_REGRESSION`
* `ARCHITECTURE_CORRECT`
* `GENERAL_INFERENCE`

Evaluative claims remain `INFERRED` unless a human makes the final decision.

---

## Gate results

ProofLoop produces one of three final outcomes:

| Result            | Meaning                                                                                |
| ----------------- | -------------------------------------------------------------------------------------- |
| `PASS`            | Required deterministic evidence is verified and no unresolved evaluative claims remain |
| `REVIEW_REQUIRED` | Evidence is valid, but a human decision is still required                              |
| `BLOCKED`         | Required evidence failed, is missing, or the pipeline failed                           |

CLI exit codes follow the same contract:

```text
0 = PASS
1 = REVIEW_REQUIRED
2 = BLOCKED / pipeline failure
```

This makes ProofLoop suitable for local workflows and CI pipelines.

---

## Offline-first architecture

The first ProofLoop milestone intentionally has **no live model dependencies**.

The offline foundation contains:

```text
proofloop/
├── agents/
├── evidence/
├── providers/
├── schemas.py
├── gate.py
├── profiles.py
├── registry.py
├── orchestrator.py
├── render.py
└── cli.py
```

The initial provider is a deterministic `FakeProvider`.
This allows ProofLoop to verify its own orchestration, evidence logic and security boundaries before real model APIs are introduced.

---

## Security principles

ProofLoop's evidence layer is intentionally conservative.

* no `shell=True`
* no arbitrary command execution
* repository paths must stay inside the configured repository root
* path traversal is rejected
* only explicitly allowed command patterns may execute
* missing evidence fails closed
* failed evidence remains visible
* model output cannot modify verification results

The verifier is not an agent.
It is infrastructure.

---

## Workflow profiles

Different tasks require different evidence.
ProofLoop therefore uses explicit workflow profiles instead of globally hard-coded requirements.

```text
verify-commit
verify-fix
inspect-file
quick-check
none
```

Example:

```bash
proofloop solve \
  "Verify that this commit contains the expected fix" \
  --repo . \
  --profile verify-commit \
  --commit HEAD
```

Run `proofloop profiles` to list them with their descriptions.

---

## Installation

```bash
pip install -e .
```

Dependencies are `pydantic` and `rich`; `pytest` for the test suite.
No model SDK is installed, and no API key is required.

```bash
pytest -v -m "not integration"
```

---

## Dogfooding

ProofLoop should be able to test its own core claim.
A canonical first check is:

```bash
python -m proofloop.cli solve "Verify that ProofLoop blocks an invalid commit claim" --repo . --profile verify-commit --commit deadbeefdeadbeefdeadbeefdeadbeefdeadbeef
```

Expected behavior:

```text
Invalid commit     FAILED
Pre-gate           BLOCKED
Judge              SKIPPED
Final disposition  BLOCKED
Exit code          2
```

If ProofLoop cannot prove that ProofLoop works, it is not done.

---

## Roadmap

### Phase 1 — Offline foundation

* evidence models
* Git/file/test verification
* proof gate
* fake providers
* orchestration
* workflow profiles
* CLI
* CI exit codes
* adversarial tests

### Phase 2 — Real model adapters

Adapters will be introduced individually:

* OpenAI
* Anthropic
* Gemini

All providers must conform to the same structured contract.
No provider is allowed to bypass the proof gate.

### Phase 3 — Multi-model engineering

Planned live topology:

```text
Planner    → model A
Critic     → model B
Judge      → model C
Verifier   → deterministic
Proof Gate → deterministic
```

The models may disagree.
The evidence layer does not negotiate.

---

## What ProofLoop is not

ProofLoop is not:

* an autonomous coding swarm
* a replacement for tests
* a replacement for code review
* a confidence voting system
* a system where three agreeing LLMs magically create truth

It is a small control layer for making AI-assisted engineering claims more auditable.

---

## Project status

**Early experimental build.**

The current priority is the offline verification foundation.
Live model integrations are intentionally deferred until the deterministic core is proven.

---

## Philosophy

ProofLoop follows a few simple rules:

> **Agent reports are claims. Repository state is evidence.**
> **LLM verdicts cannot override deterministic proof gates.**
> **Deterministic blockers stop expensive reasoning early.**
> **Structured output reduces chaos. It does not eliminate hallucination.**
> **Proof must come from the system that owns the truth.**

---

## License

TBD.
