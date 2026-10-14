from __future__ import annotations

import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Tuple

from .platforms import PYTHON_VERSION, TARGET_TAGS

HEAVY = {
    "tensorflow": "full TensorFlow has no mobile build; use ai-edge-litert (TFLite) or onnxruntime instead",
    "torch": "PyTorch has no mobile wheels for this runtime; use onnxruntime or ai-edge-litert instead",
}


def check_wheel(package: str, tag: str, extra_args: Optional[List[str]] = None) -> Tuple[bool, str]:
    """Ask pip whether a binary wheel exists for this platform tag."""
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--no-deps",
               "--platform", tag, "--python-version", PYTHON_VERSION, "-d", tmp, package]
        cmd += extra_args or []
        proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        return True, "ok"
    last = (proc.stderr.strip().splitlines() or ["failed"])[-1]
    return False, last


def check_package(package: str, targets: List[str], extra_args: Optional[List[str]] = None) -> Dict[str, Tuple[bool, str]]:
    results: Dict[str, Tuple[bool, str]] = {}
    for target in targets:
        for tag in TARGET_TAGS[target]:
            results[tag] = check_wheel(package, tag, extra_args)
    return results


def format_table(package: str, results: Dict[str, Tuple[bool, str]]) -> str:
    width = max(len(t) for t in results) if results else 10
    lines = ["%s wheel availability:" % package]
    for tag, (ok, msg) in results.items():
        lines.append("  %-*s  %s" % (width, tag, "OK" if ok else "MISSING (%s)" % msg))
    return "\n".join(lines)
