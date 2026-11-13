#!/usr/bin/env python3
"""Write neutral copies of factorial scenarios.

Usage: python scripts/make_neutral_scenarios.py <folder-with-condition-folders>

For each <condition>/scenario.yaml, writes <condition>/scenario.neutral.yaml with the
brand account's stance changed from +0.8 to 0.0. The original file is not changed.
"""
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
for f in sorted(root.glob("*/scenario.yaml")):
    raw = f.read_bytes()
    new, n = re.subn(rb"(\n  stance: )0\.8(\r?\n)", rb"\g<1>0.0\g<2>", raw)
    if n != 1:
        print("SKIPPED", f.parent.name, "brand stance matches:", n)
        continue
    (f.parent / "scenario.neutral.yaml").write_bytes(new)
    print("wrote", f.parent.name)
