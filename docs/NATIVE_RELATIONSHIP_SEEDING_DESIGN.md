# Seeding native relationships from ontology links: design

Status: design only, nothing built. Extends `docs/NATIVE_SOCIAL_INTERACTION_DESIGN.md`. Owner decision (answered): seed starting relationships from ontology links.

## 1. Why this is needed

Crowd people start a native run with no relationships. With `contact: relationship` (the default for new projects), a scenario that has no groups or communities produces no crowd word of mouth at all (measured: 0 contacts, against about 2,700 under `open`; `agora check` now warns). Seeding gives the gate something to work with, from information the user already holds.

## 2. What exists today

- Ontology links (`agora/ontology/store.py`, table `ontology_links`): typed (`link_type_id`, version, predicate, cardinality), between two records identified by `(import_id, record_key)`, immutable, supersedable, retractable by a separate append-only row.
- Engine relationships (`agora/society/store.py`): directed edges with trust and familiarity in [0, 1] and an append-only change log (cause message and reason). The contact model reads them.
- Governed runs verify an input package against a declared mapping and receipt, and the engine refuses native communication for them.

## 3. The central problem: records are not agents

Ontology records are real entities (a customer, a household, a dealer). Crowd people in a run are synthetic: they stand for a segment, not for one record. A link between two records can become a relationship between two agents only if some agent stands for each record. Two honest options:

1. **Named agents.** Records mapped to scenario accounts or LLM-driven people (`record -> agent` map in the project). Each link between two mapped records becomes a seeded edge. Exact, but covers only the few agents that stand for real records.
2. **Segment tie density.** Links are counted by the segment of each record's mapped segment. The count gives a tie density between segments (for example, 30% of Segment A people have a tie to someone in Segment B). The engine then draws seeded edges among crowd people with the run's seed. Covers the crowd, but the edges are synthetic: they show how connected the segments are, not who knows whom.

Recommendation: build option 1 first, because it never invents an edge, then option 2, labelled as synthetic in every output.

## 4. Declared mapping (no guessing)

A project file `relationship_seed.yaml` declares, and nothing is inferred:

- which `link_type_id` values count (an explicit list);
- for each, direction (`both` or `source_to_target`), starting trust, starting familiarity (each 0 to 1);
- the `record -> agent` map (option 1) or the `record -> segment` map (option 2);
- the ontology pack fingerprint and the import it reads, so the seed is tied to exact data.

A link that is retracted or superseded at read time is skipped. A link whose records are not in the map is skipped and counted in a visible "not mapped" total.

## 5. How it is recorded

- Each seeded edge is written through `adjust_relationship` as a change with no causing message and the reason `seed: link <link_id> <link_type_id> v<version>`, so the change log shows where every starting edge came from and the store digest covers it.
- The seed file's hash, the pack fingerprint and the counts (links read, seeded, skipped, not mapped) are stored with the run and included in the scenario hash, so a changed seed is a different run.
- A resumed run does not re-seed.

## 6. Governed runs and privacy

- Governed runs still refuse native. Seeding does not change that; a governed-native design is a separate decision.
- Links between real people are personal data. The seed file holds record keys, not names. The society report shows agent IDs or labels only and never prints link IDs or record keys unless a caller passes an explicit option, in line with the report's rule for text and reasons.
- The ontology store is read only. Seeding never writes links.

## 7. Phases and tests

1. Parse and validate `relationship_seed.yaml` (unknown link types, out-of-range values, unmapped records, duplicate agents).
2. Read links from the ontology store, skipping retracted and superseded ones, into a deterministic list.
3. Option 1: apply to named agents, record changes, store the seed provenance.
4. Option 2: segment tie density, seeded draws from the run seed, labelled synthetic.
5. Report: a seeded-edges section with counts.

Tests for each phase, with mutation checks on: the retraction and supersession filter, direction handling, range checks, unmapped counting, resume not re-seeding, and the digest covering seeded edges.

## 8. Not covered

Real effects of seeded ties on outcomes are not measured here. Whether seeded ties improve any prediction is untested, and nothing in this design claims it. Trust levels are declared by the user, not learned.

## 9. Open questions for the owner

- Is option 1 (named agents) enough to start, or is the crowd the point?
- Starting trust and familiarity per link type: who sets them (the user in the file, or product defaults)?
- Should seeding be allowed only when the ontology import is anchored (verified), or for any import?
