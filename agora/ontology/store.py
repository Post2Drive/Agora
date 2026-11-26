"""Persistent, project-local storage for immutable ontology definitions.

This first slice stores only domain-pack and binding definitions. Imported
source rows remain in tabular snapshots and are not copied here.
"""
from __future__ import annotations

from dataclasses import asdict
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping
import uuid

from .. import protection as _protection
from ..audit_anchor import require_anchored
from ..pathsafe import UnsafePathError, require_safe_path
from ..policy_enforcement import PolicyCallable, PolicyEnforcementError, enforce_policy
from .binding import (
    DataBinding, iter_source_object_refs, load_binding, materialize_source_object,
)
from .registry import OntologyError, OntologyPack, LinkType, parse_domain_pack

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


_LINKS_SCHEMA = (
    """CREATE TABLE ontology_links (
        link_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        pack_fingerprint TEXT NOT NULL,
        link_type_id TEXT NOT NULL,
        link_type_version TEXT NOT NULL,
        source_type_id TEXT NOT NULL,
        source_type_version TEXT NOT NULL,
        source_import_id TEXT NOT NULL,
        source_record_key TEXT NOT NULL,
        target_type_id TEXT NOT NULL,
        target_type_version TEXT NOT NULL,
        target_import_id TEXT NOT NULL,
        target_record_key TEXT NOT NULL,
        valid_from TEXT NOT NULL,
        valid_to TEXT,
        created_at TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        reason TEXT NOT NULL,
        provenance_json TEXT NOT NULL,
        supersedes_link_id TEXT,
        FOREIGN KEY (pack_fingerprint) REFERENCES ontology_packs(fingerprint),
        FOREIGN KEY (project_id, pack_fingerprint, source_type_id, source_type_version, source_import_id, source_record_key)
            REFERENCES ontology_object_refs(project_id, pack_fingerprint, type_id, type_version, import_id, record_key),
        FOREIGN KEY (project_id, pack_fingerprint, target_type_id, target_type_version, target_import_id, target_record_key)
            REFERENCES ontology_object_refs(project_id, pack_fingerprint, type_id, type_version, import_id, record_key),
        FOREIGN KEY (supersedes_link_id) REFERENCES ontology_links(link_id)
    )""",
    "CREATE INDEX ontology_links_source_idx ON ontology_links(project_id, pack_fingerprint, link_type_id, link_type_version, source_type_id, source_type_version, source_import_id, source_record_key)",
    "CREATE INDEX ontology_links_target_idx ON ontology_links(project_id, pack_fingerprint, link_type_id, link_type_version, target_type_id, target_type_version, target_import_id, target_record_key)",
    "CREATE UNIQUE INDEX ontology_links_successor_idx ON ontology_links(supersedes_link_id) WHERE supersedes_link_id IS NOT NULL",
    """CREATE TRIGGER ontology_links_no_update BEFORE UPDATE ON ontology_links
       BEGIN SELECT RAISE(ABORT, 'ontology links are immutable'); END""",
    """CREATE TRIGGER ontology_links_no_delete BEFORE DELETE ON ontology_links
       BEGIN SELECT RAISE(ABORT, 'ontology links are immutable'); END""",
)
_LINKS_CHECKSUM = hashlib.sha256("\n".join(_LINKS_SCHEMA).encode("utf-8")).hexdigest()


def _canonical_timestamp(value: str | datetime, field: str) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        except ValueError as exc:
            raise OntologyError(f"{field} must be an ISO-8601 timestamp with a timezone") from exc
    else:
        raise OntologyError(f"{field} must be an ISO-8601 timestamp with a timezone")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OntologyError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _link_endpoint(value: Mapping[str, Any], project_id: str, pack_fingerprint: str) -> dict[str, str]:
    required = {"project_id", "pack_fingerprint", "type_id", "type_version", "import_id", "record_key"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise OntologyError("link endpoint must contain exactly the pinned object identity fields")
    endpoint = {}
    for key in required:
        item = value[key]
        if not isinstance(item, str) or not item.strip() or item != item.strip():
            raise OntologyError(f"link endpoint {key} must be a non-empty canonical string")
        endpoint[key] = item
    if endpoint["project_id"] != project_id or endpoint["pack_fingerprint"] != pack_fingerprint:
        raise OntologyError("link endpoints must belong to this project and exact ontology pack")
    if endpoint["import_id"] == "latest":
        raise OntologyError("link endpoints require an exact import_id")
    return endpoint


def _encode_cursor(payload: Mapping[str, Any]) -> str:
    raw = _canonical(dict(payload)).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise OntologyError("query cursor is invalid")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        result = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise OntologyError("query cursor is invalid") from exc
    if not isinstance(result, dict):
        raise OntologyError("query cursor is invalid")
    return result


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise OntologyError(f"value is not canonically serializable: {exc}") from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _link_created_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


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
        migrations = (
            (1, _SCHEMA_CHECKSUM, _STORE_SCHEMA),
            (2, _OBJECT_REFS_CHECKSUM, _OBJECT_REFS_SCHEMA),
            (3, _LINKS_CHECKSUM, _LINKS_SCHEMA),
        )
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT version, checksum FROM schema_migrations ORDER BY version").fetchall()
            actual = [(int(row["version"]), row["checksum"]) for row in rows]
            expected = [(version, checksum) for version, checksum, _ in migrations[:len(actual)]]
            if actual != expected or len(actual) > len(migrations):
                raise OntologyError("ontology store schema is unknown or a migration checksum changed")
            for version, checksum, statements in migrations[len(actual):]:
                for statement in statements:
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES (?, ?, ?)",
                    (version, checksum, _utc_now()),
                )
            conn.commit()
        except (sqlite3.Error, OntologyError) as exc:
            conn.rollback()
            if isinstance(exc, OntologyError):
                raise
            raise OntologyError("ontology store migration failed") from exc
        rows = conn.execute("SELECT version, checksum FROM schema_migrations ORDER BY version").fetchall()
        expected = [(version, checksum) for version, checksum, _ in migrations]
        if [(int(row["version"]), row["checksum"]) for row in rows] != expected:
            raise OntologyError("ontology store schema is unknown or a migration checksum changed")
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if not {"ontology_packs", "bindings", "ontology_object_refs", "ontology_links"}.issubset(tables):
            raise OntologyError("ontology store schema is incomplete")

    def _authorize(
        self, operation: str, resource_ids: list[str], *,
        policy: PolicyCallable | None, audit: Any | None,
        sensitivity: str = "internal",
    ) -> Mapping[str, Any] | None:
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
            return decision
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
        if binding.object_type_id != type_id or binding.object_type_version != type_version:
            raise OntologyError("object reference does not match its binding object type/version")
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


    @staticmethod
    def _link_key(endpoint: Mapping[str, str]) -> tuple[str, str, str, str]:
        return (endpoint["type_id"], endpoint["type_version"], endpoint["import_id"], endpoint["record_key"])

    @staticmethod
    def _canonical_endpoint(value: Mapping[str, Any], project_id: str, pack_fingerprint: str) -> dict[str, str]:
        required = {"project_id", "pack_fingerprint", "type_id", "type_version", "import_id", "record_key"}
        if not isinstance(value, Mapping) or set(value) != required:
            raise OntologyError("link endpoint must contain exactly the pinned object identity fields")
        result = {}
        for key in required:
            item = value[key]
            if not isinstance(item, str) or not item.strip() or item != item.strip():
                raise OntologyError(f"link endpoint {key} must be a non-empty canonical string")
            result[key] = item
        if result["project_id"] != project_id or result["pack_fingerprint"] != pack_fingerprint:
            raise OntologyError("link endpoint crosses project or pack scope")
        if result["import_id"] == "latest":
            raise OntologyError("link endpoints require an explicit import_id")
        return result

    def _link_type(self, pack: OntologyPack, type_id: str, version: str) -> LinkType:
        found = [x for x in pack.link_types if x.link_type_id == type_id and x.version == version]
        if len(found) != 1:
            raise OntologyError("link type/version does not resolve in the selected pack")
        result = found[0]
        if result.cardinality not in {"one_to_one", "one_to_many", "many_to_many"}:
            raise OntologyError("unsupported ontology link cardinality")
        return result

    def _write_link(
        self, pack_fingerprint: str, link_type_id: str, link_type_version: str,
        source: Mapping[str, Any], target: Mapping[str, Any], valid_from: str | datetime,
        valid_to: str | datetime | None, reason: str, provenance: Mapping[str, Any],
        *, policy: PolicyCallable | None, audit: Any | None, supersedes_link_id: str | None = None,
    ) -> str:
        src = self._canonical_endpoint(source, self.project_id, pack_fingerprint)
        dst = self._canonical_endpoint(target, self.project_id, pack_fingerprint)
        start = _canonical_timestamp(valid_from, "valid_from")
        end = _canonical_timestamp(valid_to, "valid_to") if valid_to is not None else None
        if end is not None and end <= start:
            raise OntologyError("valid_to must be later than valid_from")
        if not isinstance(reason, str) or not reason.strip() or not isinstance(provenance, Mapping) or not provenance:
            raise OntologyError("link writes require a reason and provenance")
        provenance_json = _canonical(dict(provenance))
        kind = provenance.get("kind")
        if kind not in {"source", "manual_assertion", "derived"}:
            raise OntologyError("provenance kind must be source, manual_assertion, or derived")
        if kind == "source":
            refs = provenance.get("source_refs")
            if not isinstance(refs, list) or not refs:
                raise OntologyError("source-backed links require exact source_refs")
            for ref in refs:
                if not isinstance(ref, Mapping) or not all(
                    isinstance(ref.get(key), str) and ref[key].strip()
                    for key in ("import_id", "file_sha256", "locator")
                ):
                    raise OntologyError("each source_ref requires import_id, file_sha256, and locator")
                digest = ref["file_sha256"]
                if len(digest) != 64 or any(char not in "0123456789abcdefABCDEF" for char in digest):
                    raise OntologyError("source_ref file_sha256 must be a 64-character SHA-256")
        pack = self.get_pack(pack_fingerprint, policy=policy, audit=audit)
        link_type = self._link_type(pack, link_type_id, link_type_version)
        types = {x.type_id: x for x in pack.object_types}
        if link_type.source_type_id not in types or link_type.target_type_id not in types:
            raise OntologyError("link type endpoints do not resolve in the selected pack")
        if (src["type_id"], src["type_version"]) != (link_type.source_type_id, types[link_type.source_type_id].version):
            raise OntologyError("source endpoint does not match the selected LinkType")
        if (dst["type_id"], dst["type_version"]) != (link_type.target_type_id, types[link_type.target_type_id].version):
            raise OntologyError("target endpoint does not match the selected LinkType")
        src_key, dst_key = self._link_key(src), self._link_key(dst)
        resource_ids = [pack_fingerprint, link_type_id, link_type_version, *src_key, *dst_key]
        self._authorize("ontology_write", resource_ids, policy=policy, audit=audit)
        metadata_conn = self._connect()
        try:
            sensitivities = []
            for key in (src_key, dst_key):
                row = metadata_conn.execute(
                    """SELECT property_sensitivity_json FROM ontology_object_refs
                       WHERE project_id=? AND pack_fingerprint=? AND type_id=? AND type_version=?
                         AND import_id=? AND record_key=?""",
                    (self.project_id, pack_fingerprint, *key),
                ).fetchone()
                if row is None:
                    raise OntologyError("link endpoint is not materialized")
                stored = json.loads(row["property_sensitivity_json"])
                if isinstance(stored, dict):
                    sensitivities.extend(v for v in stored.values() if isinstance(v, str))
        finally:
            metadata_conn.close()
        rank = {"public": 0, "internal": 1, "personal": 2, "sensitive": 3}
        sensitivity = max((v for v in sensitivities if v in rank), key=rank.__getitem__, default="internal")
        decision = self._authorize(
            "ontology_write", resource_ids, policy=policy, audit=audit, sensitivity=sensitivity,
        )
        if not isinstance(decision, Mapping) or not isinstance(decision.get("subject_id"), str) or not decision["subject_id"].strip() or decision["subject_id"] == "unknown":
            raise OntologyError("link writes require a principal-bound actor identity")
        link_id = "link-" + uuid.uuid4().hex
        infinity = "9999-12-31T23:59:59.999999Z"
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            for key in (src_key, dst_key):
                if conn.execute(
                    """SELECT 1 FROM ontology_object_refs
                       WHERE project_id=? AND pack_fingerprint=? AND type_id=? AND type_version=? AND import_id=? AND record_key=?""",
                    (self.project_id, pack_fingerprint, *key),
                ).fetchone() is None:
                    raise OntologyError("link endpoint is not materialized in the exact import")
            if supersedes_link_id:
                old = conn.execute(
                    "SELECT link_type_id, link_type_version FROM ontology_links WHERE project_id=? AND pack_fingerprint=? AND link_id=?",
                    (self.project_id, pack_fingerprint, supersedes_link_id),
                ).fetchone()
                if old is None or (old["link_type_id"], old["link_type_version"]) != (link_type_id, link_type_version):
                    raise OntologyError("superseded link does not match this project, pack, and type")
                if conn.execute("SELECT 1 FROM ontology_links WHERE supersedes_link_id=?", (supersedes_link_id,)).fetchone():
                    raise OntologyError("link already has a successor")
            rows = conn.execute(
                """SELECT l.link_id, l.source_type_id, l.source_type_version, l.source_import_id, l.source_record_key,
                          l.target_type_id, l.target_type_version, l.target_import_id, l.target_record_key, l.valid_from, l.valid_to
                   FROM ontology_links l
                   WHERE l.project_id=? AND l.pack_fingerprint=? AND l.link_type_id=? AND l.link_type_version=?
                     AND NOT EXISTS (SELECT 1 FROM ontology_links n WHERE n.supersedes_link_id=l.link_id)""",
                (self.project_id, pack_fingerprint, link_type_id, link_type_version),
            ).fetchall()
            for row in rows:
                if row["link_id"] == supersedes_link_id:
                    continue
                if not (start < (row["valid_to"] or infinity) and row["valid_from"] < (end or infinity)):
                    continue
                old_src = (row["source_type_id"], row["source_type_version"], row["source_import_id"], row["source_record_key"])
                old_dst = (row["target_type_id"], row["target_type_version"], row["target_import_id"], row["target_record_key"])
                if link_type.cardinality == "one_to_one" and (src_key == old_src or dst_key == old_dst):
                    raise OntologyError("link violates one_to_one cardinality over overlapping valid time")
                if link_type.cardinality == "one_to_many" and dst_key == old_dst:
                    raise OntologyError("link violates one_to_many cardinality over overlapping valid time")
            conn.execute(
                """INSERT INTO ontology_links(
                    link_id, project_id, pack_fingerprint, link_type_id, link_type_version,
                    source_type_id, source_type_version, source_import_id, source_record_key,
                    target_type_id, target_type_version, target_import_id, target_record_key,
                    valid_from, valid_to, created_at, actor_id, reason, provenance_json, supersedes_link_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (link_id, self.project_id, pack_fingerprint, link_type_id, link_type_version,
                 *src_key, *dst_key, start, end, _link_created_now(), decision["subject_id"],
                 reason.strip(), provenance_json, supersedes_link_id),
            )
            conn.commit()
        except (sqlite3.Error, OntologyError):
            conn.rollback()
            raise
        finally:
            conn.close()
        return link_id

    def add_link(
        self, pack_fingerprint: str, link_type_id: str, link_type_version: str,
        source: Mapping[str, Any], target: Mapping[str, Any], valid_from: str | datetime,
        valid_to: str | datetime | None, reason: str, provenance: Mapping[str, Any],
        *, policy: PolicyCallable | None, audit: Any | None,
    ) -> str:
        """Create an immutable relationship between exact imported objects."""
        return self._write_link(
            pack_fingerprint, link_type_id, link_type_version, source, target,
            valid_from, valid_to, reason, provenance, policy=policy, audit=audit,
        )

    def supersede_link(
        self, pack_fingerprint: str, link_id: str, source: Mapping[str, Any],
        target: Mapping[str, Any], valid_from: str | datetime, valid_to: str | datetime | None,
        reason: str, provenance: Mapping[str, Any], *, policy: PolicyCallable | None, audit: Any | None,
    ) -> str:
        """Append a correction and retain the original link unchanged."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT link_type_id, link_type_version FROM ontology_links WHERE project_id=? AND pack_fingerprint=? AND link_id=?",
                (self.project_id, pack_fingerprint, link_id),
            ).fetchone()
            if row is None:
                raise OntologyError("link to supersede was not found")
            link_type_id, version = row["link_type_id"], row["link_type_version"]
        finally:
            conn.close()
        return self._write_link(
            pack_fingerprint, link_type_id, version, source, target, valid_from, valid_to,
            reason, provenance, policy=policy, audit=audit, supersedes_link_id=link_id,
        )

    def get_links(
        self, pack_fingerprint: str, link_type_id: str, link_type_version: str, *,
        source: Mapping[str, Any] | None = None, target: Mapping[str, Any] | None = None,
        include_superseded: bool = False, policy: PolicyCallable | None, audit: Any | None,
    ) -> list[dict[str, Any]]:
        """List link records for one exact pack and link-type version."""
        pack = self.get_pack(pack_fingerprint, policy=policy, audit=audit)
        self._link_type(pack, link_type_id, link_type_version)
        src = self._canonical_endpoint(source, self.project_id, pack_fingerprint) if source is not None else None
        dst = self._canonical_endpoint(target, self.project_id, pack_fingerprint) if target is not None else None
        clauses = ["l.project_id=?", "l.pack_fingerprint=?", "l.link_type_id=?", "l.link_type_version=?"]
        params: list[Any] = [self.project_id, pack_fingerprint, link_type_id, link_type_version]
        for side, endpoint in (("source", src), ("target", dst)):
            if endpoint:
                clauses.extend([f"l.{side}_type_id=?", f"l.{side}_type_version=?", f"l.{side}_import_id=?", f"l.{side}_record_key=?"])
                params.extend(self._link_key(endpoint))
        if not include_superseded:
            clauses.append("NOT EXISTS (SELECT 1 FROM ontology_links n WHERE n.supersedes_link_id=l.link_id)")
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT l.* FROM ontology_links l WHERE " + " AND ".join(clauses) + " ORDER BY l.valid_from, l.link_id LIMIT 101",
                params,
            ).fetchall()
            if len(rows) > 100:
                raise OntologyError("use traverse_links pagination for link sets larger than 100")
            self._authorize("ontology_read", [pack_fingerprint, link_type_id, link_type_version], policy=policy, audit=audit)
            sensitivities = []
            for row in rows:
                for side in ("source", "target"):
                    key = (row[side + "_type_id"], row[side + "_type_version"],
                           row[side + "_import_id"], row[side + "_record_key"])
                    ref = conn.execute(
                        """SELECT property_sensitivity_json FROM ontology_object_refs
                           WHERE project_id=? AND pack_fingerprint=? AND type_id=? AND type_version=?
                             AND import_id=? AND record_key=?""",
                        (self.project_id, pack_fingerprint, *key),
                    ).fetchone()
                    if ref:
                        stored = json.loads(ref["property_sensitivity_json"])
                        if isinstance(stored, dict):
                            sensitivities.extend(v for v in stored.values() if isinstance(v, str))
            rank = {"public": 0, "internal": 1, "personal": 2, "sensitive": 3}
            sensitivity = max((v for v in sensitivities if v in rank), key=rank.__getitem__, default="internal")
            self._authorize(
                "ontology_read", [pack_fingerprint, link_type_id, link_type_version],
                policy=policy, audit=audit, sensitivity=sensitivity,
            )
            return [{
                "link_id": row["link_id"], "pack_fingerprint": pack_fingerprint,
                "link_type_id": link_type_id, "link_type_version": link_type_version,
                "source": {"project_id": self.project_id, "pack_fingerprint": pack_fingerprint,
                           "type_id": row["source_type_id"], "type_version": row["source_type_version"],
                           "import_id": row["source_import_id"], "record_key": row["source_record_key"]},
                "target": {"project_id": self.project_id, "pack_fingerprint": pack_fingerprint,
                           "type_id": row["target_type_id"], "type_version": row["target_type_version"],
                           "import_id": row["target_import_id"], "record_key": row["target_record_key"]},
                "valid_from": row["valid_from"], "valid_to": row["valid_to"], "created_at": row["created_at"],
                "actor_id": row["actor_id"], "reason": row["reason"],
                "provenance": json.loads(row["provenance_json"]), "supersedes_link_id": row["supersedes_link_id"],
            } for row in rows]
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise OntologyError("ontology link records could not be read") from exc
        finally:
            conn.close()


    @staticmethod
    def _check_page_size(page_size: int) -> None:
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
            raise OntologyError("page_size must be an integer from 1 to 100")

    @staticmethod
    def _validate_filter_value(prop: Any, value: Any) -> None:
        if value is None:
            if not prop.nullable:
                raise OntologyError("null filter value is not allowed for this property")
            return
        kind = prop.data_type
        valid = (
            isinstance(value, str) if kind in {"string", "identifier", "enum", "date", "timestamp"}
            else isinstance(value, int) and not isinstance(value, bool) if kind == "integer"
            else isinstance(value, (int, float)) and not isinstance(value, bool) if kind == "decimal"
            else isinstance(value, bool) if kind == "boolean"
            else isinstance(value, (dict, list)) if kind == "structured_object"
            else False
        )
        if not valid:
            raise OntologyError(f"filter value does not match property type {kind}")
        if kind == "enum" and prop.allowed_values and value not in prop.allowed_values:
            raise OntologyError("enum filter value is not allowed by the property definition")

    @classmethod
    def _validate_filters(cls, pack: OntologyPack, type_id: str, filters: Mapping[str, Any]) -> list[tuple[str, str, Any]]:
        obj = next((item for item in pack.object_types if item.type_id == type_id), None)
        if obj is None:
            raise OntologyError("unknown object type")
        properties = {item.property_id: item for item in pack.property_types}
        allowed_properties = set(obj.properties)
        if not isinstance(filters, Mapping):
            raise OntologyError("filters must map property IDs to typed filter objects")
        checked = []
        allowed_ops = {"eq", "in", "gt", "gte", "lt", "lte", "contains"}
        for property_id, spec in filters.items():
            if property_id not in allowed_properties or property_id not in properties:
                raise OntologyError("filter references an unknown property for this object type")
            if not isinstance(spec, Mapping) or set(spec) != {"op", "value"}:
                raise OntologyError("each filter must contain exactly op and value")
            op, value, prop = spec["op"], spec["value"], properties[property_id]
            if not isinstance(op, str) or op not in allowed_ops:
                raise OntologyError("unsupported ontology filter operator")
            if op in {"gt", "gte", "lt", "lte"} and prop.data_type not in {"string", "identifier", "date", "timestamp", "integer", "decimal"}:
                raise OntologyError("ordering is not supported for this property type")
            if op == "contains" and (prop.data_type != "string" or value is None):
                raise OntologyError("contains requires a non-null value and a string property")
            if op == "in":
                if not isinstance(value, list) or not value or len(value) > 100:
                    raise OntologyError("in requires a list of 1 to 100 typed values")
                for item in value:
                    cls._validate_filter_value(prop, item)
            else:
                cls._validate_filter_value(prop, value)
            checked.append((property_id, op, value))
        return checked

    @staticmethod
    def _matches_filters(values: Mapping[str, Any], filters: list[tuple[str, str, Any]]) -> bool:
        for property_id, op, expected in filters:
            actual = values.get(property_id)
            if op == "eq":
                matched = _canonical(actual) == _canonical(expected)
            elif op == "in":
                matched = any(_canonical(actual) == _canonical(item) for item in expected)
            elif actual is None:
                matched = False
            elif op == "contains":
                matched = expected in actual
            elif op == "gt":
                matched = actual > expected
            elif op == "gte":
                matched = actual >= expected
            elif op == "lt":
                matched = actual < expected
            else:
                matched = actual <= expected
            if not matched:
                return False
        return True

    def query_objects(
        self, pack_fingerprint: str, type_id: str, type_version: str, import_id: str,
        filters: Mapping[str, Any], page_size: int, cursor: str | None, *,
        policy: PolicyCallable | None, audit: Any | None,
        purpose: str | None = None, retention: str | None = None,
    ) -> dict[str, Any]:
        """Return a bounded keyset page of exact-import source-backed objects."""
        if not isinstance(import_id, str) or not import_id.strip() or import_id == "latest":
            raise OntologyError("query requires an explicit import_id")
        self._check_page_size(page_size)
        pack = self.get_pack(pack_fingerprint, policy=policy, audit=audit)
        if not any(item.type_id == type_id and item.version == type_version for item in pack.object_types):
            raise OntologyError("object type/version does not resolve in selected pack")
        checked_filters = self._validate_filters(pack, type_id, filters)
        filter_fingerprint = hashlib.sha256(_canonical(dict(filters)).encode("utf-8")).hexdigest()
        cursor_value = _decode_cursor(cursor)
        last_key = None
        if cursor_value is not None:
            expected = {
                "v": 1, "project_id": self.project_id, "pack": pack_fingerprint,
                "type_id": type_id, "type_version": type_version, "import_id": import_id,
                "filters": filter_fingerprint,
            }
            if any(cursor_value.get(key) != value for key, value in expected.items()) or not isinstance(cursor_value.get("last_key"), str):
                raise OntologyError("query cursor does not match this project, type, import, and filter")
            last_key = cursor_value["last_key"]
        max_scan = min(10000, max(1000, page_size * 100))
        conn = self._connect()
        try:
            if last_key is None:
                rows = conn.execute(
                    """SELECT record_key FROM ontology_object_refs
                       WHERE project_id=? AND pack_fingerprint=? AND type_id=? AND type_version=? AND import_id=?
                       ORDER BY record_key LIMIT ?""",
                    (self.project_id, pack_fingerprint, type_id, type_version, import_id, max_scan),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT record_key FROM ontology_object_refs
                       WHERE project_id=? AND pack_fingerprint=? AND type_id=? AND type_version=?
                         AND import_id=? AND record_key>?
                       ORDER BY record_key LIMIT ?""",
                    (self.project_id, pack_fingerprint, type_id, type_version, import_id, last_key, max_scan),
                ).fetchall()
        finally:
            conn.close()
        results = []
        scanned_key = last_key
        for row in rows:
            scanned_key = row["record_key"]
            instance = self.get_object(
                pack_fingerprint, type_id, type_version, scanned_key, import_id,
                policy=policy, audit=audit, purpose=purpose, retention=retention,
            )
            if self._matches_filters(instance["property_values"], checked_filters):
                results.append(instance)
                if len(results) >= page_size:
                    break
        more = False
        if scanned_key is not None:
            conn = self._connect()
            try:
                more = conn.execute(
                    """SELECT 1 FROM ontology_object_refs
                       WHERE project_id=? AND pack_fingerprint=? AND type_id=? AND type_version=?
                         AND import_id=? AND record_key>? LIMIT 1""",
                    (self.project_id, pack_fingerprint, type_id, type_version, import_id, scanned_key),
                ).fetchone() is not None
            finally:
                conn.close()
        next_cursor = None
        if more:
            next_cursor = _encode_cursor({
                "v": 1, "project_id": self.project_id, "pack": pack_fingerprint,
                "type_id": type_id, "type_version": type_version, "import_id": import_id,
                "filters": filter_fingerprint, "last_key": scanned_key,
            })
        return {"objects": results, "next_cursor": next_cursor}

    @staticmethod
    def _link_result(row: sqlite3.Row, project_id: str, pack_fingerprint: str) -> dict[str, Any]:
        return {
            "link_id": row["link_id"], "pack_fingerprint": pack_fingerprint,
            "link_type_id": row["link_type_id"], "link_type_version": row["link_type_version"],
            "source": {"project_id": project_id, "pack_fingerprint": pack_fingerprint,
                       "type_id": row["source_type_id"], "type_version": row["source_type_version"],
                       "import_id": row["source_import_id"], "record_key": row["source_record_key"]},
            "target": {"project_id": project_id, "pack_fingerprint": pack_fingerprint,
                       "type_id": row["target_type_id"], "type_version": row["target_type_version"],
                       "import_id": row["target_import_id"], "record_key": row["target_record_key"]},
            "valid_from": row["valid_from"], "valid_to": row["valid_to"], "created_at": row["created_at"],
            "actor_id": row["actor_id"], "reason": row["reason"],
            "provenance": json.loads(row["provenance_json"]), "supersedes_link_id": row["supersedes_link_id"],
        }

    def traverse_links(
        self, pack_fingerprint: str, link_type_id: str, link_type_version: str,
        endpoint: Mapping[str, Any], import_id: str, page_size: int, cursor: str | None, *,
        direction: str = "both", policy: PolicyCallable | None, audit: Any | None,
    ) -> dict[str, Any]:
        """Return a bounded adjacent-link page for one exact endpoint import."""
        self._check_page_size(page_size)
        if direction not in {"out", "in", "both"}:
            raise OntologyError("direction must be out, in, or both")
        ref = self._canonical_endpoint(endpoint, self.project_id, pack_fingerprint)
        if import_id != ref["import_id"] or import_id == "latest":
            raise OntologyError("traversal import_id must match the exact endpoint reference")
        pack = self.get_pack(pack_fingerprint, policy=policy, audit=audit)
        self._link_type(pack, link_type_id, link_type_version)
        cursor_value = _decode_cursor(cursor)
        last_id = None
        as_of = _link_created_now()
        if cursor_value is not None:
            as_of = cursor_value.get("as_of")
            if not isinstance(as_of, str) or _canonical_timestamp(as_of, "cursor time") != as_of:
                raise OntologyError("traversal cursor time is invalid")
        cursor_identity = {
            "v": 1, "project_id": self.project_id, "pack": pack_fingerprint,
            "link_type_id": link_type_id, "link_type_version": link_type_version,
            "endpoint": dict(ref), "import_id": import_id, "direction": direction, "as_of": as_of,
        }
        if cursor_value is not None:
            if any(cursor_value.get(key) != value for key, value in cursor_identity.items()) or not isinstance(cursor_value.get("last_id"), str):
                raise OntologyError("traversal cursor does not match this endpoint and link selection")
            last_id = cursor_value["last_id"]
        self._authorize("ontology_read", [pack_fingerprint, link_type_id, link_type_version, *self._link_key(ref)], policy=policy, audit=audit)
        if direction == "out":
            match = "source"
        elif direction == "in":
            match = "target"
        else:
            match = "both"
        conn = self._connect()
        try:
            if match == "both":
                rows = conn.execute(
                    """SELECT l.* FROM ontology_links l WHERE l.project_id=? AND l.pack_fingerprint=?
                       AND l.link_type_id=? AND l.link_type_version=? AND l.created_at<=? AND l.link_id>?
                       AND ((l.source_type_id=? AND l.source_type_version=? AND l.source_import_id=? AND l.source_record_key=?)
                         OR (l.target_type_id=? AND l.target_type_version=? AND l.target_import_id=? AND l.target_record_key=?))
                       ORDER BY l.link_id LIMIT ?""",
                    (self.project_id, pack_fingerprint, link_type_id, link_type_version, as_of, last_id or "",
                     *self._link_key(ref), *self._link_key(ref), page_size + 1),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT l.* FROM ontology_links l WHERE l.project_id=? AND l.pack_fingerprint=?
                       AND l.link_type_id=? AND l.link_type_version=? AND l.created_at<=? AND l.link_id>?
                       AND l.""" + match + """_type_id=? AND l.""" + match + """_type_version=?
                       AND l.""" + match + """_import_id=? AND l.""" + match + """_record_key=?
                       ORDER BY l.link_id LIMIT ?""",
                    (self.project_id, pack_fingerprint, link_type_id, link_type_version, as_of, last_id or "",
                     *self._link_key(ref), page_size + 1),
                ).fetchall()
            page = rows[:page_size]
            sensitivities = []
            for row in page:
                for side in ("source", "target"):
                    key = (row[side + "_type_id"], row[side + "_type_version"],
                           row[side + "_import_id"], row[side + "_record_key"])
                    ref_row = conn.execute(
                        """SELECT property_sensitivity_json FROM ontology_object_refs
                           WHERE project_id=? AND pack_fingerprint=? AND type_id=? AND type_version=?
                             AND import_id=? AND record_key=?""",
                        (self.project_id, pack_fingerprint, *key),
                    ).fetchone()
                    if ref_row:
                        stored = json.loads(ref_row["property_sensitivity_json"])
                        if isinstance(stored, dict):
                            sensitivities.extend(v for v in stored.values() if isinstance(v, str))
            rank = {"public": 0, "internal": 1, "personal": 2, "sensitive": 3}
            sensitivity = max((v for v in sensitivities if v in rank), key=rank.__getitem__, default="internal")
            self._authorize(
                "ontology_read", [pack_fingerprint, link_type_id, link_type_version, *self._link_key(ref)],
                policy=policy, audit=audit, sensitivity=sensitivity,
            )
            next_cursor = None
            if len(rows) > page_size and page:
                next_cursor = _encode_cursor({**cursor_identity, "last_id": page[-1]["link_id"]})
            return {"links": [self._link_result(row, self.project_id, pack_fingerprint) for row in page],
                    "next_cursor": next_cursor}
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise OntologyError("ontology link traversal failed") from exc
        finally:
            conn.close()


    @staticmethod
    def _verify_connection_integrity(conn: sqlite3.Connection) -> dict[str, Any]:
        """Verify local SQLite structure and ontology metadata without reading source snapshots."""
        integrity = [row[0] for row in conn.execute("PRAGMA integrity_check").fetchall()]
        if integrity != ["ok"]:
            raise OntologyError("ontology SQLite integrity check failed")
        foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchmany(1)
        if foreign_key_errors:
            raise OntologyError("ontology store contains broken foreign-key references")

        migrations = (
            (1, _SCHEMA_CHECKSUM, _STORE_SCHEMA),
            (2, _OBJECT_REFS_CHECKSUM, _OBJECT_REFS_SCHEMA),
            (3, _LINKS_CHECKSUM, _LINKS_SCHEMA),
        )
        actual = [
            (int(row["version"]), row["checksum"])
            for row in conn.execute("SELECT version, checksum FROM schema_migrations ORDER BY version")
        ]
        expected = [(version, checksum) for version, checksum, _ in migrations]
        if actual != expected:
            raise OntologyError("ontology store migration history is unknown or incomplete")

        packs = conn.execute("SELECT fingerprint, pack_id, schema_version, content_json FROM ontology_packs")
        for row in packs:
            try:
                pack = parse_domain_pack(json.loads(row["content_json"]))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise OntologyError("ontology pack content is not valid") from exc
            if (
                pack.fingerprint != row["fingerprint"]
                or pack.pack_id != row["pack_id"]
                or pack.schema_version != row["schema_version"]
            ):
                raise OntologyError("ontology pack fingerprint or metadata does not match its content")

        bindings = conn.execute("SELECT fingerprint, content_json FROM bindings")
        for row in bindings:
            try:
                binding = load_binding(json.loads(row["content_json"]))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise OntologyError("ontology binding content is not valid") from exc
            if binding.fingerprint != row["fingerprint"]:
                raise OntologyError("ontology binding fingerprint does not match its content")

        refs = conn.execute(
            "SELECT file_sha256, source_locator_json, property_sensitivity_json FROM ontology_object_refs"
        )
        for row in refs:
            digest = row["file_sha256"]
            if not isinstance(digest, str) or len(digest) != 64 or any(
                char not in "0123456789abcdefABCDEF" for char in digest
            ):
                raise OntologyError("ontology object reference has an invalid source SHA-256")
            try:
                locator = json.loads(row["source_locator_json"])
                sensitivity = json.loads(row["property_sensitivity_json"])
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise OntologyError("ontology object reference metadata is not valid JSON") from exc
            if not isinstance(locator, dict) or not isinstance(sensitivity, dict):
                raise OntologyError("ontology object reference metadata has an invalid shape")

        links = conn.execute(
            "SELECT valid_from, valid_to, created_at, actor_id, reason, provenance_json FROM ontology_links"
        )
        for row in links:
            start = _canonical_timestamp(row["valid_from"], "valid_from")
            end = _canonical_timestamp(row["valid_to"], "valid_to") if row["valid_to"] is not None else None
            _canonical_timestamp(row["created_at"], "created_at")
            if end is not None and end <= start:
                raise OntologyError("ontology link has an invalid validity interval")
            if not isinstance(row["actor_id"], str) or not row["actor_id"].strip():
                raise OntologyError("ontology link has no actor identity")
            if not isinstance(row["reason"], str) or not row["reason"].strip():
                raise OntologyError("ontology link has no reason")
            try:
                provenance = json.loads(row["provenance_json"])
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise OntologyError("ontology link provenance is not valid JSON") from exc
            if not isinstance(provenance, dict):
                raise OntologyError("ontology link provenance has an invalid shape")
            kind = provenance.get("kind")
            if kind not in {"source", "manual_assertion", "derived"}:
                raise OntologyError("ontology link provenance kind is invalid")
            if kind == "source":
                source_refs = provenance.get("source_refs")
                if not isinstance(source_refs, list) or not source_refs:
                    raise OntologyError("source-backed link provenance has no source references")
                for ref in source_refs:
                    if not isinstance(ref, Mapping) or not all(
                        isinstance(ref.get(key), str) and ref[key].strip()
                        for key in ("import_id", "file_sha256", "locator")
                    ):
                        raise OntologyError("source-backed link provenance reference is incomplete")
                    digest = ref["file_sha256"]
                    if len(digest) != 64 or any(char not in "0123456789abcdefABCDEF" for char in digest):
                        raise OntologyError("source-backed link provenance has an invalid SHA-256")

        return {
            "ok": True,
            "schema_version": actual[-1][0],
            "sqlite_integrity": "ok",
            "foreign_keys": "ok",
            "pack_fingerprints": "ok",
            "binding_fingerprints": "ok",
            "object_reference_metadata": "ok",
            "link_records": "ok",
            "source_snapshots": "not_checked",
            "audit_event_references": "not_stored",
        }

    def verify_integrity(
        self, *, policy: PolicyCallable | None, audit: Any | None,
    ) -> dict[str, Any]:
        """Check the local ontology database; external snapshot files are not opened."""
        self._authorize("ontology_read", ["store_integrity"], policy=policy, audit=audit)
        conn = self._connect()
        try:
            return self._verify_connection_integrity(conn)
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise OntologyError("ontology store integrity verification failed") from exc
        finally:
            conn.close()

    def backup(
        self, path: str | Path, *, policy: PolicyCallable | None, audit: Any | None,
    ) -> Path:
        """Create an atomic project-local SQLite backup and verify its local integrity."""
        self._authorize("ontology_read", ["store_backup"], policy=policy, audit=audit)
        destination = Path(path)
        temporary = destination.with_name(destination.name + ".tmp")
        source_conn = None
        backup_conn = None
        created_temporary = False
        try:
            require_safe_path(self.project)
            self.project.mkdir(parents=True, exist_ok=True)
            root = self.project.resolve()
            resolved_destination = destination.resolve()
            resolved_destination.relative_to(root)
            if resolved_destination == self.path.resolve():
                raise OntologyError("backup destination cannot be the live ontology database")
            require_safe_path(destination.parent)
            require_safe_path(destination)
            if destination.exists() or temporary.exists():
                raise OntologyError("backup destination already exists")
            destination.parent.mkdir(parents=True, exist_ok=True)
            require_safe_path(destination.parent)
            require_safe_path(temporary)
            source_conn = self._connect()
            backup_conn = sqlite3.connect(str(temporary), timeout=30.0)
            backup_conn.row_factory = sqlite3.Row
            created_temporary = True
            source_conn.backup(backup_conn)
            self._verify_connection_integrity(backup_conn)
            backup_conn.close()
            backup_conn = None
            source_conn.close()
            source_conn = None
            require_safe_path(temporary)
            temporary.replace(destination)
            created_temporary = False
            require_safe_path(destination)
            return destination
        except (OSError, sqlite3.Error, UnsafePathError, ValueError, OntologyError) as exc:
            if created_temporary and temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass
            if isinstance(exc, OntologyError):
                raise
            raise OntologyError("ontology store backup failed or did not pass verification") from exc
        finally:
            if backup_conn is not None:
                backup_conn.close()
            if source_conn is not None:
                source_conn.close()


    def _verify_source_snapshot_dependencies(self, ontology_conn: sqlite3.Connection) -> None:
        """Confirm every referenced import exists in this project's tabular snapshot DB.

        Only import metadata is read; no source row payloads are selected.
        """
        dependencies = [
            dict(row) for row in ontology_conn.execute(
                """SELECT DISTINCT import_id, dataset_id, schema_id, schema_version,
                          schema_fingerprint, source_registry_id, file_sha256
                   FROM ontology_object_refs"""
            )
        ]
        link_refs: dict[str, str] = {}
        for row in ontology_conn.execute("SELECT provenance_json FROM ontology_links"):
            provenance = json.loads(row["provenance_json"])
            if provenance.get("kind") != "source":
                continue
            for ref in provenance.get("source_refs", []):
                import_id, digest = ref.get("import_id"), ref.get("file_sha256")
                if isinstance(import_id, str) and isinstance(digest, str):
                    previous = link_refs.setdefault(import_id, digest.lower())
                    if previous != digest.lower():
                        raise OntologyError("backup contains conflicting hashes for one source import")
        if not dependencies and not link_refs:
            return
        snapshot_path = self.project / "data" / "tabular.sqlite3"
        try:
            require_safe_path(snapshot_path)
            if not snapshot_path.is_file():
                raise OntologyError("required tabular source snapshot database is missing")
            conn = sqlite3.connect(snapshot_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30.0)
            conn.row_factory = sqlite3.Row
        except (OSError, sqlite3.Error, UnsafePathError, ValueError) as exc:
            raise OntologyError("required tabular source snapshot database is unavailable") from exc
        try:
            for dependency in dependencies:
                row = conn.execute(
                    """SELECT dataset_id, source_registry_id, file_sha256, status, manifest_json
                       FROM imports WHERE import_id=?""",
                    (dependency["import_id"],),
                ).fetchone()
                if row is None or row["status"] != "committed":
                    raise OntologyError("a referenced source import is missing or not committed")
                try:
                    manifest = json.loads(row["manifest_json"])
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise OntologyError("a referenced source import manifest is invalid") from exc
                if not isinstance(manifest, dict):
                    raise OntologyError("a referenced source import manifest has an invalid shape")
                row_count = conn.execute(
                    "SELECT COUNT(*) FROM import_rows WHERE import_id=?",
                    (dependency["import_id"],),
                ).fetchone()[0]
                if type(manifest.get("accepted_records")) is not int or row_count != manifest["accepted_records"]:
                    raise OntologyError("a referenced source import is missing snapshot rows")
                if (
                    row["dataset_id"] != dependency["dataset_id"]
                    or row["source_registry_id"] != dependency["source_registry_id"]
                    or row["file_sha256"].lower() != dependency["file_sha256"].lower()
                    or manifest.get("schema_id") != dependency["schema_id"]
                    or manifest.get("schema_version") != dependency["schema_version"]
                    or manifest.get("schema_fingerprint") != dependency["schema_fingerprint"]
                ):
                    raise OntologyError("a referenced source import does not match its stored provenance")
            for import_id, digest in link_refs.items():
                row = conn.execute(
                    "SELECT file_sha256, status FROM imports WHERE import_id=?", (import_id,)
                ).fetchone()
                if row is None or row["status"] != "committed" or row["file_sha256"].lower() != digest:
                    raise OntologyError("a source-backed link references a missing or changed import")
        except (sqlite3.Error, TypeError, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, OntologyError):
                raise
            raise OntologyError("tabular source dependency verification failed") from exc
        finally:
            conn.close()

    def restore(
        self, backup_path: str | Path, *, policy: PolicyCallable | None, audit: Any | None,
    ) -> Path:
        """Restore a verified, project-local backup without overwriting an existing store.

        The destination is published only after a temporary SQLite copy passes the
        same integrity checks as a live store. Source tabular snapshots are not copied.
        """
        self._authorize("ontology_write", ["store_restore"], policy=policy, audit=audit)
        backup_file = Path(backup_path)
        temporary = self.path.with_name(self.path.name + ".restore-" + uuid.uuid4().hex + ".tmp")
        source_conn = None
        restore_conn = None
        created_temporary = False
        try:
            require_safe_path(self.project)
            self.project.mkdir(parents=True, exist_ok=True)
            root = self.project.resolve()
            resolved_backup = backup_file.resolve()
            resolved_backup.relative_to(root)
            if resolved_backup == self.path.resolve() or not backup_file.is_file():
                raise OntologyError("restore requires an existing project-local backup file")
            require_safe_path(backup_file)
            require_safe_path(self.path.parent)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            require_safe_path(temporary)
            if self.path.exists() or temporary.exists():
                raise OntologyError("restore destination already exists")
            source_conn = sqlite3.connect(resolved_backup.as_uri() + "?mode=ro", uri=True, timeout=30.0)
            source_conn.row_factory = sqlite3.Row
            self._verify_connection_integrity(source_conn)
            self._verify_source_snapshot_dependencies(source_conn)
            for table in ("ontology_object_refs", "ontology_links"):
                foreign_projects = source_conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE project_id<>?", (self.project_id,)
                ).fetchone()[0]
                if foreign_projects:
                    raise OntologyError("backup contains ontology records for a different project")
            restore_conn = sqlite3.connect(str(temporary), timeout=30.0)
            restore_conn.row_factory = sqlite3.Row
            created_temporary = True
            source_conn.backup(restore_conn)
            self._verify_connection_integrity(restore_conn)
            restore_conn.close()
            restore_conn = None
            source_conn.close()
            source_conn = None
            require_safe_path(temporary)
            # Hard-link publication is atomic and fails rather than replacing a
            # destination created concurrently after the initial existence check.
            os.link(temporary, self.path)
            temporary.unlink()
            created_temporary = False
            require_safe_path(self.path)
            return self.path
        except (OSError, sqlite3.Error, UnsafePathError, ValueError, OntologyError) as exc:
            if created_temporary and temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass
            if isinstance(exc, OntologyError):
                raise
            raise OntologyError("ontology restore failed or did not pass verification") from exc
        finally:
            if restore_conn is not None:
                restore_conn.close()
            if source_conn is not None:
                source_conn.close()

    def backup_dependency_manifest(
        self, backup_path: str | Path, *, policy: PolicyCallable | None, audit: Any | None,
    ) -> dict[str, Any]:
        """Describe exact external source dependencies without exporting row values."""
        self._authorize("ontology_read", ["store_backup_dependencies"], policy=policy, audit=audit)
        backup_file = Path(backup_path)
        try:
            require_safe_path(self.project)
            resolved_backup = backup_file.resolve()
            resolved_backup.relative_to(self.project.resolve())
        except (OSError, UnsafePathError, ValueError) as exc:
            raise OntologyError("ontology backup path is unsafe or unavailable") from exc
        if resolved_backup == self.path.resolve() or not backup_file.is_file():
            raise OntologyError("dependency manifest requires an existing backup file")
        try:
            require_safe_path(backup_file)
            backup_digest = hashlib.sha256()
            backup_bytes = 0
            with backup_file.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    backup_digest.update(chunk)
                    backup_bytes += len(chunk)
        except (OSError, UnsafePathError) as exc:
            raise OntologyError("ontology backup path is unsafe or unavailable") from exc
        conn = sqlite3.connect(backup_file.resolve().as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            self._verify_connection_integrity(conn)
            packs = [
                {
                    "fingerprint": row["fingerprint"],
                    "pack_id": row["pack_id"],
                    "schema_version": row["schema_version"],
                }
                for row in conn.execute(
                    "SELECT fingerprint, pack_id, schema_version FROM ontology_packs ORDER BY fingerprint"
                )
            ]
            bindings = [
                {
                    "pack_fingerprint": row["pack_fingerprint"],
                    "fingerprint": row["fingerprint"],
                    "binding_id": row["binding_id"],
                    "binding_version": row["binding_version"],
                }
                for row in conn.execute(
                    """SELECT pack_fingerprint, fingerprint, binding_id, binding_version
                       FROM bindings ORDER BY pack_fingerprint, fingerprint"""
                )
            ]
            dependencies = [
                {
                    "import_id": row["import_id"],
                    "dataset_id": row["dataset_id"],
                    "schema_id": row["schema_id"],
                    "schema_version": row["schema_version"],
                    "schema_fingerprint": row["schema_fingerprint"],
                    "source_registry_id": row["source_registry_id"],
                    "file_sha256": row["file_sha256"].lower(),
                }
                for row in conn.execute(
                    """SELECT DISTINCT import_id, dataset_id, schema_id, schema_version,
                              schema_fingerprint, source_registry_id, file_sha256
                       FROM ontology_object_refs
                       ORDER BY import_id, dataset_id, schema_id, schema_version,
                                schema_fingerprint, source_registry_id, file_sha256"""
                )
            ]
            link_source_references_by_key = {}
            for row in conn.execute("SELECT provenance_json FROM ontology_links ORDER BY link_id"):
                provenance = json.loads(row["provenance_json"])
                if provenance.get("kind") != "source":
                    continue
                for ref in provenance["source_refs"]:
                    reference = {
                        "import_id": ref["import_id"],
                        "file_sha256": ref["file_sha256"].lower(),
                        "locator": ref["locator"],
                    }
                    link_source_references_by_key[_canonical(reference)] = reference
            link_source_references = [
                link_source_references_by_key[key]
                for key in sorted(link_source_references_by_key)
            ]
            payload = {
                "format": "agora-ontology-backup-dependencies/v1",
                "project_id": self.project_id,
                "created_at": _utc_now(),
                "ontology_schema_version": 3,
                "packs": packs,
                "bindings": bindings,
                "ontology_backup": {
                    "file_name": backup_file.name,
                    "bytes": backup_bytes,
                    "sha256": backup_digest.hexdigest(),
                },
                "source_snapshot_files": dependencies,
                "link_source_references": link_source_references,
                "source_row_values_included": False,
            }
            digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
            return {**payload, "manifest_sha256": digest}
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise OntologyError("ontology backup dependency manifest could not be created") from exc
        finally:
            conn.close()
