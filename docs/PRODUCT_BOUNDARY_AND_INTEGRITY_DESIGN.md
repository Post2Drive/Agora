# Product boundary and integrity design (draft)

**Status:** Draft for ChatGPT review and owner decision. Design only: nothing here is built, no source file is changed, and every new module named below needs a separate exact-path owner approval. `VALIDATED_PREDICTION_ENABLED` stays `False`. This document makes no security claim about what exists today.

**Owner direction (24 Nov 2026):** AGORA is sold as software or a service, not as a customisable repository. Customers use it; they do not change it. Only the owners (and, later, the commercial entity) can change the core. Delivery starts hosted by us. The interim in-engine label is PR #216; signed receipts and signed releases are the chosen next steps.

## 1. Goal and threat model

**Goal:** a paying customer, including their administrators, can configure and operate AGORA but cannot forge an authorization, alter the engine's behaviour, or present a result as coming from a verified release when it did not.

**Adversary:** a customer insider or customer IT team with legitimate access to the product's configuration surface and, in an on-premises case, to the machine it runs on.

**Out of scope for this draft:** compromise of our own key custody or build pipeline, physical attacks on our infrastructure, nation-state adversaries, and a customer who owns the machine reverse-engineering a build we handed them. These are listed in section 9 as residual risk, not solved.

## 2. Product boundary

| Ours (closed, signed, owner-run) | Theirs (configurable, validated) |
|---|---|
| Simulation engine, projection, readouts | Data connections (read-only, approved) |
| Policy and receipt service | Ontology packs and bindings (schema-checked) |
| Principal and identity adapters | Scenarios, populations, decision options |
| Validation harness and its frozen protocols | Who may approve what (within policy ceilings) |
| Release signing and run stamping | Reports, dashboards, notification routes |
| Audit chain and provenance store | Tenant users and roles (inside our identity layer) |

Rules: no customer code runs inside the engine process (no plugins, scripts or user-supplied callables); configuration can only narrow what policy allows, never widen it; extension happens through declared, versioned, schema-validated APIs; new connectors are built by us, not by the customer.

## 3. Signed authorization receipts (proposed)

**Problem today:** receipts are checked by in-process sentinels that any same-process caller can import (documented in `M3_DESIGN.md`; PR #216 adds only a provenance label).

**Proposal:** a policy service we operate decides allow or deny and signs the receipt with an asymmetric key (for example Ed25519) whose private half never leaves our key management. The engine holds only public keys.

Receipt content (bound by the signature): tenant, subject, project, import id, binding id, manifest hash, scenario hash, purpose, issuing release or service id, key id, issued-at, expires-at, nonce. The engine verifies signature, key id against a signed key list, expiry, exact scope match, and nonce replay before any projection or write. Any failure refuses and writes nothing (the existing refusal contract).

Key handling to decide: custody (cloud KMS versus HSM), rotation interval, revocation list distribution, clock source, nonce store. The synthetic fixture issuer stays test-only and must not appear in a production trust list.

**What it stops:** minting a receipt without our key. **What it does not stop:** a customer with code execution on the engine host patching the verifier (see sections 4 and 9).

## 4. Signed releases and run stamping (proposed)

- The build pipeline produces an immutable artifact (wheel or container digest) and a signed manifest of its file hashes. Signing tool and transparency log are open choices.
- On start, the engine hashes its own files against the signed manifest and records `release_id` and `integrity: verified|unverified` in every run's provenance and reports. A modified engine can still run but is labelled unverified, and the policy service can refuse to issue receipts to unverified releases.
- Hosted deployment pulls by digest only; images are immutable; customers have no shell or file access.

**What it gives:** detection and evidence. **What it cannot give:** physical prevention on a machine the customer controls.

## 5. Hosted deployment (first delivery model)

- One engine fleet we run; per-tenant data stores and keys; tenant id in every receipt and audit record.
- Egress control: engines can reach only approved read-only sources; no write-back in the first release.
- Customers interact only through the API and console. Operations (deploys, key use, support access) are logged in the existing audit chain.
- Unknowns: hosting provider and cost, regional data residency (India, UK), isolation model (shared fleet versus dedicated), backup and restore, incident response. None are decided here.

## 6. On-premises or air-gapped customers (later)

A signed build that we install, update and attest ourselves, with the policy service reachable or replaced by a customer-isolated instance we operate. Residual risk: the customer holds the machine. Mitigations are contractual (licence, audit right), detective (section 4) and operational (we control update and receipt issuance). Not planned before the hosted release.

## 7. What a buyer can and cannot do (target state)

| Action | Hosted | On-prem signed build |
|---|---|---|
| Configure data, ontology, scenarios, options | Yes | Yes |
| Mint or alter an authorization receipt | No | No (without our key) |
| Change engine code and have it accepted as verified | No | Detectable, labelled unverified |
| Run engine code of their own inside our process | No | Not supported; breach of licence |
| Read our source | No | No |

## 8. Phased plan (each phase needs owner approval and its own PR)

0. **Done:** PR #216 origin label and refusal of undeclared hand-built packages (a label, not a boundary).
1. Receipt format and a local verifying stub with test keys; engine verification path; forged-receipt negative tests with mutation proofs. New module paths required.
2. Policy service with key custody on synthetic data only.
3. Release signing, self-check, run stamping; unverified-release refusal rule.
4. API and console boundary; configuration schemas and ceilings.
5. Hosted pilot on synthetic data; then a separately approved customer pilot.

## 9. Residual risks and open questions

- Compromise of our signing keys or build pipeline defeats everything above; key custody and access control need their own review.
- A same-process caller on a host the customer controls can patch verification; only detection and contract apply there.
- Legal terms (licence, audit right, export controls, data protection in India and the UK) need professional advice; nothing here is legal advice.
- The comparison to platforms like Palantir is general knowledge about how such platforms are commonly sold, not verified current facts about any vendor.
- Cost, staffing and hosting choices are unestimated.

## 10. Non-claims

This design does not establish that AGORA's outputs match reality, that any deployment is production-ready, or that any control above exists today.
