# M3 Exit Evidence — Claude Milestone Declaration Checklist

**Status:** Working checklist, not a milestone declaration. As of 23 November 2026, Claude has not recorded an exact M3-reached confirmation. ChatGPT maintains this evidence checklist and may report evidence gaps; only Claude's explicit collaboration-log entry may declare M3 reached.

**Post-#188 correction (Claude review):** #189 (RT05c) merged at exact head `21b540ee91cbfb47335156c8f2c2510b1b4d7d45`, merge/main `757da519f7af2c75a515ca42c6d23015d9e47123`, run `45141079904`, 4/4; it closes the three residual backup findings (record always required, stopped record needs seal-free chain, strict run_id). Path-based SQLite reopen (TOCTOU) remains the documented owner-gated boundary. #189 is the latest code merge; main is `757da519`.

**Assessment base:** main `a2473cf1bd196e84fdc6301152c30b7ac94f1bd1` (23 November 2026; latest main includes documentation sync #188; latest code merge remains #186).

## 1. Merged implementation slices

| Slice | Merged PR | Mainline evidence | Exact-head CI |
|---|---:|---|---|
| 4.1 deterministic projection | #163 | `agora/scenario_projection.py`, tests; pure projection, explicit mapping/allow-list/bounds | Confirm exact run/job evidence in Claude's log before final declaration |
| 4.1b fail-closed projection hardening | #164 | `agora/scenario_projection.py`, tests; sensitivity and mapping/hash validation tightened | Confirm exact run/job evidence in Claude's log before final declaration |
| 4.2 governed engine integration | #171 | `agora/sim/engine.py` plus tests only; optional governed input, verification, append-once provenance guard, changed-input/legacy/force refusal | Run `45089066900`, 4/4 |
| 4.3 governed CLI | #172 | `agora/cli.py` plus tests; exact import ID, binding/pack/mapping args, `--force` refusal, exit 3 on engine refusal | Run `45093439437`, 4/4 |
| 4.4 instance-row integrity | #173 | `agora/scenario_projection.py` plus tests; order-independent `instances_hash` included in `projection_hash` | Run `45096233966`, 4/4 |
| 4.6 base/projected scenario hashes | #178 | `agora/sim/engine.py` plus tests only, within the owner's named scope; original `scenario.yaml` hash is `base_scenario_hash`, separate `projected_scenario_hash` binds it to `projection_hash` | Run `45113858688`, 4/4 |

For #171–#173 and #178, 4/4 means Ubuntu/Windows × Python 3.11/3.12 jobs all completed successfully. Claude's log reports 15 new engine tests, 7 CLI tests, 2 row-hash tests and four hash-split regression cases, plus local full-suite/mutation results; ChatGPT did not run or independently reproduce those local tests. For #178, exact head `a620feb98d342250e29ded132781630fcb31f395` passed run `45113858688` 4/4. Its diff changes only `agora/sim/engine.py` and `tests/test_engine_governed_input.py`; the sole `agora/sim/**` path remains the owner-approved `engine.py`. Confirm exact merge-head and workflow evidence for every implementation PR; do not rely on a branch-head result if the merged SHA differs.

**Supporting validation utility (not an M3 engine slice):** #175 adds pure benchmark metrics/baselines in `agora/validation/benchmark_metrics.py`; exact PR-head CI `45105990141` passed 4/4. Follow-up #176 hardens boolean, date and window validation and pins the official M5 RMSSE scale convention (differences start at the first non-zero training observation; pre-sale leading zeros are excluded); exact-head CI `45110601617` passed 4/4. #179 adds strict `samples`, `min_clusters` and `alpha` guards; exact-head CI `45116463242` passed 4/4. #180 adds a non-negative seed guard (merged at `82c830fd`, merge commit `76ee7625`; exact-head CI run `45119572140` passed 4/4). These supporting utilities do not complete the governed engine slices or authorize data use; no dataset run is authorized.

**Documentation evidence:** ChatGPT docs PR #181 merged at exact head `73a4947efc1beb94b55718568a1d453d579bae1b` (merge commit/main `9dad1c8f9ab9ccc3c73aee76403cecab222d25e6`); exact-head CI run `45122674011` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. Its five changed paths were exclusively `docs/**`. This is documentation evidence only; it does not close the policy-authorization, validation-protocol approval or dataset-register gates.

**Subsequent mainline security and documentation evidence — 23 November 2026:**
- Track A PR #183 merged at exact head `0f870e22aad3d2496a5da872c21c5871106e262d`; exact-head CI `45126668732` passed 4/4. It adds static symlink/reparse-point refusal for audit chain, anchor and lock paths. This does not prove resistance to concurrent path replacement; that TOCTOU boundary remains conditional on the owner's threat-model decision.
- Backup RT05b PR #186 merged at exact head `b50e1e3f6386e6762de83c08023721d7882a720e`; exact-head CI `45137276771` passed 4/4. It tightens run-record/seal consistency. The independent review recorded in `RUNG_STATUS.md` still identifies residual unsealed-record/status-and-ID cases and path-based SQLite reopen risk; do not treat #186 as closing those findings.
- Dataset download guide and M3 documentation/exit checklist were included in ChatGPT docs PR #174, merged at exact head `e231961494a849d092c45a9a9377855fe30f188b` (merge commit `aeb9ab08046268674ef7c848f78ad17fb2002738`); exact-head CI `45107961493` passed 4/4. Ten changed paths were all under `docs/**`.
- Follow-up ChatGPT docs PR #188 merged at exact head `3704728a9623365c7c7e2dd7b736cd2d53fcd175` (merge commit/current main `a2473cf1bd196e84fdc6301152c30b7ac94f1bd1`); exact-head CI `45138934878` passed 4/4. Five changed paths were all under `docs/**`, syncing the M3 design, provenance, rung status, validation protocol and dataset checklist.

These supporting security, metrics and documentation merges do not resolve the production identity/policy boundary, do not freeze the validation protocol, and do not authorize dataset acquisition/use or a simulation/validation run.



## 2. Scope and safety evidence

- [ ] Review changed-file lists for #163/#164/#171/#172/#173/#178 and confirm no unauthorized path under `agora/sim/**` was edited. #171 and #178 touch only the owner-approved `agora/sim/engine.py`; #172/#173 and projection slices remain outside `agora/sim/**`.
- [ ] Confirm the default `governed_input=None` path remains compatible and the legacy run path is not silently treated as governed.
- [ ] Confirm no simulation, calibration, backtest, forecast, validation or real/public dataset run occurred without separate owner approval. Unit tests with synthetic fixtures/mock backend are not dataset runs.
- [ ] Confirm `VALIDATED_PREDICTION_ENABLED=False` remains unchanged.
- [ ] Confirm no real/personal/customer data, credentials, connectors, network fetches or write-back were introduced.

## 3. Blocking correctness and trust-boundary findings

These are not waived by merged PRs or green CI:

Resolved by #178: `base_scenario_hash` is captured from the original `scenario.yaml` before projection; `projected_scenario_hash` is separate and bound to `projection_hash`. The exact-head CI passed 4/4 and merged tests cover row/mapping changes plus unchanged-envelope resume refusal. Claude reports local mutation proofs; ChatGPT did not reproduce them.
1. **Policy authorization boundary:** the CLI currently calls `_governed_policy()`, which returns `None`; the policy-required builder therefore denies before opening snapshot bytes. Do not weaken this. The owner must decide whether a bounded synthetic Principal is acceptable for local public-data validation or a production identity adapter is required. Any accepted adapter must be Principal-bound, scoped, expiring, fail-closed, and prove denial precedes source reads.
2. **Direct engine constructor:** a self-consistent package/hash is not proof of a successful policy decision. Prove direct `Simulation(..., governed_input=...)` cannot bypass the policy-built input boundary, or require a trusted capability that arbitrary callers cannot forge. Include a mutation proof.
3. **Provenance/report completeness:** verify manifest, projection, mapping, instances, original/projected scenario hashes and report/export fields agree. Keep append-once semantics and ensure `--force` cannot alter the envelope.

Claude must explicitly resolve each item or record a justified, owner-approved deferral before declaring the implementation milestone. A deferral cannot be used to claim an operator-usable governed workflow while the CLI still denies.

## 4. Documentation and validation gates

- [ ] `RUN_PROVENANCE_SPEC.md` accurately describes the implementation and all unresolved semantics.
- [ ] `M3_DESIGN.md` records the exact owner-approved engine path and current implementation, with no broader implied authorization.
- [ ] `OPERATOR_RUNBOOK.md` documents the CLI syntax and explicitly says it is blocked until policy identity is available; legacy `agora run` is not a substitute.
- [ ] `RUNG_STATUS.md`, `MILESTONE_OPERATOR_PILOT.md` and `MILESTONE_PILOT_READY.md` distinguish M2 reached from M3 unreached.
- [ ] `VALIDATION_PROTOCOL.md` remains clearly draft until owner approval. Freeze blockers include exact files/headers/licences, per-file privacy review, seeds/run counts, bootstrap parameters, independent evaluator/label custody, M5 reserve-file alignment and target-output compatibility.
- [ ] Dataset acquisition checklist records canonical sources, expected semantic fields, exact file/version/hash capture, licence terms and personal-data stop rules.
- [ ] A merged docs commit updates the assessment base and links this checklist; exact-head docs CI is green.

## 5. Owner decisions and external inputs

- [ ] Owner confirms whether a synthetic Principal is acceptable for local public-data validation or requires production identity.
- [ ] Owner supplies/approves the exact three benchmark packages and source terms; each file has a dataset-register row with source/version, licence/citation, access date, filename, bytes and SHA-256.
- [ ] Owner explicitly approves freezing a specific version/SHA of the validation protocol.
- [ ] Any simulation/validation run has separate explicit owner authorization naming scope, data, project and run purpose. M3 code merge is not run authorization.

## 6. Claude's final declaration requirements

Before declaring M3 reached, Claude's collaboration-log entry must:

1. State the exact main SHA assessed and link each merged PR/head SHA.
2. List exact-head CI run IDs and all four job conclusions for each required slice.
3. State test counts and mutation proofs with clear distinction between CI evidence and local-only claims.
4. Confirm only the owner-approved `agora/sim/engine.py` path was touched under `agora/sim/**`.
5. Confirm the policy identity/capability trust boundary is resolved or explicitly state why M3 is limited to implementation-only and not operator-usable; cite #178 for the now-implemented base/projected hash semantics.
6. Link merged docs and the validation-protocol status; no false claim that draft preregistration equals approved validation.
7. Confirm no dataset/simulation/validation run occurred without authorization and `VALIDATED_PREDICTION_ENABLED=False`.
8. Use the exact phrase **"M3 reached"** only if all required acceptance gates are satisfied; otherwise state **"M3 not yet reached"** and name the remaining blockers.

**No dataset was acquired, no simulation or validation was run, and no prediction-validity claim is made by this document.**


## 7. Dataset reachability update — 23 November 2026

Claude's 09:05 IST check reports GitHub reachable, while Harvard Dataverse, Kaggle and Ember's official host are blocked by the workspace allowlist. No data was downloaded. The acquisition checklist now records two third-party GitHub mirror candidates:
- MEDSL V20 county returns in `mathis-group/cas-201-data-project`, whose README records the same MD5 as Dataverse V20, 94,151 rows and CC0 1.0.
- Ember monthly CSV in `Awes0mer/fuel-cars-pollution`, whose manifest records the official Ember source URL, CC BY 4.0, 7,695,642 bytes and SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`; this is a 16-Nov snapshot, while the official Ember page now reports an 18-Nov update.

Both are third-party mirrors and require explicit owner approval of exact repository/commit/file/version before acquisition. M5 remains owner-supplied through Kaggle terms. No mirror was downloaded, imported or run by ChatGPT.
