"""Persistent, project-local storage for immutable ontology definitions.

This first slice stores only domain-pack and binding definitions. Imported
source rows remain in tabular snapshots and are not copied here.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from .. import protection as _protection
from ..audit_anchor import require_anchored
from ..pathsafe import UnsafePathError, require_safe_path
from ..policy_enforcement import PolicyCallable, PolicyEnforcementError, enforce_policy
from .binding import (
    DataBinding, iter_source_object_refs, load_binding, materialize_source_object,
)
from .registry import OntologyError, OntologyPack, parse_domain_pack

_STORE_SCHEMA = (
    """CREATE TABLE ontology_packs (
        fingerprint TEXT PRIMARY KEY,
        pack_id TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        content_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE bindings (
        pack_fingerprint TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        binding_id TEXT NOT NULL,
        binding_version TEXT NOT NULL,
        content_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (pack_fingerprint, fingerprint),
        FOREIGN KEY (pack_fingerprint) REFERENCES ontology_packs(fingerprint)
    )""",
    """CREATE TRIGGER ontology_packs_no_update
        BEFORE UPDATE ON ontology_packs
        BEGIN SELECT RAISE(ABORT, 'ontology pack snapshots are immutable'); END""",
    """CREATE TRIGGER ontology_packs_no_delete
        BEFORE DELETE ON ontology_packs
        BEGIN SELECT RAISE(ABORT, 'ontology pack snapshots are immutable'); END""",
    """CREATE TRIGGER ontology_bindings_no_update
        BEFORE UPDATE ON bindings
        BEGIN SELECT RAISE(ABORT, 'ontology binding snapshots are immutable'); END""",
    """CREATE TRIGGER ontology_bindings_no_delete
        BEFORE DELETE ON bindings
        BEGIN SELECT RAISE(ABORT, 'ontology binding snapshots are immutable'); END""",
)
_SCHEMA_CHECKSUM = hashlib.sha256("\n".join(_STORE_SCHEMA).encode("utf-8")).hexdigest()
_OBJECT_REFS_SCHEMA = (
    """CREATE TABLE ontology_object_refs (
        project_id TEXT NOT NULL,
        pack_fingerprint TEXT NOT NULL,
        type_id TEXT NOT NULL,
        type_version TEXT NOT NULL,
        binding_fingerprint TEXT NOT NULL,
        import_id TEXT NOT NULL,
        dataset_id TEXT NOT NULL,
        record_key TEXT NOT NULL,
        snapshot_row_id TEXT NOT NULL,
        schema_id TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        schema_fingerprint TEXT NOT NULL,
        source_registry_id TEXT,
        file_sha256 TEXT NOT NULL,
        source_locator_json TEXT NOT NULL,
        property_sensitivity_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (project_id, pack_fingerprint, type_id, type_version, import_id, record_key),
        UNIQUE (project_id, pack_fingerprint, type_id, type_version, import_id, snapshot_row_id),
        FOREIGN KEY (pack_fingerprint) REFERENCES ontology_packs(fingerprint),
        FOREIGN KEY (pack_fingerprint, binding_fingerprint)
            REFERENCES bindings(pack_fingerprint, fingerprint)
    )""",
    """CREATE TRIGGER ontology_object_refs_no_update
        BEFORE UPDATE ON ontology_object_refs
        BEGIN SELECT RAISE(ABORT, 'ontology object references are immutable'); END""",
    """CREATE TRIGGER ontology_object_refs_no_delete
        BEFORE DELETE ON ontology_object_refs
        BEGIN SELECT RAISE(ABORT, 'ontology object references are immutable'); END""",
)
_OBJECT_REFS_CHECKSUM = hashlib.sha256("\n".join(_OBJECT_REFS_SCHEMA).encode("utf-8")).hexdigest()


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise OntologyError(f"value is not canonically serializable: {exc}") from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class OntologyObjectStore:
    """Immutable pack/binding catalog stored under project/data."""

    def __init__(self, project: str | Path):
        self.project = Path(project)
        self.project_id = self.project.name or str(self.project)
        self.path = self.project / "data" / "ontology.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        try:
            require_safe_path(self.project)
            require_safe_path(self.path.parent)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            require_safe_path(self.path)
            conn = sqlite3.connect(str(self.path), timeout=30.0, isolation_level=None)
        except (OSError, UnsafePathError, sqlite3.Error) as exc:
            raise OntologyError("ontology store path is unavailable or unsafe") from exc
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        self._initialize(conn)
        return conn

    def _initialize(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )"""
        )
        rows = conn.execute("SELECT version, checksum FROM schema_migrations ORDER BY version").fetchall()
        if not rows:
            try:
                conn.execute("BEGIN IMMEDIATE")
                for statement in _STORE_SCHEMA:
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES (1, ?, ?)",
                    (_SCHEMA_CHECKSUM, _utc_now()),
                )
                for statement in _OBJECT_REFS_SCHEMA:
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES (2, ?, ?)",
                    (_OBJECT_REFS_CHECKSUM, _utc_now()),
                )
                conn.commit()
                rows = conn.execute("SELECT version, checksum FROM schema_migrations ORDER BY version").fetchall()
            except sqlite3.Error as exc:
                conn.rollback()
                raise OntologyError("ontology store migration failed") from exc
        elif len(rows) == 1 and rows[0]["version"] == 1:
            if rows[0]["checksum"] != _SCHEMA_CHECKSUM:
                raise OntologyError("ontology store v1 migration checksum changed")
            try:
                conn.execute("BEGIN IMMEDIATE")
                for statement in _OBJECT_REFS_SCHEMA:
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES (2, ?, ?)",
                    (_OBJECT_REFS_CHECKSUM, _utc_now()),
                )
                conn.commit()
                rows = conn.execute("SELECT version, checksum FROM schema_migrations ORDER BY version").fetchall()
            except sqlite3.Error as exc:
                conn.rollback()
                raise OntologyError("ontology store migration failed") from exc
        expected_versions = [(1, _SCHEMA_CHECKSUM), (2, _OBJECT_REFS_CHECKSUM)]
        if [(row["version"], row["checksum"]) for row in rows] != expected_versions:
            raise OntologyError("ontology store schema is unknown or a migration checksum changed")
        expected = {"ontology_packs", "bindings", "ontology_object_refs"}
        present = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if not expected.issubset(present):
            raise OntologyError("ontology store schema is incomplete")

    def _authorize(
        self, operation: str, resource_ids: list[str], *,
        policy: PolicyCallable | None, audit: Any | None,
        sensitivity: str = "internal",
    ) -> None:
        try:
            decision = enforce_policy(
                policy,
                project=self.project,
                operation=operation,
                resource={
                    "project_id": self.project_id,
                    "resource_ids": resource_ids,
                    "source_sensitivity": sensitivity,
                    "target_sensitivity": sensitivity,
                    "purpose": "ontology_catalog",
                    "retention": "project_lifetime",
                },
                audit=audit,
            )
            if audit is None:
                raise OntologyError("ontology catalog operations require an audit writer")
            writer = require_anchored(audit) if _protection.ANCHOR_REQUIRED else audit
            writer.append({
                "event_id": f"ontology-{uuid.uuid4().hex}",
                "event_type": "ontology_operation_authorized",
                "operation": operation,
                "decision": "allow",
                "subject_id": str(decision.get("subject_id", "unknown")) if decision else "unknown",
                "policy_version": str(decision.get("policy_version", "unknown")) if decision else "unknown",
                "resource_ids": resource_ids,
                "reason": "policy_allow",
            })
        except PolicyEnforcementError as exc:
            raise OntologyError("policy denied ontology catalog access") from exc

    def register_pack(
        self, pack: OntologyPack, *, policy: PolicyCallable | None, audit: Any | None,
    ) -> str:
        if not isinstance(pack, OntologyPack):
            raise OntologyError("pack must be a validated OntologyPack")
        pack = parse_domain_pack(json.loads(_canonical(asdict(pack))))
        fingerprint = pack.fingerprint
        resource_id = f"{pack.pack_id}:{fingerprint}"
        self._authorize("ontology_write", [resource_id], policy=policy, audit=audit)
        payload = _canonical(asdict(pack))
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute(
                "SELECT content_json FROM ontology_packs WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
            if previous is not None:
                if previous["content_json"] != payload:
                    raise OntologyError("same ontology pack fingerprint has different content")
                conn.commit()
                return fingerprint
            conn.execute(
                "INSERT INTO ontology_packs(fingerprint, pack_id, schema_version, content_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (fingerprint, pack.pack_id, pack.schema_version, payload, _utc_now()),
            )
            conn.commit()
            return fingerprint
        except (sqlite3.Error, OntologyError):
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_pack(
        self, fingerprint: str, *, policy: PolicyCallable | None, audit: Any | None,
    ) -> OntologyPack:
        self._authorize("ontology_read", [fingerprint], policy=policy, audit=audit)
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT content_json FROM ontology_packs WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
            if row is None:
                raise OntologyError("unknown ontology pack fingerprint")
            pack = parse_domain_pack(json.loads(row["content_json"]))
            if pack.fingerprint != fingerprint:
                raise OntologyError("stored ontology pack fingerprint does not match its content")
            return pack
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise OntologyError("ontology pack snapshot could not be read") from exc
        finally:
            conn.close()

    def register_binding(
        self, pack_fingerprint: str, binding: DataBinding | dict[str, Any], *,
        policy: PolicyCallable | None, audit: Any | None,
    ) -> str:
        binding = load_binding(binding.as_dict() if isinstance(binding, DataBinding) else binding)
        self._authorize(
            "ontology_write", [pack_fingerprint, binding.binding_id, binding.fingerprint],
            policy=policy, audit=audit,
        )
        payload = _canonical(binding.as_dict())
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT content_json FROM ontology_packs WHERE fingerprint=?", (pack_fingerprint,)
            ).fetchone()
            if row is None:
                raise OntologyError("binding refers to an unknown ontology pack fingerprint")
            pack = parse_domain_pack(json.loads(row["content_json"]))
            object_types = [
                item for item in pack.object_types
                if item.type_id == binding.object_type_id and item.version == binding.object_type_version
            ]
            if len(object_types) != 1:
                raise OntologyError("binding object type/version does not resolve in the selected pack")
            if set(binding.column_map.values()) != set(object_types[0].properties):
                raise OntologyError("binding must map exactly the selected ObjectType properties")
            property_ids = {item.property_id for item in pack.property_types}
            if not set(binding.column_map.values()).issubset(property_ids):
                raise OntologyError("binding references a property outside the selected pack")
            existing = conn.execute(
                "SELECT content_json FROM bindings WHERE pack_fingerprint=? AND fingerprint=?",
                (pack_fingerprint, binding.fingerprint),
            ).fetchone()
            if existing is not None:
                if existing["content_json"] != payload:
                    raise OntologyError("same ontology binding fingerprint has different content")
                conn.commit()
                return binding.fingerprint
            conn.execute(
                "INSERT INTO bindings(pack_fingerprint, fingerprint, binding_id, binding_version, content_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pack_fingerprint, binding.fingerprint, binding.binding_id, binding.binding_version, payload, _utc_now()),
            )
            conn.commit()
            return binding.fingerprint
        except (sqlite3.Error, OntologyError, json.JSONDecodeError):
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_binding(
        self, pack_fingerprint: str, binding_fingerprint: str, *,
        policy: PolicyCallable | None, audit: Any | None,
    ) -> DataBinding:
        self._authorize(
            "ontology_read", [pack_fingerprint, binding_fingerprint],
            policy=policy, audit=audit,
        )
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT content_json FROM bindings WHERE pack_fingerprint=? AND fingerprint=?",
                (pack_fingerprint, binding_fingerprint),
            ).fetchone()
            if row is None:
                raise OntologyError("unknown ontology binding fingerprint for the selected pack")
            binding = load_binding(json.loads(row["content_json"]))
            if binding.fingerprint != binding_fingerprint:
                raise OntologyError("stored ontology binding fingerprint does not match its content")
            return binding
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise OntologyError("ontology binding snapshot could not be read") from exc
        finally:
            conn.close()


    def materialize_binding(
        self, pack_fingerprint: str, binding_fingerprint: str, import_id: str, *,
        policy: PolicyCallable | None, audit: Any | None,
        purpose: str | None = None, retention: str | None = None,
    ) -> int:
        """Index stable object identities and provenance for one exact import."""
        if not isinstance(import_id, str) or not import_id.strip() or import_id == "latest":
            raise OntologyError("an explicit import_id is required")
        self._authorize(
            "ontology_write", [pack_fingerprint, binding_fingerprint, import_id],
            policy=policy, audit=audit,
        )
        pack = self.get_pack(pack_fingerprint, policy=policy, audit=audit)
        binding = self.get_binding(
            pack_fingerprint, binding_fingerprint, policy=policy, audit=audit,
        )
        refs = iter_source_object_refs(
            binding, pack, self.project, import_id, policy=policy, audit=audit,
            purpose=purpose, retention=retention,
        )
        conn = self._connect()
        count = 0
        try:
            conn.execute("BEGIN IMMEDIATE")
            for ref in refs:
                if not ref.get("file_sha256"):
                    raise OntologyError("source snapshot row is missing its content SHA-256")
                values = (
                    self.project_id, pack_fingerprint, ref["object_type_id"],
                    ref["object_type_version"], binding_fingerprint, import_id,
                    ref["dataset_id"], ref["record_key"], ref["row_id"],
                    ref["schema_id"], ref["schema_version"], ref["schema_fingerprint"],
                    ref["source_registry_id"], ref["file_sha256"],
                    _canonical(ref["source_locator"]),
                    _canonical(ref["property_sensitivity"]), _utc_now(),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO ontology_object_refs(
                        project_id, pack_fingerprint, type_id, type_version,
                        binding_fingerprint, import_id, dataset_id, record_key,
                        snapshot_row_id, schema_id, schema_version, schema_fingerprint,
                        source_registry_id, file_sha256, source_locator_json,
                        property_sensitivity_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
                stored = conn.execute(
                    """SELECT dataset_id, snapshot_row_id, schema_id, schema_version,
                              schema_fingerprint, source_registry_id, file_sha256,
                              source_locator_json, property_sensitivity_json
                       FROM ontology_object_refs
                       WHERE project_id=? AND pack_fingerprint=? AND type_id=? AND type_version=?
                         AND import_id=? AND record_key=?""",
                    (self.project_id, pack_fingerprint, ref["object_type_id"],
                     ref["object_type_version"], import_id, ref["record_key"]),
                ).fetchone()
                expected = (
                    ref["dataset_id"], ref["row_id"], ref["schema_id"], ref["schema_version"],
                    ref["schema_fingerprint"], ref["source_registry_id"], ref["file_sha256"],
                    _canonical(ref["source_locator"]), _canonical(ref["property_sensitivity"]),
                )
                if stored is None or tuple(stored) != expected:
                    raise OntologyError("stable object identity conflicts with an existing snapshot reference")
                count += 1
            if count == 0:
                raise OntologyError("snapshot contains no materializable rows")
            conn.commit()
            return count
        except (sqlite3.Error, OntologyError):
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_object(
        self, pack_fingerprint: str, type_id: str, type_version: str,
        record_key: str, import_id: str, *, policy: PolicyCallable | None,
        audit: Any | None, purpose: str | None = None, retention: str | None = None,
    ) -> dict[str, Any]:
        """Resolve one stable object from its exact immutable snapshot row."""
        if not isinstance(import_id, str) or not import_id.strip() or import_id == "latest":
            raise OntologyError("an explicit import_id is required")
        self._authorize(
            "ontology_read", [pack_fingerprint, type_id, type_version, record_key, import_id],
            policy=policy, audit=audit,
        )
        conn = self._connect()
        try:
            ref = conn.execute(
                """SELECT binding_fingerprint, dataset_id, snapshot_row_id, schema_id,
                          schema_version, schema_fingerprint, source_registry_id, file_sha256,
                          source_locator_json, property_sensitivity_json
                   FROM ontology_object_refs
                   WHERE project_id=? AND pack_fingerprint=? AND type_id=? AND type_version=?
                     AND import_id=? AND record_key=?""",
                (self.project_id, pack_fingerprint, type_id, type_version, import_id, record_key),
            ).fetchone()
            if ref is None:
                raise OntologyError("object reference was not found in the exact import")
            binding_fingerprint = ref["binding_fingerprint"]
            expected = dict(ref)
        finally:
            conn.close()
        pack = self.get_pack(pack_fingerprint, policy=policy, audit=audit)
        binding = self.get_binding(
            pack_fingerprint, binding_fingerprint, policy=policy, audit=audit,
        )
        instance = materialize_source_object(
            binding, pack, self.project, import_id, expected["snapshot_row_id"],
            record_key, policy=policy, audit=audit, purpose=purpose, retention=retention,
        )
        stored_locator = json.loads(expected["source_locator_json"])
        stored_sensitivity = json.loads(expected["property_sensitivity_json"])
        if (
            instance["dataset_id"] != expected["dataset_id"]
            or instance["schema_id"] != expected["schema_id"]
            or instance["schema_version"] != expected["schema_version"]
            or instance["schema_fingerprint"] != expected["schema_fingerprint"]
            or instance["source_registry_id"] != expected["source_registry_id"]
            or instance["file_sha256"] != expected["file_sha256"]
            or _canonical(instance["source_locator"]) != _canonical(stored_locator)
            or _canonical(instance["property_sensitivity"]) != _canonical(stored_sensitivity)
        ):
            raise OntologyError("snapshot provenance no longer matches the stored object reference")
        return instance
