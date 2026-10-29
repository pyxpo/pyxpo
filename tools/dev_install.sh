#!/bin/sh
# Dev setup: installs pyxpo core and every native module package as editable installs, so tests,
# examples and test-apps see local changes without reinstalling.
#
# Each package has its own repo pyxpo/pyxpo-<name>. They live side by side in ../pyxpo-packages
# (PYXPO_PACKAGES overrides that folder). A package missing there is cloned from GitHub first.
#
# Usage: tools/dev_install.sh            (uses .venv/bin/python, creating .venv if needed)
#        PYTHON=/path/to/python tools/dev_install.sh
set -e
# Git Bash on Windows: `pwd -W` gives D:/a/x, which Windows pip understands (it rejects /d/a/x).
ROOT=$(cd "$(dirname "$0")/.." && { pwd -W 2>/dev/null || pwd; })
PKGS=${PYXPO_PACKAGES:-$ROOT/../pyxpo-packages}
PY=${PYTHON:-$ROOT/.venv/bin/python}
# PYTHON may be a bare command name (CI sets PYTHON=python): resolve it on PATH before the -x check.
PY=$(command -v "$PY" || echo "$PY")
if [ ! -x "$PY" ]; then
    python3 -m venv "$ROOT/.venv"
    PY=$ROOT/.venv/bin/python
fi
"$PY" -m pip install -q -U pip "setuptools>=77" build
"$PY" -m pip install -q -e "$ROOT[dev]"
mkdir -p "$PKGS"
PKGS=$(cd "$PKGS" && { pwd -W 2>/dev/null || pwd; })
set --
for n in $("$PY" -c "from pyxpo.build import autolink; print(' '.join(autolink.OFFICIAL))"); do
    [ -d "$PKGS/pyxpo-$n" ] || git clone -q --depth 1 "https://github.com/pyxpo/pyxpo-$n.git" "$PKGS/pyxpo-$n"
done
for d in "$PKGS"/pyxpo-*/; do
    [ -f "$d/pyproject.toml" ] && set -- "$@" -e "${d%/}"
done
# --no-deps: the packages only depend on pyxpo, which is the editable core above. A package may already ask for
# the next core version (pyxpo>=X) before core is bumped, and pip would refuse that.
"$PY" -m pip install -q --no-deps "$@"
"$PY" -c "from pyxpo.build import autolink; print('pyxpo modules installed:', ', '.join(sorted(autolink.discover())) or 'none')"
