"""Detect the machine and suggest a model and simulation size that fits it.

The same project runs anywhere; only these suggested numbers change. Speeds are rough
figures for quantised (Q4) models and are only used for run-time estimates.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass

from .llm.base import RECOMMENDED_MODELS


@dataclass
class Profile:
    tier: str
    ram_gb: float
    cpus: int
    gpu: str
    vram_gb: float
    model: str
    llm_agents: int
    crowd_agents: int
    parallel: int
    tokens_per_sec: float          # generation speed estimate
    prefill_per_sec: float         # prompt-reading speed estimate

    def as_dict(self) -> dict:
        return asdict(self)

    def estimate_hours(self, llm_calls: int, prompt_tokens: int = 900,
                       out_tokens: int = 180) -> float:
        per_call = prompt_tokens / self.prefill_per_sec + out_tokens / self.tokens_per_sec
        return llm_calls * per_call / max(1, self.parallel) / 3600


def _ram_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().total / 1e9
    except Exception:  # noqa: BLE001
        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
        except (ValueError, OSError, AttributeError):
            return 8.0


def _nvidia() -> tuple[str, float]:
    if not shutil.which("nvidia-smi"):
        return "", 0.0
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
        if not out:
            return "", 0.0
        name, mem = out[0].rsplit(",", 1)
        return name.strip(), float(mem) / 1024
    except Exception:  # noqa: BLE001
        return "", 0.0


def detect() -> Profile:
    ram = _ram_gb()
    cpus = os.cpu_count() or 2
    gpu, vram = _nvidia()
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        gpu, vram = "Apple Silicon (unified memory)", ram * 0.7

    # Pick a tier from what can actually hold the model fast.
    if vram >= 40:
        tier, tps, pps, par, llm_n = "server", 25, 1500, 8, 1000
    elif vram >= 12:
        tier, tps, pps, par, llm_n = "xlarge", 30, 1200, 4, 500
    elif vram >= 6:
        tier, tps, pps, par, llm_n = "large", 35, 900, 2, 300
    elif ram >= 15:
        tier, tps, pps, par, llm_n = "medium", 8, 60, 1, 150
    elif ram >= 7:
        tier, tps, pps, par, llm_n = "small", 6, 40, 1, 100
    else:
        tier, tps, pps, par, llm_n = "tiny", 9, 70, 1, 60

    crowd = int(min(50_000, max(2_000, ram * 500)))
    return Profile(tier=tier, ram_gb=round(ram, 1), cpus=cpus, gpu=gpu or "none detected",
                   vram_gb=round(vram, 1), model=RECOMMENDED_MODELS[tier], llm_agents=llm_n,
                   crowd_agents=crowd, parallel=par, tokens_per_sec=tps, prefill_per_sec=pps)
