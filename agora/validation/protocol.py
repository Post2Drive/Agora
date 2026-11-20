"""Canonical, dataset-bound chronological holdout protocol.

The protocol is shared by validation checks and holdout evaluation. It prevents
future-dated records and configured group leakage from entering training, and
binds an evaluation to an identified dataset snapshot and source hashes when
those identities are supplied.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Mapping

from agora.sources.registry import ROLES as SOURCE_ROLES

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _get(record: Any, key: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(key, default)
    return getattr(record, key, default)


def _as_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise ValueError(f"Invalid {field_name}: expected ISO-8601 date") from exc
    raise ValueError(f"Invalid {field_name}: expected date or ISO-8601 string")


def _normalise_hashes(value: Mapping[str, str] | None) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("source_hashes must be a mapping of source IDs to SHA-256 hashes")
    result: dict[str, str] = {}
    for source_id, digest in value.items():
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_hashes contains an empty or invalid source ID")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ValueError(f"Invalid SHA-256 for source {source_id!r}")
        result[source_id] = digest
    return dict(sorted(result.items()))


@dataclass(frozen=True)
class HoldoutProtocol:
    protocol_id: str
    train_end: date
    test_start: date
    test_end: date
    minimum_train: int = 10
    minimum_test: int = 10
    grouping_key: str | None = "event_id"
    protocol_version: str = "1.0"
    dataset_id: str | None = None
    source_hashes: Mapping[str, str] = field(default_factory=dict)
    source_roles: Mapping[str, str] = field(default_factory=dict)
    baseline_id: str = "caller_supplied_baseline"
    baseline_description: str = "Baseline supplied by the evaluation caller"
    acceptance_thresholds: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "train_end", _as_date(self.train_end, field_name="train_end"))
        object.__setattr__(self, "test_start", _as_date(self.test_start, field_name="test_start"))
        object.__setattr__(self, "test_end", _as_date(self.test_end, field_name="test_end"))
        if not isinstance(self.protocol_id, str) or not self.protocol_id.strip():
            raise ValueError("protocol_id must be a non-empty string")
        if not isinstance(self.protocol_version, str) or not self.protocol_version.strip():
            raise ValueError("protocol_version must be a non-empty string")
        if self.test_start <= self.train_end:
            raise ValueError("test_start must be after train_end")
        if self.test_end < self.test_start:
            raise ValueError("test_end must not precede test_start")
        if isinstance(self.minimum_train, bool) or not isinstance(self.minimum_train, int) or self.minimum_train < 1:
            raise ValueError("minimum_train must be a positive integer")
        if isinstance(self.minimum_test, bool) or not isinstance(self.minimum_test, int) or self.minimum_test < 1:
            raise ValueError("minimum_test must be a positive integer")
        if self.grouping_key is not None and (not isinstance(self.grouping_key, str) or not self.grouping_key.strip()):
            raise ValueError("grouping_key must be a non-empty string or None")
        if self.dataset_id is not None and (not isinstance(self.dataset_id, str) or not self.dataset_id.strip()):
            raise ValueError("dataset_id must be a non-empty string when provided")
        if not isinstance(self.baseline_id, str) or not self.baseline_id.strip():
            raise ValueError("baseline_id must be a non-empty string")
        if not isinstance(self.baseline_description, str) or not self.baseline_description.strip():
            raise ValueError("baseline_description must be a non-empty string")
        if not isinstance(self.acceptance_thresholds, Mapping):
            raise TypeError("acceptance_thresholds must be a mapping")
        thresholds = {}
        for metric, rule in self.acceptance_thresholds.items():
            if not isinstance(metric, str) or not metric.strip() or not isinstance(rule, Mapping):
                raise ValueError("Each acceptance threshold must map a metric name to a rule")
            operator, value = rule.get("operator"), rule.get("value")
            if operator not in {"min", "max"} or isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Invalid acceptance threshold for {metric!r}")
            if not math.isfinite(float(value)):
                raise ValueError(f"Acceptance threshold for {metric!r} must be finite")
            thresholds[metric] = {"operator": operator, "value": float(value)}
        object.__setattr__(self, "acceptance_thresholds", thresholds)
        normalised_hashes = _normalise_hashes(self.source_hashes)
        if not isinstance(self.source_roles, Mapping):
            raise TypeError("source_roles must be a mapping of source IDs to data roles")
        allowed_roles = SOURCE_ROLES
        roles = dict(self.source_roles)
        if any(not isinstance(key, str) or not key.strip() or value not in allowed_roles
               for key, value in roles.items()):
            raise ValueError("source_roles contains an invalid source ID or data role")
        if roles and set(roles) != set(normalised_hashes):
            raise ValueError("source_roles must cover exactly the source IDs in source_hashes")
        object.__setattr__(self, "source_hashes", normalised_hashes)
        object.__setattr__(self, "source_roles", dict(sorted(roles.items())))

    def identity(self) -> dict[str, Any]:
        """Stable protocol identity, suitable for storing with evaluation evidence."""
        payload = {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "train_end": self.train_end.isoformat(),
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
            "minimum_train": self.minimum_train,
            "minimum_test": self.minimum_test,
            "grouping_key": self.grouping_key,
            "dataset_id": self.dataset_id,
            "source_hashes": dict(self.source_hashes),
            "source_roles": dict(self.source_roles),
            "baseline_id": self.baseline_id,
            "baseline_description": self.baseline_description,
            "acceptance_thresholds": dict(self.acceptance_thresholds),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return {**payload, "protocol_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}

    def _check_identity(self, dataset_id: str | None, source_hashes: Mapping[str, str] | None) -> dict[str, Any]:
        supplied_hashes = _normalise_hashes(source_hashes)
        if self.dataset_id is not None and dataset_id != self.dataset_id:
            raise ValueError("dataset_id does not match the pre-registered holdout protocol")
        if self.source_hashes and source_hashes is None:
            raise ValueError("source_hashes are required by the pre-registered holdout protocol")
        if self.source_hashes and supplied_hashes != dict(self.source_hashes):
            raise ValueError("source_hashes do not match the pre-registered holdout protocol")
        return {"dataset_id": dataset_id or self.dataset_id, "source_hashes": supplied_hashes or dict(self.source_hashes)}

    def partition(
        self,
        records: Iterable[Any],
        *,
        dataset_id: str | None = None,
        source_hashes: Mapping[str, str] | None = None,
    ) -> tuple[list[Any], list[Any], dict[str, Any]]:
        """Validate identities and return isolated train/test rows plus evidence."""
        identity = self._check_identity(dataset_id, source_hashes)
        rows = list(records)
        dated: list[tuple[date, Any]] = []
        seen_ids: set[str] = set()
        for index, row in enumerate(rows):
            raw_date = _get(row, "date", _get(row, "when"))
            row_date = _as_date(raw_date, field_name=f"record[{index}].date")
            record_id = _get(row, "record_id")
            if record_id is not None:
                if not isinstance(record_id, str) or not record_id.strip():
                    raise ValueError(f"Invalid record_id at record {index}")
                if record_id in seen_ids:
                    raise ValueError(f"Duplicate record_id: {record_id}")
                seen_ids.add(record_id)
            dated.append((row_date, row))

        if self.source_roles:
            for row_date, row in dated:
                source_id = _get(row, "source_id")
                if source_id not in self.source_roles:
                    raise ValueError("Every record must reference a source_id covered by the protocol source_roles")
                registered_role = self.source_roles[source_id]
                row_role = _get(row, "data_role")
                if row_role is not None and row_role != registered_role:
                    raise ValueError(f"Record data_role conflicts with registered role for source {source_id!r}")
                if row_date <= self.train_end and registered_role != "calibration":
                    raise ValueError("Only calibration-role sources may enter the training partition")
                if self.test_start <= row_date <= self.test_end and registered_role not in {"validation", "sealed_holdout"}:
                    raise ValueError("Only validation or sealed_holdout sources may enter the test partition")

        train = [row for day, row in dated if day <= self.train_end]
        test = [row for day, row in dated if self.test_start <= day <= self.test_end]
        if len(train) < self.minimum_train:
            raise ValueError(f"Insufficient training records: {len(train)} < {self.minimum_train}")
        if len(test) < self.minimum_test:
            raise ValueError(f"Insufficient holdout records: {len(test)} < {self.minimum_test}")

        if self.grouping_key is not None:
            train_groups: set[Any] = set()
            test_groups: set[Any] = set()
            for partition_name, partition_rows, target in (
                ("training", train, train_groups), ("holdout", test, test_groups)
            ):
                for index, row in enumerate(partition_rows):
                    group = _get(row, self.grouping_key)
                    if group is None or (isinstance(group, str) and not group.strip()):
                        raise ValueError(
                            f"Missing grouping key {self.grouping_key!r} in {partition_name} record"
                        )
                    try:
                        target.add(group)
                    except TypeError as exc:
                        raise ValueError(f"Unhashable grouping key {self.grouping_key!r}") from exc
            overlap = train_groups & test_groups
            if overlap:
                raise ValueError(f"Group leakage detected for {self.grouping_key!r}: {sorted(map(str, overlap))[:5]}")

        protocol_identity = self.identity()
        summary = {
            **protocol_identity,
            **identity,
            "n_total": len(rows),
            "n_train": len(train),
            "n_test": len(test),
            "train_start": min((_as_date(_get(r, "date", _get(r, "when")), field_name="date") for r in train)).isoformat(),
            "train_end_observed": max((_as_date(_get(r, "date", _get(r, "when")), field_name="date") for r in train)).isoformat(),
            "test_start_observed": min((_as_date(_get(r, "date", _get(r, "when")), field_name="date") for r in test)).isoformat(),
            "test_end_observed": max((_as_date(_get(r, "date", _get(r, "when")), field_name="date") for r in test)).isoformat(),
            "grouping_key": self.grouping_key,
            "group_leakage_checked": self.grouping_key is not None,
        }
        return train, test, summary

    def validate(
        self,
        records: Iterable[Any],
        *,
        dataset_id: str | None = None,
        source_hashes: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Validate without exposing the train/test rows."""
        _, _, summary = self.partition(records, dataset_id=dataset_id, source_hashes=source_hashes)
        return summary
