# Decision cell executor: design note (FORK_FROM_EVENT, FORK_FROM_EARLIER, CONTINUE, RERUN_FROM_START and a narrow CHANGE_INPUTS)

Status: library only, 28 Nov 2026. Decided by the Claude session that wrote it, under the owner's instruction of 26 Nov 2026; not independently reviewed. Mock backend only: nothing it produces is a forecast. `VALIDATED_PREDICTION_ENABLED` stays False.

Why: `record_run_result` records what a result rests on only if its caller remembers to call it. The executor makes the gate, the run and the record one call, `execute_event_fork`, and releases output only after the record exists.

## Decisions

| Question | Decision | Reason |
|---|---|---|
| Which option first? | FORK_FROM_EVENT; CONTINUE, RERUN_FROM_START, FORK_FROM_EARLIER and CHANGE_INPUTS over FORK_FROM_EVENT followed (sections below). All other options are refused before the gate. | The spec's with-and-without comparison, using the existing verified `Simulation.fork_from`. |
| What is added to branch A? | Every listed statement of the item, in its recorded wording, as `news` in the round after the event round, with no opinion shift. The caller chooses nothing. | The gate checks the wording against the recorded list and hashes the labels into the action fingerprint, so a second approval covers what runs. A caller-supplied event or shift would not be covered by either. Only CHANGE_INPUTS may leave one out. |
| Who works out cost and snapshot status? | The executor, from the source project. The snapshot probe is a real fork into a throwaway directory. | A caller cannot understate the budget or assert that a snapshot verifies. |
| How is the without-event branch recorded? | It is not recorded on its own. The two branches are one result, the comparison, whose hash covers both final states. | The comparison rests on the item, so stamping it is correct. A stamp on the baseline alone would be false, so the baseline is not offered as a result. |
| What if the run succeeds and recording fails? | No output is released. Branches are built in a staging directory that moves to its final place only after the record is written and the stamps are read. | An unrecorded result could never be stamped. |
| What if recording succeeds and a later step fails? | The record stays, the output is removed and the result id is spent. | A record without output misleads nobody; output without a record could. This includes a record committed but not anchored. |
| Kill switch | Polled before the gate, before every round and before recording; only exactly `False` continues. | Fail closed. |
| Reading | `read_event_fork` returns the comparison and its current stamps together, and refuses an unrecorded result, a changed manifest or a changed branch database (including changes still in the write-ahead log). | A later retraction reaches whoever reads the result through this call. |

## CONTINUE (`execute_continuation`, `read_continuation`)

The same gate, staging, record-before-release and kill-switch rules apply. What differs:

| Question | Decision | Reason |
|---|---|---|
| Is the study changed in place? | No. The snapshot at the last committed round is restored into a new project, which gets the statements and runs to the end. | The spec says to keep the agents' state and to leave source runs untouched. A restore does both, and a failed or stopped continuation leaves nothing half-written in the source. |
| Where does the item go? | The round after the last committed one. A request that names an event round is refused. | CONTINUE adds at the next open round. An unused event round would still enter the action fingerprint that a second approval covers. |
| What does the result rest on? | The item, any extra basis items and any named parent results, as for a fork. | The one branch contains the statements, so a retraction stamps it. |
| Is there a baseline? | No. | One branch cannot show what difference the item made, and the manifest holds no comparison. Use FORK_FROM_EVENT for that. |
| What does it cost? | Remaining rounds times agents, once. `fork_branch_cost(source, last_round)` gives the figure to show. | The spec prices a continuation as one branch. |
| Are the two kinds interchangeable? | No. Each has its own manifest schema and read call; reading one as the other is refused (`WRONG_RESULT_KIND`). A result id is used once across both. | A reader must not mistake a single run for a comparison. |

A continuation needs a snapshot at the last committed round (the run must have been started with that round in `snapshot_rounds`); without it the gate blocks, and nothing is rerun in its place. A finished study has no round left. Nothing marks the source as continued, so it can be continued again under another result id; choosing which result is the study's current one is not built.

## RERUN_FROM_START (`execute_rerun`, `read_rerun`, `rerun_cost`)

The same gate, staging, record-before-release and kill-switch rules apply. What differs:

| Question | Decision | Reason |
|---|---|---|
| What is taken from the source? | The scenario file (with its seed) and the knowledge graph file if there is one. No agent state, round, reply cache or snapshot. | The spec calls this a full rerun. Copying state would make it a continuation under another name. |
| How is the scenario bound? | Its hash must equal the one the source recorded when first prepared, checked before the gate. The new project's own hash must equal it too, before it runs. | Otherwise a later edit to the file would be reported as the effect of the event. The second check judges the copy that runs. |
| Where does the item go? | `request.event_round` is the round the person picks. As for a fork, the statements are added in the round after it. It may not be later than the last committed round. | One meaning for "event round" across options, and the value is already in the action fingerprint a second approval covers. The system has no recorded event time to work it out from. |
| What if the source has added events? | Refused (`SOURCE_HAS_ADDED_EVENTS`), whatever their round. | A fresh project would drop them. Carrying them over would bring in events whose basis items are not known here. |
| What about a governed source? | Refused (`SOURCE_GOVERNED`). | The new project would carry no input provenance. Same line as `fork_from`. |
| What if the scenario names a live model? | Refused before the gate (`BACKEND_NOT_DETERMINISTIC`). | This executor runs the mock backend only. |
| Is there a baseline? | No. The manifest holds one branch. | A rerun makes no comparison. |
| What does it cost? | All scenario rounds times agents, once, wherever the event is. `rerun_cost(source)` gives the figure to show. Over budget, the gate needs the exact amount confirmed. | The spec prices it as the full run. |

On the mock backend, a rerun and the with-event branch of a fork at the same event round end in the same state digest, and a test holds this. It checks that the two paths agree for that test scenario with no knowledge graph; it says nothing about a live model, other scenarios or whether either run is right.

The knowledge graph is copied as it is now. Nothing records what it was when the source started, so a rerun can differ from the source for that reason alone; the manifest holds the copy's hash (`graph_sha256`). A rerun also uses the engine code as it is now, which need not be the code that ran the source, and the source's own model backend is not read. The item cannot be placed in the first round. Nothing compares a rerun with its source.

## FORK_FROM_EARLIER (`execute_earlier_fork`, `read_earlier_fork`)

The same gate, two-branch comparison, staging, record-before-release and kill-switch rules as FORK_FROM_EVENT apply. What differs:

| Question | Decision | Reason |
|---|---|---|
| Where do the branches start? | Both from the verified snapshot at `request.from_round`, which the gate requires to be earlier than `request.event_round`. No snapshot there means blocked; nothing is rerun or taken from a nearer round. | The spec: same as a fork from the event, from a chosen earlier snapshot. |
| In which round are the statements added? | The round after `from_round`, so the item arrives earlier than it did. | The spec's example is "what if we had responded sooner". Adding them after the event round instead would, on a deterministic backend, only repeat FORK_FROM_EVENT at a higher cost. |
| How is that shown? | The manifest has `event_placement: hypothetical-earlier` with `event_round`, `forked_from_round` and `added_in_round`. It has its own schema and read call (`WRONG_RESULT_KIND` otherwise). | A reader must not take a moved item for the event as it happened. |
| What does the without-event branch mean? | The study continued from `from_round` with the item never added. It is one half of the comparison, not a result of its own. | Same rule as FORK_FROM_EVENT. |
| Which event round is accepted? | One the study has reached (`EVENT_ROUND_NOT_REACHED` otherwise). | "Earlier than the event" needs the event to have a round in the study. The system has no recorded event time, so this is the person's choice, as for a rerun. |
| What if the source has events added after `from_round`? | Refused (`SOURCE_HAS_LATER_EVENTS`), including ones before the event round. | A fork from `from_round` would drop them from both branches. |
| What does it cost? | Rounds after `from_round` times agents, twice. `fork_branch_cost(source, from_round)` gives one branch. | The spec prices a fork as two branches. |

Only the item's arrival moves. Nothing models a different response by anyone, and the statements keep their recorded wording even where it would not have made sense at the earlier time. Scenario events stay in their own rounds in both branches, so if the scenario already scripts the same news at the event round, the with-event branch holds it twice. On the mock backend an earlier fork's branches are the same as those of a FORK_FROM_EVENT whose event round is `from_round` (a test holds this for one test scenario); the two kinds differ in what the record says they are.

## CHANGE_INPUTS over FORK_FROM_EVENT (`execute_changed_inputs_fork`, `read_changed_inputs_fork`)

The smallest case: the person chooses some, not all, of one item's recorded statements, and the fork from the event runs with those. The gate, comparison, staging, record-before-release and kill-switch rules are those of FORK_FROM_EVENT. What differs:

| Question | Decision | Reason |
|---|---|---|
| How is the chosen set bound to what the gate fingerprints? | Each `InputRef.input_id` is `statement_input_id(item_id, statement_id)`: the text `statement:` followed by the JSON list of the two ids. The gate already hashes the inputs (id, sensitivity, data owner) and the underlying option into the action fingerprint, and the evidence hash covers every statement's evidence. | No gate change is needed, and a second approval covers one exact choice. |
| Why does the id name the item? | A data owner's `InputGrant` names the project, study, input id and person, but no item. Statement ids are only unique within an item. | With a bare statement id, a grant for one item's `st1` would also open another item's `st1`. |
| What must be given as `statements`? | The item's whole recorded list, as on every labelled path. | Leaving a statement out is a recorded choice in the request, not a shorter list. |
| Which choices are refused? | An id that is not one of this item's statements (`INPUT_NOT_A_STATEMENT`) and a choice of all of them (`NOTHING_LEFT_OUT`), both before the gate. The gate blocks an empty choice and a repeated id. | Extra inputs would be fingerprinted but never reach the run. With nothing left out the result is a plain fork under another name. |
| Can the item be left out entirely? | No: an empty choice is blocked. The item is always in the basis (`record_run_result` adds the gate's item). | A retraction stamps the result whatever was left out. This can stamp a result that did not use the retracted wording; it does not clear one that did. |
| How do sensitive-input grants apply? | As the gate already does: each chosen input rated `personal` or higher needs its data owner's grant to the person. A statement left out needs none, because it does not enter the run. | The spec: sensitive inputs need the data owner's grant. |
| Which underlying run? | FORK_FROM_EVENT only (`OPTION_NOT_EXECUTABLE` otherwise). | Smallest case first. |
| What is in the manifest? | Its own schema and read call; `underlying_option`, `included_statement_ids`, `excluded_statement_ids`. `statement_labels` covers the whole view the person decided on; `primary_source_exception_ids` lists only added statements. | A reader must see what was left out. A statement that was not added is not relied on. |
| What is compared? | The chosen statements against no item. Not against the full item: for that, run a FORK_FROM_EVENT too. | Same two-branch meaning as the underlying run. |

The choice covers this item's statements only. Everything else the study already reads (scenario events, population, knowledge graph) is the same in both branches. Choosing evidence by source or by trust level, across items, or over another underlying run is not built.

The sensitivity gap first noted here is closed by the next section.

## Recorded sensitivity and data owner of each statement

Before this, nothing recorded how sensitive a statement was or whose data it was. The grant check ran only for CHANGE_INPUTS, on values in the request, so a plain fork, continuation or rerun could add a sensitive statement with no grant.

| Question | Decision | Reason |
|---|---|---|
| Where is it recorded? | In the item's statement list, in the same anchored audit event. `register_item_statements` requires a `StatementRating` (sensitivity, data owner) for every statement. `personal` and `sensitive` need a data owner. | One record, one version number, so the gate's existing "the list changed" commit check also covers a rating change. |
| Which choices are checked? | Every run option, for every listed statement (all of them are added). CHANGE_INPUTS, for each chosen statement. IGNORE, HOLD, COMPARE and ESCALATE add nothing and need no grant. | The grant is about what enters a run. |
| Whose values are used? | The recorded ones, read by `request_labelled_option`. No caller of that path or of `request_project_option` can supply them. A CHANGE_INPUTS input that names one of the item's statements with another sensitivity or owner is blocked (`input_rating_mismatch`). | A person must not under-rate their way past the check. The action fingerprint hashes the request's inputs, so they must be true. |
| Lists recorded before ratings | Every run option that would add an unrated statement is blocked (`statement_unrated`). A later version of the list rates them. | Fail closed: unknown sensitivity is not low sensitivity. |
| May a later version change a rating? | It may raise one, or name an owner where none was recorded. It may not lower one or replace a recorded owner. A version that only raises ratings is allowed. | Lowering or replacing would let a re-registration remove the need for a grant. A rating set too low must stay fixable. |
| How does a grant name a statement? | `InputGrant.input_id` is `statement_input_id(item_id, statement_id)` for every option. | One grant means the same statement whichever option runs, and never another item's. |
| Does a rating change lapse a second approval? | Yes: ratings are part of the evidence hash, which is in the action fingerprint. A list with no ratings keeps its old hash. | The approver approved a view with those ratings. |

A wrong rating that is too high, or a wrong owner, cannot be undone under this item: register the content as a new item, or build an owner-transfer operation with its own authorisation (not built). Ratings are as good as the trusted service that registers them; nothing checks them against the content. The check is made when the gate runs: a rating raised while a run is in progress does not stop that run. What the source study already holds is covered by the next section. The read calls still perform no permission check.

## Statements a source study already holds

A run started from a snapshot carries every event added up to that round. Before this, nobody was asked for a grant for them, so a person without one could build on a run that already held a personal statement. This applies to fork from the event, fork from earlier, continuation and changed inputs. A rerun carries nothing: it already refuses a source with added events.

| Question | Decision | Reason |
|---|---|---|
| Which events are judged? | Those in a throwaway restore of the snapshot, up to the start round. The snapshot only verifies if a second restore carries the same ones, and each branch is compared again before it runs. | The snapshot, not the live source database, is what goes into the run. |
| How is an event traced to a statement? | It must be exactly what a run here adds (`type` news, `text`, `round`), with the recorded wording of a statement of an item in the basis of a named parent result. | The source records event text, not statement ids. Requiring a named parent also keeps a later retraction of that item on the new result. |
| What if one cannot be traced? | The run is refused before the gate (`SOURCE_EVENT_UNTRACED`). This includes events a person added to a project directly. | Unknown sensitivity is not low sensitivity. |
| What if several statements have the same wording? | Every one recorded in the study is judged, whether or not a parent rests on its item. | The text cannot tell them apart. Otherwise naming a parent whose item rates the words lower would remove the grant. This can ask for more grants than necessary. |
| Which ratings apply? | The ones in force now. A statement recorded unrated blocks the run. | A rating raised after the source ran is a correction that later runs must respect. |
| Is it bound to approval and commit? | The held input ids and ratings are in the action fingerprint and the gate's audit entry (`held:<input id>`). Any statement list recorded or changed in the study between the read and the commit stops the entry (`STATEMENTS_CHANGED`). An action with nothing held keeps its old fingerprint. | A second approval must lapse when what it covered changes. |
| Does the result say so? | The manifest lists `held_statement_ids` when there are any. | A reader should see what was carried in. |

Limits. Only added events are traced: data that reached a source through its scenario, population or knowledge graph is not seen. Which result a source came from is covered by the next section. Held statements get no verification labels or primary-source exception flags in the new result. `request_labelled_option` checks held statements only when it is given them; the executor always does. Someone who can rewrite a source's snapshot and its recorded digests can remove an event from both; for a source with added events the rewritten digest would then no longer be one a parent recorded.

## Which result a source came from

Before this, a caller could name any parent that rested on the item whose wording an added event matched. The lineage, and with it the retraction stamps, rested on the service's word. Executed results also kept no snapshot, so none of them could in fact be forked again.

| Question | Decision | Reason |
|---|---|---|
| What is compared? | The digest of the snapshot being restored, against the snapshot digests a named parent's manifest lists for its branches, at the same round. The manifest's bytes must hash to the `result_hash` in the anchored record. | The snapshot is what goes into the run. Its digest covers the state (added events included), reply cache, graph, scenario hash, seed, engine and model identity. |
| Why not compare the source database with the parent's final state digest (the first suggestion)? | A fork starts from a snapshot of an earlier round, and a finished result has no round left. The final state says nothing about that snapshot. | A check on the live database would not judge what runs. |
| How can a result be built on, then? | `keep_snapshots` on each execute call names rounds of the output branches to snapshot. For a fork or continuation each is after the start round; each is before the last round. The digests go in `branches.<name>.snapshots`. None by default. | Keeping a snapshot changes no state (a test compares digests), costs disk, and is only useful if someone will build on it. The gate does not price the disk. |
| When is the check required? | When the start snapshot carries added events. A parent that qualifies must be among `parent_result_ids`, or the run is refused before the gate (`SOURCE_NOT_PARENT_OUTPUT`). | Those events are what a retraction must follow. |
| Which parents trace the held events? | Only the ones that recorded the snapshot. Their basis already includes their own parents' items. | A bystander that merely rests on the item added nothing to this source. |
| Where are parent manifests read? | Under the same `out_dir` as the new result. A missing, changed or unreadable one does not count. | One results directory per service; fail closed. |
| What is rechecked? | The gate's snapshot probe and every branch must report the same snapshot digest as the first read. | A snapshot swapped between the check and the run is not run. |
| What does the new result say? | `source_produced_by` lists each qualifying parent and branch, next to `held_statement_ids`. | A reader can follow the chain. |

**Behaviour change:** a source holding added events that no executed result kept as a snapshot can no longer be run from, whatever parents are named. That includes events a service wrote into a study itself, and every result executed before this change.

Limits. The match is of snapshot content, not of a directory: a copy of a parent's branch counts, and so would an identical snapshot built another way. A source with no added events can still be a result's output (a without-event branch, say), and then only the caller can say so. A result recorded by calling `record_run_result` directly is as trustworthy as that caller. A parent's current retraction stamps do not block the run; they carry over to the new result. Snapshots are tied to the exact Agora code, Python and library versions, so after any upgrade a kept snapshot can no longer be restored and the gate blocks the run (`snapshot_unavailable`).

## Limits

- `source`, `out_dir`, the study state, the kill-switch probe, statement sources and judgments, and any extra basis items or parent results are trusted service inputs. Nothing proves that `source` is the project of that study.
- If `source` was itself produced from a recorded result, the service must name it as a parent, or retractions behind it are not carried over. This is checked only for a source whose start snapshot carries added events.
- A process that dies mid-run leaves a `.executing` directory that blocks that result id until an operator removes it.
- The read check covers the manifest and the branch databases, not the reply caches or other files. Someone who can write the output directory can still copy files from it without using this call, and so without stamps.
- Reads perform no permission check. There is no service boundary, command, screen or report; adding a network service needs a separate security review.

## Not built

CHANGE_INPUTS beyond the case above; data-owner transfer or rating correction downwards; a segment-level comparison view; live model backends; governed or signed-receipt runs (`fork_from` refuses governed sources).
