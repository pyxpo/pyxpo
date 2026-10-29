#!/bin/bash
# Pushes each packages/<name> folder, with its own commit history, to its own repo pyxpo/pyxpo-<name>.
# The monorepo stays the place to develop; the package repos are read-only mirrors of main.
#
#   tools/split_packages.sh              # every package
#   tools/split_packages.sh camera video # only these
#
# PYXPO_SPLIT_URL sets the remote, with NAME for the repo name. Default: HTTPS, which uses the same
# credentials as origin. Example for SSH: PYXPO_SPLIT_URL='git@github.com:pyxpo/NAME.git'
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
URL="${PYXPO_SPLIT_URL:-https://github.com/pyxpo/NAME.git}"
cd "$REPO"

if [ $# -gt 0 ]; then names=("$@"); else names=($(ls packages)); fi

failed=()
for n in "${names[@]}"; do
  [ -f "packages/$n/pyproject.toml" ] || { echo "skip $n: no packages/$n/pyproject.toml"; continue; }
  repo="pyxpo-$n"
  echo "== $repo"
  sha="$(git subtree split -q --prefix="packages/$n" HEAD)"
  if git push "${URL/NAME/$repo}" "$sha:refs/heads/main"; then
    echo "   $repo main -> ${sha:0:7}"
  else
    failed+=("$repo")
  fi
done

if [ ${#failed[@]} -gt 0 ]; then echo "failed: ${failed[*]}"; exit 1; fi
