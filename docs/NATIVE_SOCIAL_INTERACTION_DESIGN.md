# Native Social Interaction Engine — design (draft v0.1)

Status: design, with phase 1 implemented (below). Direction set by the owner on 26 Nov 2026. The engine does not use the native store yet, so no run's behaviour has changed.

**Implemented:** phase 1, `agora/society/store.py` (`SocietyStore`): conversations of four kinds, memberships with roles, an append-only message log that records the reason for every message, per-agent inboxes with read cursors, directed relationships with an append-only change log tied to the causing message, and a deterministic `digest()` over all state. Tests: `tests/test_society_store.py`, mutation-verified. **Implemented, phase 2 (direct messaging path):** scenario option `communication: platform | native | both` (default `platform`, which leaves every run byte-for-byte unchanged and creates no native tables). In `native` and `both`, an LLM agent's private message is delivered through the store with no simulated app; in `both` it is also posted on a shared platform when one exists. Native tables live inside the run database, so state digests, snapshots and forks cover them with no extra code, and they commit with the round. A message sent in round N reaches the recipient's decision prompt in round N+1 (section "Private messages to you") and raises both parties' familiarity, with the message recorded as the cause. Governed runs refuse native communication until their evidence design covers it. Tests: `tests/test_native_communication.py`, mutation-verified.

**Not implemented:** groups, open discussions and broadcasts in the engine (phase 3); scored initiation and permission matrix (phase 4); trust effects from message content (phase 4); crowd agents sending or receiving messages that change their state; platform adapters (phase 5); reports (phase 6). In phase 2 only LLM-driven agents read and send native messages.

## 1. Problem

Today an agent can only message another agent through a simulated platform. In `agora/sim/engine.py`, `Simulation._dm` returns nothing unless the two agents share a platform whose registry entry has `dms`, and the message is stored as a platform post in a `dm_space`. Groups and public discussion likewise exist only as platform features. Consequences:

- Two agents with no shared platform cannot communicate, which is wrong for a real society (neighbours, colleagues, family).
- Platform rules (length limits, feed ranking, availability) shape conversations that, in the real world, happen face to face, by phone, or in channels the study does not model.
- Information spread is confounded with platform choice. A study of a decision (for example a pricing change) cannot separate "word of mouth" from "the WhatsApp model".

## 2. Principle

Direct agent-to-agent communication is a core AGORA capability. Simulated platforms (WhatsApp, Instagram, Reddit, Telegram, LinkedIn, X/Threads, YouTube/TikTok, Facebook Groups) are optional environments layered on top. An agent never needs a platform account to talk to another agent.

## 3. Native model

Each agent has, inside AGORA and independent of platforms:

| Element | Meaning |
| --- | --- |
| Native identity | Stable agent ID and handle; the existing `Agent` record. |
| Inbox | Ordered, per-agent queue of delivered messages with read/unread and delivery round. |
| Relationships | Directed edges with trust, familiarity, influence-of-sender and last-contact round. |
| Group memberships | Membership in native groups with a role (member, moderator, owner). |
| Conversation history | Per-pair and per-group threads, each message with author, round, text, and the reason it was sent. |
| Communication permissions | Who may contact whom, per scenario (open, relationship-gated, group-only, blocked). |

Conversation kinds:

1. Direct (private, two agents).
2. Group (closed membership, persistent thread).
3. Open discussion (public thread attached to an event, news item, or decision).
4. Broadcast channel (one-to-many, replies optional).

A platform is a *channel adapter*: it maps a native conversation onto platform-specific constraints (length, visibility, feed ranking, availability) and may add platform-only behaviour (likes, reposts). A conversation may exist natively with no adapter. When an adapter is used, the native conversation is the source of truth and the platform post is a rendering of it.

## 4. Who initiates and whom

Agents initiate conversations on their own turn; nothing waits for operator instruction. Choosing a counterpart is a scored decision, not random:

`score(a→b) = w_trust·trust + w_rel·familiarity + w_int·topic_interest_overlap + w_inf·influence(b) + w_mem·memory_salience(b) + w_open·openness(a)`

with weights set in the scenario and recorded in the run configuration. Candidates are limited to permitted contacts. LLM agents may override by naming a handle, subject to permissions; crowd agents use the score only. All draws use the existing RNG derivation from (seed, round, agent) so runs stay reproducible.

## 5. Effects

A delivered message can change, and must record when it does:

- Opinion/stance (through the existing opinion model, weighted by trust, influence and the recipient's stubbornness and openness).
- Relationship edges (trust and familiarity move; direction and size recorded).
- Memory (salient exchanges enter the recipient's memory with a pointer to the thread message).
- Actions (a conversation can lead to a decision, a choice, a share, or a new conversation).

Information spread is therefore an observable consequence of who talked to whom through which relationships, not a property of a platform.

## 6. Observability and audit

For every message AGORA records: conversation ID and kind, sender, recipients, round, text, the decision rationale for initiating (the score components or the LLM's stated reason), and each resulting change (stance delta, relationship delta, memory entry, follow-up action) with its cause. Reports can answer: who communicated, what changed, why, and what followed. In governed runs the records are part of the run's evidence and follow the existing audit and sealing rules. No raw conversation text is exported without the same sensitivity policy that applies to other agent output.

## 7. Compatibility and migration

- Existing platform simulations keep working. Platform DMs and posts continue to be produced by adapters; a scenario flag selects `native`, `platform` or `both`. Default for existing scenarios stays `platform` so published results do not change.
- Snapshot/fork digests (`take_snapshot`, `fork_from`) must cover native state (inbox, threads, relationships, memberships). Digest schema version increases; older snapshots remain loadable but are marked as lacking native state.
- Replay determinism (`replay_is_deterministic`) must hold for native conversations under the mock backend.
- Performance: crowd agents use batch scoring with a per-round contact budget; LLM-agent conversations count against the existing call budget.

## 8. Phased delivery

1. **Native data model and store (no behaviour change). Implemented.** Tables for conversations, messages, memberships, relationships, with digests and tests. Engine untouched except snapshot coverage hooks.
2. **Direct messaging path. Implemented.** `_dm` delivers natively when no platform is shared or when the scenario is `native`; inbox read path for agents; effects on relationships and memory; mutation-tested.
3. **Groups and open discussions.** Group lifecycle, membership permissions, public threads tied to events.
4. **Initiation policy.** Scored counterpart choice, contact budgets, permission matrix.
5. **Adapters.** Map native conversations to platform renderings; remove platform-only gating from direct paths.
6. **Evidence and reports.** "Who/what/why/follow-up" report from the recorded changes; sensitivity-aware export.

## 9. Claims boundary

This capability makes AGORA's simulated society more complete and its information flow inspectable. It does not by itself improve predictive accuracy. `VALIDATED_PREDICTION_ENABLED` remains false, and any accuracy claim needs separate evidence under the existing preregistration rules.

## 10. Open decisions for the owner

1. Is `native` the default for *new* scenarios while existing ones stay `platform`? (Recommended: yes.)
2. Should relationship edges be seeded from imported data (ontology links) when a project has them? (Recommended: yes, as an optional input.)
3. Contact permission default: relationship-gated (recommended) or open.
