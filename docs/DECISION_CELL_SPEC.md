# AGORA Decision Cell — Design Spec (DRAFT v0.1)

Status: DRAFT for ChatGPT review and owner approval. Docs only. Approves no code, no engine edit (`agora/sim/**`), no data, no feed, no run, no flag change. `VALIDATED_PREDICTION_ENABLED` stays False.

## 1. Purpose
When something new happens (breaking news, a viral video, a leak report, an incident), a named human in charge can bring it into a running or finished study and choose, with full information, how AGORA should respond. The system never acts on its own: it verifies, shows, runs what the human chooses, and records everything.

Non-goals: predicting that an event will occur; autonomous action; targeting or directing force; using private or leaked material as a source; any claim of validated prediction.

## 2. The loop
1. **Intake** — event items from feeds or typed by people. Each carries source, time received, time of event, and who submitted it.
2. **Verify** — dedupe; source trust score; label each statement CLAIM, REPORTED-BY-MULTIPLE, or CONFIRMED. Unconfirmed items can raise a flag but cannot change a forecast without a human choice.
3. **Situation view** — plain words: known, unknown, changed since last view, which studies and segments are touched.
4. **Human choice** (section 3).
5. **Run** — the chosen path executes in the governed pipeline; every input is hash-linked.
6. **Result** — ranges by segment and branch, with the event and its confidence shown beside them.
7. **After-action** — later, predicted versus observed is recorded; hit and false-alarm rates are tracked per source and event type.

## 3. Human options (all always available to the person in charge)
| Option | What it does |
|---|---|
| IGNORE | Log the event, leave the study unchanged, record why. |
| HOLD | Defer with a re-check time; the forecast is stamped "unreviewed event pending". |
| CONTINUE (inject) | Keep agents' state; add the event at the next open round; finish the run. Fast. |
| FORK FROM EVENT | Copy the study at the event round; run branch A (with event) and branch B (without); compare. |
| FORK FROM ANY EARLIER ROUND | Same, from a chosen earlier snapshot, e.g. to test "what if we had responded sooner". |
| RERUN FROM START | Full rerun with the event present from its real timestamp; slowest, cleanest. |
| CHANGE INPUTS | Choose which evidence to include or exclude (per item, per source, per trust level) and rerun or fork with that set. |
| COMPARE | Side-by-side of any branches already run. |
| ESCALATE | Send to a second named approver before anything runs (for sensitive projects). |
Options can be combined (e.g. fork from event with a different evidence set). Each choice needs: the person's identity, a reason text, and the time budget. A choice that costs more than the budget asks for confirmation.

Timeout rule: if nobody responds within the project's response window, the system publishes the unchanged result with an "unreviewed event pending" flag. It never changes a forecast on its own.

## 4. Data the human can use
Anything already approved and bound for the study: the study's own sources, the governed package, previous branches, and event items that passed section 2. New feeds and new datasets need separate named owner approval. Personal data stays excluded unless a consent review passes.

## 5. Engine requirement (needs separate owner approval to edit agora/sim/**)
- Per-round snapshot of agent state: opinions, memory, social links, random generator state, and the injected-event list.
- `fork_from(snapshot, event_set)` that resumes deterministically; same inputs and seed give the same result.
- Cost estimate before a run (rounds left times agents) shown to the human.
- Snapshots are hashed and listed in the run provenance record.

## 6. Governance
Default deny stays. Every choice, input and result is written to the audit log and linked to its source. Kill switch per study. Sensitive deployments (defence, security) are limited to decision support: situation awareness, scenario ranges, logistics impact. No targeting, no direction of force.

## 7. Validation (preregistered before any claim)
- **Stage A, event study on existing data:** a dated event list (debates, FBI letter 2016, tape 2016, etc.) with expected direction fixed before looking; compare injected-event response with the observed move in the daily state averages in the following 7 and 14 days. Report hits and misses, including losses. Uses data already approved; the event list is written from public record and reviewed by ChatGPT.
- **Stage B, replay:** archived news streams replayed in time order with no look-ahead; measure alert hit rate, false-alarm rate, time to alert.
- **Stage C, confirmatory:** a held-out cycle (2020 planned) under a new protocol with the owner's freeze sentence.
Any tie or loss is a valid result.

## 8. Staging
1. Spec and human-option workflow with typed events (no feeds), existing inject plus compare.
2. Engine snapshots and fork-from-event (owner approves engine edit first).
3. Feed adapters on the owner's hosting (e.g. Railway), source scoring, alerts to the person in charge.
4. Customer deployment: security review and an agreement on what the system may and may not do.

## 9. Open decisions for the owner
1. First client type to design for: company, political or defence (Claude recommends company).
2. Approve the `agora/sim/**` snapshot edit (design first, as done for M3).
3. Response windows and who the approvers are per project.
4. Hosting for live feeds.
