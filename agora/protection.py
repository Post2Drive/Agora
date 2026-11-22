"""Protected-by-default switches.

Governed entry points (import, binding, scenario input, approval, outcome
record/review) always require a policy and an anchored audit writer. Callers
have no keyword to opt out. The two module flags below exist ONLY so the test
suite can build legacy unprotected fixtures; production code never sets them,
and there is no environment variable or CLI flag that does. tests/conftest.py
resets them for every test and ``tests/test_protected_defaults.py`` proves the
protected values hold.
"""
from __future__ import annotations

POLICY_REQUIRED = True
ANCHOR_REQUIRED = True
LEGACY_APPROVE_ENABLED = False
PRINCIPAL_BOUND_REQUIRED = True
# Governed enforce_policy() rejects any policy callable that is not a
# BoundPolicy produced from an adapter-issued Principal. Test-only relaxation
# via tests/conftest.py; no env var or CLI switch.
# Legacy role-string approve() is disabled in production. This flag (no env
# var, no CLI switch) is set True only by tests/conftest.py.
