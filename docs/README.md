# Agora documentation

Agora is a living-world simulation and decision-intelligence platform. This index groups the documents by topic and labels what each one is. Status terms: **Current** (maintained, describes the repository now), **Design** (proposed or partly implemented; read its own status line), **Historical** (a record of a past milestone or plan; kept unchanged for evidence), **Frozen** (a protocol, manifest or result that must not be edited).

For the one authoritative statement of what is implemented, read [Rung status](RUNG_STATUS.md). Where a historical document disagrees with it, the status document wins.

## 1. Start here

- [README](../README.md): what Agora is, quick start, limitations. Current.
- [Roadmap](../ROADMAP.md): delivery phases. Current.
- [Platform roadmap](PLATFORM_ROADMAP.md): technical capability roadmap. Current.
- [Rung status](RUNG_STATUS.md): canonical implementation status. Current.
- [Baseline assessment](BASELINE_ASSESSMENT.md): capability matrix and enforcement findings with file and test evidence, 28 Nov 2026. Current; read-only, changes no code.

## 2. Living worlds and communication

- [Native social interaction design](NATIVE_SOCIAL_INTERACTION_DESIGN.md): direct agent-to-agent communication as a core capability, with simulated platforms as optional environments. Phases 1 to 4 and 6 implemented, phase 5 and several extensions not built; the document states which.
- [Scenario inputs](SCENARIO_INPUTS_SPEC.md): how data and assumptions enter a scenario. Current.

## 3. Knowledge and ontology

- [Ontology specification](ONTOLOGY_SPEC.md), [domain ontology model](DOMAIN_ONTOLOGY_MODEL.md), [data binding](ONTOLOGY_DATA_BINDING.md). Current.
- [Ontology capability target](ONTOLOGY_CAPABILITY_TARGET.md) and [object store design](ONTOLOGY_OBJECT_STORE_DESIGN.md). Design, partly implemented; each states its own status.
- [Ontology pack compatibility policy](ONTOLOGY_COMPATIBILITY.md). Current; a check you run, not enforced by the store.
- [Typed Python types from a domain pack](ONTOLOGY_TYPED_CLIENT.md). Library and command only; a shape check, not an API or SDK.
- [Ontology read interface, version 1](ONTOLOGY_READ_INTERFACE.md). In-process library pinned to one pack fingerprint; not a network service or SDK.
- [Ontology action proposals](ONTOLOGY_ACTION_PROPOSALS.md). Current; library only, executes nothing.
- [Portable ontology schemas and conformance vectors](ONTOLOGY_PORTABLE_SCHEMAS.md). Current; structure only.
- [Ingestion specification](INGESTION_SPEC.md), [run provenance](RUN_PROVENANCE_SPEC.md). Current.

## 4. Decisions and outcomes

- [Decision cell](DECISION_CELL_SPEC.md), [decision record](DECISION_RECORD_SPEC.md), [decision outcomes](DECISION_OUTCOMES_SPEC.md). Design and current contracts; read each status line.
- [Decision record implementation plan](DECISION_RECORD_IMPLEMENTATION_PLAN.md). Historical plan.
- [Outcome review markers](OUTCOME_REVIEW_MARKERS_SPEC.md), [hold review procedure](OUTCOME_HOLD_REVIEW_MANUAL_PROCEDURE.md), [reconciliation](RECONCILIATION_SPEC.md), [reconciliation procedure](RECONCILIATION_MANUAL_PROCEDURE.md). Current.

## 5. Security and governance

- [Product boundary and integrity design](PRODUCT_BOUNDARY_AND_INTEGRITY_DESIGN.md), [security architecture](SECURITY_ARCHITECTURE.md), [identity adapter](IDENTITY_ADAPTER_SPEC.md), [deployment hardening](DEPLOYMENT_HARDENING_SPEC.md), [retention and erasure](RETENTION_ERASURE_DESIGN.md). Current or Design; read each status line.
- [Audit anchor](AUDIT_ANCHOR_SPEC.md), [anchor wiring plan](ANCHOR_WIRING_PLAN.md), [principal migration plan](PRINCIPAL_MIGRATION_PLAN.md), [red team plan](RED_TEAM_PLAN.md). Specification and plans.
- [Governance approval lifecycle](GOVERNANCE_APPROVAL_LIFECYCLE.md), [governance holdout protocol](GOVERNANCE_HOLDOUT_PROTOCOL.md), [evaluator custody](EVALUATOR_CUSTODY.md). Current.
- [Governance audit log](GOVERNANCE_AUDIT_LOG.md). Historical record; append-only.

## 6. Validation and research

- [Validation protocol](VALIDATION_PROTOCOL.md), [validation run spec](VALIDATION_RUN_SPEC.md), [dataset manifest](VALIDATION_DATASET_MANIFEST.csv). **Frozen.** Do not edit.
- [Validation protocol v1 draft](VALIDATION_PROTOCOL_V1_DRAFT.md), [manifest v1 draft](VALIDATION_DATASET_MANIFEST_V1_DRAFT.csv). Historical drafts; kept unchanged.
- [Package E results](VALIDATION_RESULTS_PACKAGE_E.md). Recorded evidence; kept unchanged. It reports no edge over the published average; validated prediction is not enabled.
- [Dataset manifest template](DATASET_MANIFEST_TEMPLATE.md), [dataset download guide](DATASET_DOWNLOAD_GUIDE.md), [M3 dataset acquisition checklist](M3_DATASET_ACQUISITION_CHECKLIST.md). Current; acquisition is owner-gated.
- [Freight pricing showcase](SHOWCASE_FREIGHT.md). Synthetic-assumption showcase, not measured behaviour.

## 7. Operations

- [Operator runbook](OPERATOR_RUNBOOK.md), [pilot runbook](PILOT_RUNBOOK.md), [pilot readiness](PILOT_READINESS.md), [pilot data contract](PILOT_DATA_CONTRACT.md), [pilot run record fields](PILOT_RUN_RECORD_FIELDS.md), [synthetic pilot fixture](SYNTHETIC_PILOT_FIXTURE_SPEC.md), [pipeline how-to](PIPELINE_HOWTO.md). Current.
- [Runbook command inventory](M2_RUNBOOK_COMMAND_INVENTORY.md). Evidence.

## 8. Historical records

Kept unchanged as evidence of what was planned or decided at the time:
[milestone: pilot ready](MILESTONE_PILOT_READY.md), [milestone: operator pilot](MILESTONE_OPERATOR_PILOT.md), [M2 fixture selection](M2_FIXTURE_SELECTION_PLAN.md), [M2 one-command start](M2_ONE_COMMAND_START_PLAN.md), [M2 dress rehearsal](M2_DRESS_REHEARSAL_PLAN.md), [M2 audit anchor operator plan](M2_AUDIT_ANCHOR_OPERATOR_PLAN.md), [M2 backup/restore tamper plan](M2_BACKUP_RESTORE_TAMPER_PLAN.md), [rung 1–3 status snapshot](RUNG_1_3_STATUS.md), [M3 proposal](M3_PROPOSAL.md), [M3 design](M3_DESIGN.md), [M3 exit evidence](M3_EXIT_EVIDENCE.md), [simulation wiring proposal](SIM_WIRING_PROPOSAL.md), [full-potential test plan](FULL_POTENTIAL_TEST_PLAN.md), [ontology object store plan](superpowers/plans/2026-11-26-ontology-object-store.md).

M3 is declared effective for its stated, scope-limited purpose only. That is not predictive validity or production readiness.
