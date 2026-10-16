"""The VS Code extension's data file must match pyxpo (style keys, components, config schema)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_vscode_data_is_current():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "gen_vscode_data.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
