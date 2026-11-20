"""Stable identity primitives shared by ingestion and ontology code."""

from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Any


class IdentityError(ValueError):
    """Raised when a stable identity cannot be computed safely."""


def stable_record_key(dataset_identity: str, primary_key_value: Any) -> str:
    """Return a versioned key independent of snapshots and mutable row fields."""
    if not isinstance(dataset_identity, str) or not dataset_identity.strip():
        raise IdentityError("dataset_identity must be a non-empty string")
    if type(primary_key_value) not in (str, int, float, bool):
        raise IdentityError("primary_key_value must be a non-null scalar")
    if isinstance(primary_key_value, float) and not math.isfinite(primary_key_value):
        raise IdentityError("primary_key_value must be finite")

    try:
        payload = json.dumps(
            {
                "dataset_identity": dataset_identity.strip(),
                "primary_key": primary_key_value,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise IdentityError("identity values are not canonically serializable") from exc
    digest = sha256(b"agora-record-v1\0" + payload).hexdigest()
    return f"agora-record-v1:{digest}"
