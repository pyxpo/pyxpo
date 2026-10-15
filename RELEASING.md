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

The core wheel and sdist never contain the native module packages: `MANIFEST.in` prunes `packages/`, and
`tools/check_release.py` fails if `pyxpo/modules/` or any `pyxpo_*` package shows up.

## Publish a native module package

Each folder in `packages/` (`file-system`, `image-manipulator`, `image-picker`, `media-library`, `secure-store`, `sharing`, `storage`) is its own PyPI project
(`pyxpo-<name>`) with its own version (`__version__` in `packages/<name>/pyxpo_<name>/__init__.py`).

1. Bump that `__version__`, commit, and tag `pkg/<name>/v<version>` (for example `pkg/image-picker/v0.1.1`).
   If the package needs a newer core, raise its `pyxpo>=` dependency and release the core first.
2. One-time setup per project: on pypi.org add a Trusted Publisher for `pyxpo-<name>`, this repository, workflow
   `release-packages.yml`, environment `pypi`.
3. Pushing the tag runs `.github/workflows/release-packages.yml`: tests, then
   `python tools/build_packages.py --tag pkg/<name>/v<version>` (the tag must match the version; the wheel and sdist
   must carry `pyxpo-module.json`, the iOS and Android sources and the `pyxpo.modules` entry point), `twine check`, and
   publish after you approve the `pypi` environment.

Local check of every package: `python tools/build_packages.py` (output in `wheelhouse-packages/`).

## Dry run before the first release

```
python -m build --outdir wheelhouse/ && twine check wheelhouse/*
python -m venv /tmp/v && /tmp/v/bin/pip install wheelhouse/*.whl
PYXPO_CACHE_DIR=/tmp/c /tmp/v/bin/pyxpo create demo && cd demo && /tmp/v/bin/pyxpo build android
```

Offline or mirrored use: `PYXPO_RUNTIME_ARCHIVES=<dir with the tarballs>`, `PYXPO_RUNTIME_BASE_URL=<https or file URL>`,
`PYXPO_OFFLINE=1`, `pyxpo runtime fetch|path|clean`.
