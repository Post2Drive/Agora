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
from .binding import DataBinding, load_binding
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
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise OntologyError("ontology store migration failed") from exc
            return
        if len(rows) != 1 or rows[0]["version"] != 1 or rows[0]["checksum"] != _SCHEMA_CHECKSUM:
            raise OntologyError("ontology store schema is unknown or its migration checksum changed")
        expected = {"ontology_packs", "bindings"}
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
        binding = binding if isinstance(binding, DataBinding) else load_binding(binding)
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
