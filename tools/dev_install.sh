#!/bin/sh
# Monorepo dev setup: installs pyxpo core and every native module package in packages/ as editable
# installs, so tests, examples and test-apps see local changes without reinstalling.
#
# Usage: tools/dev_install.sh            (uses .venv/bin/python, creating .venv if needed)
#        PYTHON=/path/to/python tools/dev_install.sh
set -e
# Git Bash on Windows: `pwd -W` gives D:/a/x, which Windows pip understands (it rejects /d/a/x).
ROOT=$(cd "$(dirname "$0")/.." && { pwd -W 2>/dev/null || pwd; })
PY=${PYTHON:-$ROOT/.venv/bin/python}
# PYTHON may be a bare command name (CI sets PYTHON=python): resolve it on PATH before the -x check.
PY=$(command -v "$PY" || echo "$PY")
if [ ! -x "$PY" ]; then
    python3 -m venv "$ROOT/.venv"
    PY=$ROOT/.venv/bin/python
fi
set -- -e "$ROOT[dev]"
for d in "$ROOT"/packages/*/; do
    [ -f "$d/pyproject.toml" ] && set -- "$@" -e "${d%/}"
done
"$PY" -m pip install -q -U pip "setuptools>=77" build
"$PY" -m pip install -q "$@"
"$PY" -c "from pyxpo.build import autolink; print('pyxpo modules installed:', ', '.join(sorted(autolink.discover())) or 'none')"
