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

## 3A. Receipt cryptography and key lifecycle (proposed specification)

- **Canonical signed bytes.** The signature covers the UTF-8 bytes of the receipt's JSON in a single canonical form: keys sorted, no insignificant whitespace, integers only (no floats), timestamps as UTC RFC 3339 strings with a `Z` suffix, hashes as lowercase hex with an explicit algorithm prefix. Duplicate keys, unknown fields and non-canonical encodings are rejected, not normalised. One canonicaliser is shared by signer and verifier and tested against fixed vectors.
- **Algorithm, version, domain separation.** Ed25519 only in version 1; the receipt carries `v` (format version) and `alg`. The signer prepends a fixed domain tag (for example `agora.receipt.v1\0`) to the canonical bytes before signing, so a signature made for a receipt can never validate as a release manifest or any other object. A verifier refuses an unknown `v` or `alg` (no downgrade, no algorithm negotiation).
- **Root bootstrap and signed key list.** The engine ships with, or is configured with, one or more offline root public keys, pinned by hash. Online signing keys are listed in a key list signed by a root key, with `key_id`, public key, `not_before`, `not_after`, status (active, retired, revoked) and a monotonically increasing `list_version`. The engine accepts a receipt only if its `key_id` is active in a list that verifies against a pinned root. The root private key is kept offline and used only to sign key lists.
- **Rotation, revocation, rollback.** Online keys have a bounded lifetime and overlap during rotation. Revocation is a new, higher `list_version` marking the key revoked; receipts signed by it are refused from the moment the engine holds that list. The engine stores the highest `list_version` it has seen and refuses any lower one (rollback protection). A list past its own expiry is treated as stale: the engine refuses new receipts until it is refreshed (fail closed).
- **Nonce replay and atomicity.** Each receipt carries a random 128-bit `nonce` and a short `expires_at`. The verifier records `(key_id, nonce)` and consumes it in the same transaction as the action it authorises, so a crash cannot leave an action done with a reusable nonce, or a nonce burned with no action. A receipt that is single-use for one run cannot be replayed for another. Nonce records are kept at least until `expires_at` plus the permitted clock skew, then may be purged; a receipt whose nonce record could have been purged is already expired and is refused.
- **Clock and offline behaviour.** Expiry is checked against a trusted time source we operate; permitted skew is a small fixed number of seconds. If the engine cannot establish trusted time, or the key list or revocation data are stale beyond a stated limit, it refuses and writes nothing; there is no offline allow mode in v1.
- **Release verification, fail closed.** At start the engine verifies the signed release manifest against a pinned root, then hashes its own files. Verification failure marks the run `integrity: unverified` and the policy service refuses to issue receipts to that release id; if the policy service is unreachable the engine issues no governed run. A missing, malformed or unsigned manifest is treated as unverified, never as verified by default.

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

**Hosted isolation and operations (to be specified before any pilot).** Per-tenant separation of data stores, keys and audit chains, with a tenant id enforced at the receipt check and again at the data layer; engine workers run without network access except to the approved read-only source gateway; no tenant can read another's snapshots, logs or reports; operators use named, time-limited, audited access with no standing production shell; secrets and signing keys are never present on engine workers (workers hold public keys only); deploys are by signed digest with a recorded approver; backups are encrypted and restore-tested per tenant; incident response, key-compromise runbook (revoke, rotate, re-issue key list, notify) and tenant offboarding (verified deletion) are written before the first customer. None of this is built or tested.

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
