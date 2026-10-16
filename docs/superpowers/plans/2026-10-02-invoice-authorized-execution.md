# Invoice authorized execution — implementation plan

> **Historical — superseded on 2026-10-13.** This completed plan records prior technical work and QA, not active implementation instructions. The current academic flow is documented in [the evaluation protocol](../../invoice_academic_evaluation_protocol.md) and [the evaluator documentation](../../invoice_final_executor.md). Contractual execution steps below must not be rebuilt or treated as pending tasks.

> **For agentic workers:** use `superpowers:executing-plans`, TDD and a fresh independent final review. User requested autonomous execution; no commits, push or real data execution.

**Goal:** close historical-evidence binding and the authorized input → scoring → publication handoff, tested only with generated fixtures.

**Architecture:** retain the adapter and input-validation route. Extend the pre-access contract to 1.2 with pinned historical evidence. A separate, explicit runner consumes an unused receipt, validates inputs, calculates existing metrics once and publishes an exclusive bundle; it cannot resume an already consumed input-only attempt. No CLI or approval generator.

**Tech Stack:** existing Python/pandas/scikit-learn/joblib/pytest, no new dependency.

**Spec:** `docs/invoice_academic_evaluation_protocol.md`, `docs/invoice_final_executor.md` and the user's 95fb8d1 follow-up. The methodological contract is unchanged.

## Constraints and rulings

- No TEST/data/model access in this task. Only the three historical Invoice JSONs may be read/hashed as evidence; fixtures generated outside checkout exercise the runner.
- Preserve all 19 features, parameters, offset, budgets 1/5/10, signed-value baseline and `source_reconciled=false`.
- Identity hashes are not human authentication or legacy training provenance.
- Work in the requested checkout; preserve both locally modified Supplier notebooks. No staging/commit/cleanup of user files.
- User delegated technical decisions and execution; no intermediate approval prompts or real authorization documents.
- Atomic/exclusive local operations protect against accidental retries; hostile filesystem writers are outside the existing trust model.

## Review focus

- Old 1.1 authorizations must not silently enable scoring/publication in 1.2.
- Historical JSONs must be checked from exact bytes/paths, not only hashes written in Markdown.
- Expiry/document/input changes between stages must stop scoring/publication, consuming the attempt.
- Separate input-only execution must not be reusable for another evaluation; no caller-provided frame/model bypass.
- Publication must require a valid run, exact destination and complete evidence, not caller-supplied metrics.

## Task 1 — historical evidence and gate binding

Files: new `ml/scripts/invoice_historical_evidence.py`, its synthetic tests; modify gate and its fixtures.

- [x] Audit three real JSON byte identities and historical cross-references read-only, without dataset access.
- [x] RED: synthetic history verifier rejects missing/mutated JSON, malformed structures, mismatched model/features and references; gate rejects missing/incorrect evidence bindings and old schema.
- [x] Implement `verify_historical_evidence(root, expected_hashes, configuration, pre_access_sha256)` with exact path allowlist and pinned identities; return only an integrity summary. Gate schema 1.2 binds evidence and new source modules before input I/O.
- [x] GREEN: relevant synthetic tests pass under real-input read guards.

## Task 2 — explicit authorized execution

Files: new `ml/scripts/invoice_real_evaluation.py` and tests; minimal extraction of the existing in-memory calculation; input route retains no automatic scoring.

- [x] RED: `run_authorized_evaluation(..., start_evaluation=False, split='test')` cannot access inputs by default; valid fixture yields all budgets, provenance false, receipts, metrics and manifest without fit.
- [x] Test absent/tampered/expired authority, wrong freeze/hash/input/split/feature order, symlink/path escape, raw access before authority, copies, retries, publication without run and overwrite. Symlink-dependent cases have explicit Windows skips below.
- [x] Implement runner: validate external pins → consume fresh input route → recheck documents/inputs → exclusive scoring marker → shared metrics once → recheck → exclusive pending bundle → verify → publish.
- [x] Implement `verify_real_bundle(...)` using external manifest/freeze pins and bound authorization/receipt/input/scoring records; no dataset reopening during verification.
- [x] GREEN: integration plus Invoice regression; preserve synthetic-only public evaluator and no CLI/real approval issuer.

## Task 3 — validation, review and technical docs

- [x] Full synthetic regression with protected-path read instrumentation; record skips and dependency versions.
- [x] Ruff on affected files and `git diff --check`.
- [x] Independent read-only review; significant fixes require RED→GREEN evidence.
- [x] Update only technical status/protocol/roadmap/README; no academic results/report.
- [x] Compare notebook and historical JSON hashes; report exact Git scope and remaining human gate.

## Execution ledger

- Initial HEAD 95fb8d1; only Supplier notebooks 01/02 locally modified (kernel display names), preserved.
- Ruling: use the existing checkout and keep a plan ledger here; no worktree transfer or commits, matching the user's continuation/review scope.
- Ruling: fresh temporary runtime needed because both old environments cannot import pandas dependencies; use unchanged requirements-dev.txt pins.

### Closure — 05/10/2026

- Invoice suite: **591 passed, 8 skipped in 135.22s**.
- Full regression: **816 passed, 8 skipped in 137.32s**. Both runs used `python -I -B`, an external exclusive temporary directory, pytest cache disabled, and process-level guards on real project datasets/models/evidence. **REAL_PROJECT_DATA_ACCESS_ATTEMPTS=0** in both runs. These guards are instrumentation, not an operating-system sandbox.
- Skips: five adapter symlink cases, one synthetic executor symlink case, one historical-evidence symlink case, and one legacy-boundary symlink case. This Windows host could not create those links; the cases were not represented as passing.
- Ruff on all nine involved Python files: **All checks passed!**. `git diff --check` passed; new untracked files were also checked separately for whitespace.
- Runtime: Python 3.14.3, pandas 2.3.3, NumPy 2.5.2, PyArrow 25.0.1, scikit-learn 1.9.0, joblib 1.6.0, pytest 9.1.1 and Ruff 0.16.5. Installed unchanged requirements-dev.txt pins in a separate disposable environment; no main-environment/dependency-file changes.
- Independent review found two integration defects: input mutation during bundle construction could evade the last check, and an accepted uppercase-hash receipt failed publication. Both were reproduced RED, corrected and passed GREEN. Tests also exposed missing evidence/frame and source-consistency checks, now enforced. Final static code review: no remaining blocker within the documented cooperative-filesystem scope.
- Historical verifier RED→GREEN also removed caller-key-order dependency and rejects JSON numeric overflow/path redirection. The first interrupted integration run failed on key order; after that correction, six old fixture expectations were updated to reach their intended contract boundary. These intermediate failures are superseded by the final green regression, not omitted as successes.
- The three historical JSONs match the exact SHA-256 identities in the academic protocol. Read-only verification confirmed their internal links, shared validation IDs and compatibility with the legacy contract. No referenced dataset/model was reopened to rehash it; no historical metric was recalculated. This is integrity/compatibility evidence, not independent training provenance.
- Preserved notebook SHA-256: `01_supplier_risk_eda.ipynb` = `f750a05c83637f09faa9c9fce357c8f0448bc98f47f1d3e0bfc150e6f2f83e3f`; `02_supplier_risk_baseline_models.ipynb` = `8c31090637683cc0391075e5211b78ee3772cbf98a6b8a0ba479c0b1283dcc46`. Both retain preexisting local changes and remain outside this task/staging.
- No real TEST content was read, hashed, scored or evaluated. No real authorization, training, notebook execution, dataset/model/label changes, staging, commit or push. TEST files were deliberately not opened to claim a before/after cryptographic comparison.
- Remaining boundary: review and issue an exclusive formal freeze, then obtain independent human approval/pins acknowledging the legacy provenance limits. Implementation is not approval. `source_reconciled=false` remains required. Do not run input validation as a real dry run; it consumes the attempt.

### Changed-file inventory

Created: this plan; `ml/scripts/invoice_historical_evidence.py`; `ml/scripts/invoice_real_evaluation.py`; `tests/invoice/invoice_history_fixtures.py`; `tests/invoice/test_invoice_historical_evidence.py`; `tests/invoice/test_invoice_real_evaluation.py`.

Modified: `README.md`; `docs/implementation_roadmap.md`; `docs/model_strategy.md`; `docs/invoice_academic_evaluation_protocol.md`; `docs/invoice_final_executor.md`; `ml/scripts/invoice_final_evaluation.py`; `ml/scripts/invoice_real_inputs.py`; `tests/invoice/test_invoice_authorization.py`; `tests/invoice/test_invoice_real_inputs.py`.

The adapter implementation, historical JSONs, datasets, models, scientific results and Supplier notebooks were not edited. HEAD remains `95fb8d1`; all task changes are unstaged for human review.

## Final pre-freeze review — 06/10/2026

This is a separate continuation requested after the integration above. No formal
freeze, real approval, input-route rehearsal, scoring or scientific result was
produced. The new request permits hashing the four separate pre-access files;
TEST and shared raw remain excluded from resolution, inspection and hashing.

- [x] Independent static review of gate, inputs, runner, publication and tests.
- [x] Reproduce five failing synthetic cases before the localized fixes: two
  invalid document paths, an invalid receipt path, a complete but unpublished
  partial bundle, and incomplete execution receipts before staging creation.
- [x] Reject incorrect document names/receipt location before resolving them;
  reject pending bundles through the public final-result verifier; require all
  three execution receipts before creating staging. Private staging verification
  remains internal to the runner and does not publish results.
- [x] Strengthen historical semantic tests by refreshing descendant references
  and checking the intended rejection reason, not an unrelated stale digest.
  Valid-bundle verification is also exercised with synthetic input reads denied.
- [x] Focused GREEN: **244 passed, 1 skipped in 88.93s**.
- [x] Invoice suite: **595 passed, 8 skipped in 140.13s**.
- [x] Full regression: **820 passed, 8 skipped in 139.63s**.
  All three runs used external synthetic fixtures, `python -I -B`, no pytest
  cache, and the protected-input audit guard: **REAL_PROJECT_DATA_ACCESS_ATTEMPTS=0**.
  The eight skips are the same Windows symlink privilege cases listed above;
  they are not represented as passing. No dependency/environment upgrade occurred.
- [x] Scoped Ruff on the same nine Python files: **All checks passed!**.
- [x] `git diff --check` and whitespace checks of each new untracked file:
  approved. Git emitted only LF/CRLF conversion notices, not whitespace errors.
- [x] Recheck exact bytes and internal links of the three historical JSONs;
  all match the pins. No metrics were recomputed. The four pre-access SHA-256
  identities also match historical references; they were only hashed, not
  deserialized or scored. Supplier notebook hashes remain as recorded above.
- [x] Independent follow-up found no remaining code blocker under the existing
  cooperative-filesystem trust model. Documented that bundle metric validation
  checks limited invariants, not exhaustive semantic correctness or authenticity.
- [x] Add dated technical notes to the three historical reports: their results
  remain unchanged; old commands are not current permission to re-run real data
  or copy sources around fixture guards. Other current overview docs already
  reflect the technical integration and were preserved during this continuation.
- [x] Prepare `docs/invoice_freeze_preparation.json`, schema
  `invoice-freeze-preparation/1.0`, as a non-executable inventory, not a real
  freeze or authorization. It records candidate ID, code and allowed-input hashes,
  versions and unresolved provenance. TEST/raw content hashes are null; no run
  destination or human identity exists. Schema rejection occurs before path I/O.
  Independent review caught JSON serialization of `max_features` as `1` rather
  than strict `1.0`; the literal was corrected and canonical comparison checked.
  Final preparation SHA-256:
  `036021fd68d98e9c93ceb0a6fcf31910dc14ae436b48067c103007f6e0ae7563`.
  Candidate ID: `invoice-prefreeze-4dbb67f7-1206-43a2-82b4-0cbb4fb946de`.
  These identify a draft, not permission or a certified immutable formal freeze.

Files edited in this continuation (some were already dirty/untracked from integration):

- `ml/scripts/invoice_final_evaluation.py`
- `ml/scripts/invoice_real_inputs.py`
- `ml/scripts/invoice_real_evaluation.py`
- `tests/invoice/test_invoice_authorization.py`
- `tests/invoice/test_invoice_real_inputs.py`
- `tests/invoice/test_invoice_real_evaluation.py`
- `tests/invoice/test_invoice_historical_evidence.py`
- `docs/invoice_final_executor.md`
- `docs/invoice_validation_results.md`
- `docs/invoice_triage_results.md`
- `docs/invoice_value_comparison_results.md`
- This plan ledger.

Only newly created file in this continuation: `docs/invoice_freeze_preparation.json`.
Existing notebooks, datasets, models, splits, historical evidence and Supplier
final results were not edited. No staging, commit or push. The next boundary is
human review and issuance of a separate formal freeze/independent authorization;
the draft does not grant permission to open TEST. Software verification does not
certify training provenance, fraud truth or operational usefulness.

## Formalization audit — 06/10/2026 (formal issuance blocked)

The subsequent request requires a portable formal control artifact, without
personal, temporary or machine-specific paths. No production code, preparation
inventory, model, dataset, historical result or notebook was changed in this audit.

- Recomputed all **29 permitted file hashes** in the preparation inventory:
  ten executor sources/protocol, ten supporting files, four separate pre-access
  inputs/model files, three historical JSONs and two protected Supplier notebooks.
  All match. The notebook hashes are preservation evidence, not Invoice runtime
  dependencies. TEST/shared raw were excluded from all reads and hashes.
- Preparation inventory SHA-256 remains
  `036021fd68d98e9c93ceb0a6fcf31910dc14ae436b48067c103007f6e0ae7563`.
  Canonical configuration, 19-feature order, model/metadata identities and history
  links match. The historical validation-ID fingerprint was compared as recorded;
  it was not recomputed from dataset rows. No claim about TEST IDs was made.
- Python 3.14.3 and all **22 package pins** in requirements/requirements-dev match
  the isolated QA environment. The current gate verifies only six runtime version
  fields, not every transitive package or library byte. Supplemental QA metadata
  must not be copied into its strict `versions` map without changing the contract.
- Fresh synthetic Invoice suite: **595 passed, 8 skipped in 146.80s**;
  **REAL_PROJECT_DATA_ACCESS_ATTEMPTS=0**. The skips are the eight previously
  listed Windows symlink privilege cases. Scoped Ruff: **All checks passed!**.
  No code changed, so full regression was not repeated. These tests validate the
  existing contract, not a new formal artifact that has not been issued.
- Independent read-only review confirmed a contract conflict: schema
  `invoice-real-preregistration/1.2` requires exactly twelve top-level keys,
  absolute `project_root`/`run_dir`/input paths, an external execution directory,
  and `freeze.json` bound to that directory. The authorization and bundle also
  bind this destination. A portable manifest is not an admissible 1.2 freeze.
- No formal freeze was issued and no authorization was created. Merely changing
  `formal_freeze` or renaming the preparation file would misrepresent its validity.
  No input-only dry run, inference, training, scientific evaluation, staging,
  commit or push occurred. `source_reconciled=false` remains unchanged.

Required design decision before implementation: adopt a portable control freeze
and an explicitly bound execution context, with a versioned gate/bundle contract
and synthetic tests for their cryptographic binding; or explicitly revise the
portability requirement to retain the existing machine-bound 1.2 contract.
The recommended direction is portability with a separately bound context, not
silently loosening the current path checks. This is a contract change to review,
not human authorization to open TEST. Until resolved, keep the gate blocked and
preserve the preparation inventory as a draft.
