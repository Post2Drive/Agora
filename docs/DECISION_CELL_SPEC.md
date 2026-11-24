# AGORA Decision Cell — Design Spec (DRAFT v0.2)

Status: DRAFT for ChatGPT review and owner approval. Docs only. Approves no code, no engine edit (`agora/sim/**`), no data, no feed, no run, no flag change. `VALIDATED_PREDICTION_ENABLED` stays False.

## 1. Purpose
When something new happens (breaking news, a viral video, a leak report, an incident), a named human in charge can bring it into a running or finished study and choose, with full information, how AGORA should respond. The system never acts on its own: it verifies, shows, runs what the human chooses, and records everything.

Non-goals: predicting that an event will occur; autonomous action; targeting or directing force; using private or leaked material as a source; any claim of validated prediction.

## 2. The loop
1. **Intake** — event items from feeds or typed by people. Each carries source, time received, time of event, and who submitted it.
2. **Verify** — dedupe; source trust score; label each statement CLAIM, REPORTED-BY-MULTIPLE, or CONFIRMED (definitions in section 2A). Unconfirmed items can raise a flag but cannot change a forecast without a human choice.
3. **Situation view** — plain words: known, unknown, changed since last view, which studies and segments are touched.
4. **Human choice** (section 3).
5. **Run** — the chosen path executes in the governed pipeline; every input is hash-linked.
6. **Result** — ranges by segment and branch, with the event and its confidence shown beside them.
7. **After-action** — later, predicted versus observed is recorded; hit and false-alarm rates are tracked per source and event type.

## 2A. Verification definitions
- **Source independence.** Two sources are independent only if neither cites, syndicates or copies the other and they do not share an owner or a single upstream origin (wire service, press release, one original post). Independence is judged per statement and recorded; if it cannot be established the sources count as one.
- **Minimum evidence.** REPORTED-BY-MULTIPLE needs at least two independent sources for the same statement. CONFIRMED needs either a primary source (the party itself, an official record, original footage with provenance) or at least two independent sources of which one is primary or has a published correction policy.
- **Event time.** Each item carries event-time (when it happened), received-time (when we got it) and an event-time uncertainty (exact, minutes, hours, day, unknown). An item with unknown event time cannot be injected at a specific round; the human must pick the round and that choice is logged.
- **Corrections and retractions.** A retraction or correction is a new item linked to the original. Anything run on a retracted item is stamped "based on retracted item" in every result and report; the human is shown which branches are affected and can fork without it.
- **Who may mark CONFIRMED.** Only the named approver for the project (or a delegate listed in the project record) may promote an item to CONFIRMED, with a reason text. The system may propose, never promote. Promotion and demotion are audit-logged.

## 3. Human options (shown to everyone with access; executable only if permitted, see 3A)
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

Timeout rule: if nobody responds within the project's response window, the system **holds the last human-approved result** and alerts the approver and a named backup. It publishes nothing new and changes no forecast. If no approved result exists, nothing is published and the item stays pending. The hold, the alert and the elapsed time are audit-logged.

## 3A. Permission, snapshot and budget matrix
Showing an option is not the same as being able to run it. An option is executable only when all three checks pass; otherwise it is displayed greyed with the failing reason and the attempt is logged.

| Option | Permission needed | Snapshot needed | Budget check |
|---|---|---|---|
| IGNORE, HOLD, COMPARE | project member | none | none |
| CONTINUE (inject) | approver | current-round snapshot | cost estimate vs budget |
| FORK FROM EVENT | approver | snapshot at event round | cost estimate x2 branches |
| FORK FROM ANY EARLIER ROUND | approver | snapshot for that round must exist and verify | cost estimate x2 branches |
| RERUN FROM START | approver | none (full rerun) | full-run cost; second confirmation above budget |
| CHANGE INPUTS | approver; sensitive inputs need the data owner's grant | as for the underlying run | as for the underlying run |
| ESCALATE | project member | none | none; blocks other options until the second approver answers |

Rules: no snapshot means the option is shown as unavailable, not silently replaced by a rerun. Budget exceedance requires an explicit confirmation by the approver, recorded with the amount. Permissions come from the Principal and policy path already in AGORA; nothing here widens them.

## 4. Data the human can use
Anything already approved and bound for the study: the study's own sources, the governed package, previous branches, and event items that passed section 2. New feeds and new datasets need separate named owner approval. Personal data stays excluded unless a consent review passes.

## 5. Engine requirement (needs separate owner approval to edit agora/sim/**)
- Per-round snapshot of agent state: opinions, memory, social links, random generator state, and the injected-event list.
- `fork_from(snapshot, event_set)` that resumes deterministically; same inputs and seed give the same result.
- Cost estimate before a run (rounds left times agents) shown to the human.
- Snapshots are hashed and listed in the run provenance record.
- **Immutable snapshot and deterministic replay, or refuse.** A snapshot is write-once and verified by hash before use. A fork resumes only if the replay check passes (same snapshot, same event set, same seed gives the same result hash on a short test replay). If the snapshot is missing, fails its hash, or replay is not deterministic, the system refuses the fork, logs the refusal with the reason, and offers only options that do not need it.

## 6. Governance
Default deny stays. Every choice, input and result is written to the audit log and linked to its source. Kill switch per study. Sensitive deployments (defence, security) are limited to decision support: situation awareness, scenario ranges, logistics impact. No targeting, no direction of force.

## 7. Validation (preregistered before any claim)
- **Stage A, event study on existing data.** Preregistered before any look at the outcome windows: (a) the dated event list, written from public record and reviewed by ChatGPT; (b) for each event, the expected direction of the move (up, down, none) and the affected segment, fixed and hashed before the comparison; (c) cutoffs: the baseline is the last state average on or before the event date, outcome windows are 7 and 14 days after, and no data after the window is used; (d) overlap rule: events whose 14-day windows overlap are grouped into one cluster and scored once, not counted separately; windows that contain a later listed event are flagged; (e) hit means observed move has the preregistered sign and exceeds the preregistered minimum size; the size threshold is fixed with the list. Report all hits, misses and losses. Uses data already approved; no new data.
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
2. Approve the `agora/sim/**` snapshot edit (design first, as done for M3). Not approved; nothing in this spec implies it.
3. Response windows and who the approvers are per project.
4. Hosting for live feeds.
