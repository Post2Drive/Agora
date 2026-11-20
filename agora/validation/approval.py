"""Scenario-bound metadata required before a validation approval can be used."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .json_io import strict_json_load

SCOPE_FIELDS = ("domain", "use_case", "target", "population", "geography", "horizon")


def report_scope(project: str | Path, llm: Any) -> dict[str, Any]:
    """Load explicit owner-authored scope and bind it to exact scenario/model config.

    Geography and target are intentionally not inferred from free-text scenario
    context. The owner must provide validation/scope.json and bind its scenario hash.
    """
    root = Path(project)
    scenario_path = root / "scenario.yaml"
    scope_path = root / "validation" / "scope.json"
    if not scenario_path.is_file():
        raise PermissionError("Validated Prediction requires scenario.yaml")
    if not scope_path.is_file():
        raise PermissionError("Validated Prediction requires owner-authored validation/scope.json; scope is never inferred from free text")
    try:
        scope = strict_json_load(scope_path)
    except (OSError, ValueError) as exc:
        raise PermissionError(f"Cannot read validation/scope.json: {exc}") from exc
    if not isinstance(scope, dict):
        raise PermissionError("validation/scope.json must contain a JSON object")
    missing = [key for key in ("scenario_name", "scenario_sha256", *SCOPE_FIELDS)
               if not isinstance(scope.get(key), str) or not scope[key].strip()]
    if missing:
        raise PermissionError("validation/scope.json missing non-empty fields: " + ", ".join(missing))
    scenario_bytes = scenario_path.read_bytes()
    scenario_sha = hashlib.sha256(scenario_bytes).hexdigest()
    if scope["scenario_sha256"] != scenario_sha:
        raise PermissionError("Validation scope is bound to a different scenario.yaml SHA-256")
    from agora.scenario import load as load_scenario
    scenario = load_scenario(scenario_path)
    if scope["scenario_name"] != scenario.name:
        raise PermissionError("Validation scope scenario_name does not match scenario.yaml")
    if llm is None or not getattr(llm, "cfg", None):
        raise PermissionError("Validated Prediction requires an identified model configuration")
    cfg = llm.cfg
    model_version = f"{cfg.backend}:{cfg.model}"
    config_payload = {
        "scenario_sha256": scenario_sha,
        "backend": cfg.backend, "model": cfg.model, "url": cfg.url,
        "timeout": cfg.timeout, "parallel": cfg.parallel, "context": cfg.context,
        "allow_remote": cfg.allow_remote, "allow_blocked_models": cfg.allow_blocked_models,
        "cache": cfg.cache,
    }
    config_hash = hashlib.sha256(json.dumps(
        config_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()
    return {**{key: scope[key] for key in SCOPE_FIELDS},
            "scenario_name": scenario.name, "scenario_sha256": scenario_sha,
            "model_version": model_version, "config_hash": config_hash}
