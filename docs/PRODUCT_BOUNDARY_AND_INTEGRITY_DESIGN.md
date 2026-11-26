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
- **Root bootstrap and signed key list.** The engine ships with, or is configured with, one or more offline root public keys, pinned by hash. Online signing keys are listed in a key list signed by a root key, with `key_id`, public key, `not_before`, `not_after`, status (active, retired, revoked), a monotonically increasing `list_version`, and signed UTC `issued_at` and `expires_at` timestamps. The engine accepts a receipt only if its `key_id` is active in a list that verifies against a pinned root. The root private key is kept offline and used only to sign key lists.
- **Rotation, revocation, rollback.** Online keys have a bounded lifetime and overlap during rotation. Revocation is a new, higher `list_version` marking the key revoked; receipts signed by it are refused from the moment the engine holds that list. The engine stores the highest `list_version` it has seen and refuses any lower one (rollback protection). A list past its own expiry is treated as stale: the engine refuses new receipts until it is refreshed (fail closed).
- **Nonce replay and atomicity.** Each receipt carries a random 128-bit `nonce` and a short `expires_at`. The verifier records `(key_id, nonce)` and consumes it in the same transaction as the action it authorises, so a crash cannot leave an action done with a reusable nonce, or a nonce burned with no action. A receipt that is single-use for one run cannot be replayed for another. Nonce records are kept at least until `expires_at` plus the permitted clock skew, then may be purged; a receipt whose nonce record could have been purged is already expired and is refused.
- **Clock and offline behaviour.** Expiry is checked against a trusted time source we operate; permitted skew is a small fixed number of seconds. If the engine cannot establish trusted time, or the key list or revocation data are stale beyond a stated limit, it refuses and writes nothing; there is no offline allow mode in v1.
- **Release verification, fail closed.** At start the engine verifies the signed release manifest against a pinned root, then hashes its own files. Verification failure marks the run `integrity: unverified` and the policy service refuses to issue receipts to that release id; if the policy service is unreachable the engine issues no governed run. A missing, malformed or unsigned manifest is treated as unverified, never as verified by default.

## 3B. Decisions and closed gaps (owner decisions of 24 Nov 2026; still design only)

**Owner decisions recorded:** hosted delivery first; **dedicated engine worker per tenant**; **cloud KMS** for online signing keys (managed Ed25519 signing, key use audit-logged); root key offline; HSM deferred until a paying client requires it. No implementation beyond the phase-1 paths approved in section 8.

1. **Canonical formats and test vectors (key lists, release manifests).** Both reuse the receipt rules of 3A (sorted keys, no floats, UTC `Z` timestamps, hex hashes with algorithm prefix, reject duplicates and unknown fields) with their own `type` field (`key_list`, `release_manifest`) inside the signed bytes and their own domain tag (`agora.keylist.v1\0`, `agora.release.v1\0`). A release manifest lists `{path, sha256, size}` sorted by path plus `release_id`, build time and `min_key_list_version`. Phase 1 ships fixed test vectors (input JSON, canonical bytes hex, signature hex, expected verdict) for receipts, then key lists and manifests in later phases; a vector set is a release gate. Test keys are marked and refused by any production trust list.
2. **Root-key rollover and compromise recovery.** Two root keys are pinned: current and standby (offline, separately stored). Rollover: the current root signs a key list that adds the standby as active root; engines accept the new root only through that chain, then retire the old one. Compromise of an online key: revoke via a higher key-list version, re-issue receipts. Compromise of the root: the standby root signs a `root_revocation` and a new list; engines that cannot chain to it are re-provisioned out of band by us (hosted: redeploy the pinned roots by signed digest). Loss of both roots is a full re-provision event; the runbook and a yearly drill are required before any customer.
3. **Durable nonce / action / audit consistency across services.** The policy service issues receipts; the engine consumes them. Rule: the engine consumes a nonce and appends the audit event in one transaction in the tenant's own store (one writer, no cross-service transaction). If the engine cannot commit, the action did not happen and the nonce is not consumed. The policy service keeps a record of issued `(receipt id, nonce, expires_at)` only for reconciliation: a reconcile job compares issued versus consumed per tenant and flags receipts that were consumed without an audit event or issued and never expired. An action is valid only if the consume-and-audit commit succeeded; the engine never acts on an in-memory receipt.
4. **Numeric limits (v1 proposed defaults, to be confirmed by test).** Receipt lifetime 5 minutes; permitted clock skew 30 seconds; key-list maximum age 15 minutes, refreshed every 5 minutes; online key lifetime 90 days with 14 days overlap; nonce records retained for lifetime + skew + 5 minutes; root keys reviewed yearly. After signature and root verification, freshness is checked against the signed `issued_at`/`expires_at` and trusted time; record a monotonic verification time and fail closed if signed age or monotonic elapsed time exceeds 15 minutes, expiry passes, the clock rolls back, or trusted time cannot be established. The 300-second receipt lifetime and 30-second skew match the phase-1 verifier. Any change requires corresponding code, tests and vectors plus owner approval. Defaults are in signed configuration, not caller-settable.
5. **Authentication of the actual running release.** A self-reported hash is not proof. Hosted: workers start only from our signed container digest; at start the worker obtains a short-lived attestation from the platform or our own launcher that binds `release_id`, image digest and worker id, signed by an attestation key held outside the worker; the policy service issues receipts only to a worker presenting a valid attestation, and stamps `release_id` into the receipt. A modified worker cannot obtain attestation, so it cannot get receipts. This is detection-plus-issuance control, not tamper-proofing of a host the customer owns (section 6). The exact attestation mechanism depends on the hosting provider and is chosen at the provider decision.
6. **Tenant isolation and custody (chosen architecture).** One worker per tenant, one data store, one audit chain and one set of derived keys per tenant; the tenant id is checked in the receipt, at the data layer and on every audit append; no shared writable volume; cross-tenant access is a test case that must fail. Cloud KMS holds online signing keys with an access policy that only the policy service identity can sign and only an operator group can rotate; workers hold public keys only. KMS and operator actions are logged to our audit store. Cost is higher than a shared fleet and is accepted for the first pilots.

**Implementation note (26 Nov 2026): durable nonce consumption, local library only.** `agora/security/receipt_ledger.py` implements the "consume and audit in one transaction" rule of 3A and 3B item 3 for one local store: after verification, the `receipt_consumed` audit event and the `(key_id, nonce)` row commit in one SQLite transaction through the anchored audit writer. Expiry is checked again after the write lock is held. The chain refuses a repeated consumption event id, and admissions stop if the nonce rows no longer match the chain, if the nonce table or its triggers have been altered, or if the store holds another tenant's receipts. If the anchor write fails after the commit, the receipt is spent and the action is refused. Design choices: the nonce table lives in the audit database (so no cross-database commit is needed); the anchored writer is mandatory with no relaxation flag; nonce records are not purged in this version. **Not done:** the engine and governed pipeline do not call it; the authorised action is not part of the transaction; there is no policy service, issued-versus-consumed reconciliation, signed key list or trusted time source (the caller passes the clock); it does not stop code in the same process, or an owner of both the database and the anchor, from bypassing or rewriting it.

**Implementation note (26 Nov 2026): signed key list, local library only.** `agora/security/key_list.py` implements the signed key list of 3A for one tenant store with test keys: canonical bytes under the `agora.keylist.v1` domain tag, one pinned root, a signed lifetime and age of at most 15 minutes, an online key window of at most 90 days, and a monotonic age and clock-rollback check. Accepting a list appends an event to the anchored audit chain, and that history is the rollback state: a lower version, different bytes under the same version, a key status moving backwards (including a revoked key returning after being omitted), or a re-bound key id or public key is refused. `admit_receipt_with_key_list` checks inside the nonce-consumption transaction that the list is still the newest accepted one and still fresh. Design choices (the stricter reading in each case): exactly one pinned root, so a standby root cannot sign until rollover is built; key status only moves forward; a key id and a public key are bound for the life of the store. **Not done:** root rollover and root revocation (3B item 2), pinning a standby root, canonical test vectors for key lists, list distribution and refresh, a trusted time source, release manifests, and any engine or pipeline call. The lower-level `admit_receipt` still accepts caller-supplied keys, so a service must call only the key-list function. A new, empty store accepts any correctly signed list that is still fresh. It does not stop same-process code, or an owner of both the audit database and the anchor, from rewriting this state.

## 4. Signed releases and run stamping (proposed)

- The build pipeline produces an immutable artifact (wheel or container digest) and a signed manifest of its file hashes. Signing tool and transparency log are open choices.
- On start, the engine hashes its own files against the signed manifest and records `release_id` and `integrity: verified|unverified` in every run's provenance and reports. A modified engine can still run but is labelled unverified, and the policy service can refuse to issue receipts to unverified releases.
- Hosted deployment pulls by digest only; images are immutable; customers have no shell or file access.

**What it gives:** detection and evidence. **What it cannot give:** physical prevention on a machine the customer controls.

## 5. Hosted deployment (first delivery model)

- Hosted control plane operated by us; one dedicated engine worker per tenant; per-tenant data stores, encryption/data keys and audit chains; tenant id in every receipt and audit record.
- Egress control: engines can reach only approved read-only sources; no write-back in the first release.
- Customers interact only through the API and console. Operations (deploys, key use, support access) are logged in the existing audit chain.
- Remaining decisions: hosting provider and cost, regional data residency (India, UK), backup and restore design, and incident-response operations. The first hosted architecture uses a dedicated engine worker per tenant; shared-versus-dedicated tenant isolation is no longer open.

**Hosted isolation and operations (to be specified before any pilot; dedicated worker per tenant is the selected model).** Per-tenant separation of data stores, keys and audit chains, with a tenant id enforced at the receipt check and again at the data layer; engine workers run without network access except to the approved read-only source gateway; no tenant can read another's snapshots, logs or reports; operators use named, time-limited, audited access with no standing production shell; secrets and signing keys are never present on engine workers (workers hold public keys only); deploys are by signed digest with a recorded approver; backups are encrypted and restore-tested per tenant; incident response, key-compromise runbook (revoke, rotate, re-issue key list, notify) and tenant offboarding (verified deletion) are written before the first customer. None of this is built or tested.

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
1. Receipt format and a local verifying module with test keys; forged-receipt negative tests with mutation proofs. **Approved paths (owner, 24 Nov 2026):** `agora/security/signed_receipt.py`, `tests/test_signed_receipt.py`, `tests/vectors/receipt_vectors.json`. No engine wiring, no production key, no `agora/sim/**` change; the engine verification path is a later, separately approved slice.
2. Policy service with key custody on synthetic data only.
3. Release signing, self-check, run stamping; unverified-release refusal rule.
4. API and console boundary; configuration schemas and ceilings.
5. Hosted pilot on synthetic data; then a separately approved customer pilot.

## 9. Residual risks and open questions

- Compromise of our signing keys or build pipeline defeats everything above; key custody and access control need their own review.
- A same-process caller on a host the customer controls can patch verification; only detection and contract apply there.
- Legal terms (licence, audit right, export controls, data protection in India and the UK) need professional advice; nothing here is legal advice.
- Commercial packaging, pricing and sales-model assumptions are unverified market judgement, not evidence.
- Cost, staffing and hosting choices are unestimated.

## 10. Non-claims

This design does not establish that AGORA's outputs match reality, that any deployment is production-ready, or that any control above exists today.
