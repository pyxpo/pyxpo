# Releasing pyxpo

pyxpo ships as two pieces:

1. **The wheel on PyPI** (about 250 KB): Python code, project templates, the C bridge sources, and `runtime_manifest.json`.
2. **CPython runtime tarballs on GitHub Releases** (about 95 MB total): the prebuilt CPython for iOS and each Android ABI.
   `pyxpo build` downloads what it needs on first use into `~/.cache/pyxpo/runtime/<runtime-version>/` and checks the
   sha256 pinned in the wheel. The runtime version (for example `3.13.7-1`) is separate from the pyxpo version.

## Publish a new runtime (only when CPython or its build changes)

```
python tools/package_runtime.py ios dist/ios out/ --host-python .cache/Python-3.13.7/cross-build/build/python.exe
python tools/package_runtime.py android-arm64-v8a dist/android/arm64-v8a out/
python tools/package_runtime.py android-x86_64 dist/android/x86_64 out/
gh release create runtime-3.13.7-1 out/*.tar.gz --title "pyxpo runtime 3.13.7-1"
```

Copy each printed entry into `assets` of `src/pyxpo/build/runtime_manifest.json` and set `runtime` and `base_url` to match.

## Publish pyxpo

1. Bump `__version__` in `src/pyxpo/__init__.py`, commit, and tag `vX.Y.Z`.
2. One-time setup: on pypi.org (and test.pypi.org) add a Trusted Publisher for this repository, workflow `release.yml`,
   environment `pypi`. In GitHub, create the `pypi` environment and add yourself as required reviewer.
3. `git push --tags` runs tests, builds into `wheelhouse/`, runs `tools/check_release.py` (tag, wheel size and contents,
   every runtime URL answers 200) and publishes after you approve the `pypi` environment.

Never run `python -m build` without `--outdir wheelhouse/`: the default output folder `dist/` holds the CPython runtimes.

## Dry run before the first release

```
python -m build --outdir wheelhouse/ && twine check wheelhouse/*
python -m venv /tmp/v && /tmp/v/bin/pip install wheelhouse/*.whl
PYXPO_CACHE_DIR=/tmp/c /tmp/v/bin/pyxpo create demo && cd demo && /tmp/v/bin/pyxpo build android
```

Offline or mirrored use: `PYXPO_RUNTIME_ARCHIVES=<dir with the tarballs>`, `PYXPO_RUNTIME_BASE_URL=<https or file URL>`,
`PYXPO_OFFLINE=1`, `pyxpo runtime fetch|path|clean`.
