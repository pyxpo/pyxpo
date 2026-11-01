# Releasing pyxpo

This is the full release runbook. Follow the steps in order.

## What gets released

| Piece | Where | Tag that triggers it | Workflow |
|---|---|---|---|
| Core `pyxpo` | PyPI project `pyxpo` | `vX.Y.Z` (for example `v0.1.0a2`) | `.github/workflows/release.yml` |
| Each module package | PyPI project `pyxpo-<name>` | `vX.Y.Z` in repo `pyxpo/pyxpo-<name>` (for example `v0.1.1`) | `.github/workflows/release.yml` in that repo |
| CPython runtime tarballs | GitHub Release `runtime-<python>-<n>` | none (manual `gh release create`) | none |

Each module package has its own repo `pyxpo/pyxpo-<name>` (the list is `OFFICIAL` in `src/pyxpo/build/autolink.py`). Locally they are cloned side by side in `../pyxpo-packages/pyxpo-<name>`; `tools/dev_install.sh` clones any that are missing. Each one has its own version and is released on its own.

Where the versions live:

- Core: `__version__` in `src/pyxpo/__init__.py`
- Package: `__version__` in `pyxpo_<name>/__init__.py` of the package repo
- Runtime: `runtime` in `src/pyxpo/build/runtime_manifest.json` (separate from the pyxpo version)

The core wheel is small (about 250 KB). The CPython runtimes (about 150 MB) are not in the wheel. `pyxpo build`
downloads them on first use into `~/.cache/pyxpo/runtime/<runtime-version>/` and checks the sha256 pinned in
`runtime_manifest.json`.

## Rules that never change

- A version on PyPI can be uploaded only once. Even after you delete it, you cannot upload the same version again.
  If a release is broken, bump the version and release again.
- Never run `python -m build` without `--outdir wheelhouse/`. The default folder `dist/` holds the CPython runtimes.
- Run local checks with the project venv (`.venv/bin/python`), not the system `python3`. The system Python does not
  have the `build` module, so the check fails with `No module named build.__main__`.
- Publishing always waits for a manual approval in GitHub (environment `pypi`). Nothing reaches PyPI without it.
- The tag must match the version in the code. The workflows fail the release if they differ.

## One-time setup (already done for 0.1.0a1)

1. GitHub repo `pyxpo/pyxpo` is public.
2. GitHub environment `pypi` exists (repo Settings > Environments) with you as required reviewer.
3. Each PyPI project has a Trusted Publisher. Once a project is published, its publisher is active and stays active.
   You only need to add a publisher again for a brand-new package (see "Add a new package" below).

## Release the core `pyxpo`

1. Bump `__version__` in `src/pyxpo/__init__.py`, then run `.venv/bin/python tools/gen_vscode_data.py` (the VS Code data embeds the version; a stale copy fails the release tests).
2. Run the tests: `.venv/bin/python -m pytest -q`
3. Commit and push to `main`.
4. Tag and push:
   ```
   git tag v0.1.0a2
   git push origin v0.1.0a2
   ```
5. Watch the run: `gh run list --workflow release.yml -L1`, then `gh run watch <id>`.
   It runs tests on Python 3.9, 3.11, 3.13, builds into `wheelhouse/`, then runs `tools/check_release.py`. That script
   checks the tag, the wheel size and contents, and that every runtime URL answers 200.
6. When the `publish` job shows **Waiting**, approve it:
   open the run page > **Review deployments** > tick `pypi` > **Approve and deploy**.
7. Check it is live: https://pypi.org/project/pyxpo/ (or
   `curl -s -o /dev/null -w "%{http_code}" https://pypi.org/pypi/pyxpo/<version>/json` prints `200`).

## Release a module package

Work in the package repo (`../pyxpo-packages/pyxpo-<name>`).

1. Bump `__version__` in `pyxpo_<name>/__init__.py` and add a CHANGELOG entry.
   If the package needs a newer core, raise its `pyxpo>=` dependency in `pyproject.toml` and release the core first.
2. Commit and push to `main`.
3. Check locally from the pyxpo repo (must print `ok`):
   ```
   .venv/bin/python tools/build_packages.py <name> --tag v<version>
   ```
4. Tag and push, in the package repo:
   ```
   git tag v<version>
   git push origin v<version>
   ```
5. Watch the run: `gh run list -R pyxpo/pyxpo-<name> --workflow release.yml -L1`.
6. When `publish` shows **Waiting**, approve it (Review deployments > `pypi` > Approve and deploy).
7. Check it is live: `https://pypi.org/project/pyxpo-<name>/`.

You can release several packages one after another this way. Each tag starts its own run.

## Add a new package (first release of a new PyPI project)

1. Create the repo `pyxpo/pyxpo-<name>` and copy `.gitignore` and `.github/workflows/` from an existing package repo.
   Add `<name>` to `OFFICIAL` in `src/pyxpo/build/autolink.py`.
2. In the repo: Settings > **Environments** > New environment `pypi` (add yourself as required reviewer).
3. PyPI calls a publisher for a project that does not exist yet a **pending publisher**. On pypi.org: Account >
   **Publishing** > "Add a new pending publisher" > GitHub, and fill in:
   - PyPI Project Name: `pyxpo-<name>`
   - Owner: `pyxpo`
   - Repository name: `pyxpo-<name>`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
4. Push the package tag and approve the run (steps 3 to 7 of "Release a module package").

Each package repo has its own publisher settings, so several new packages can be pending at the same time.

An existing package whose publisher still points at `pyxpo/pyxpo` and `release-packages.yml` (packages released
before the split): open https://pypi.org/manage/project/pyxpo-<name>/settings/publishing/, add the publisher above,
and remove the old one.

## When something goes wrong

**A test or build job fails before publish.** Nothing was uploaded. Fix the problem, commit, push to `main`, then
move the tag to the new commit:
```
git tag -d v0.1.0a2
git push origin :refs/tags/v0.1.0a2
git tag v0.1.0a2
git push origin v0.1.0a2
```
Use the same steps in the package repo for a package. Move a tag only if its publish job did not run.

**The publish job fails or the upload was wrong.** That version is used up on PyPI. Bump the version and release
again. To hide a broken version from installs, "yank" it on the PyPI project page (Manage > Releases).

**PyPI says the publisher is not trusted / `invalid-publisher`.** The publisher settings on PyPI do not match the run.
Check the owner, repo, workflow file name and environment name for typos.

**Publish job never starts.** It is waiting for approval. Open the run page and click Review deployments.

**A release was pushed by mistake.** Go to the run page and click Cancel workflow, or reject the deployment instead of
approving it. Nothing is uploaded until you approve.

## Publish a new CPython runtime (only when CPython or its build changes)

The `ios` asset also carries the Mac Catalyst slice that the native desktop app (`pyxpo run desktop`) needs. Add it
to `dist/ios/Python.xcframework` before packaging, after the iOS slices exist:

```
tools/build_catalyst_python.sh .cache/Python-3.13.7 .cache/openssl-3.5.9   # adds ios-arm64-maccatalyst (no lzma yet)
```

The script builds OpenSSL from source for Catalyst (the macOS SDK has none). Download the same OpenSSL version as
the iOS slices from https://github.com/openssl/openssl/releases and check it against its `.sha256` first. The
script stops if `_ssl` or `_hashlib` was not built.

Without that slice, `pyxpo run desktop` falls back to the browser preview.

The Windows shell is not a runtime asset yet. Build it on Windows with `pwsh tools/build_windows_shell.ps1`, or run
the `windows` workflow (Actions tab, Run workflow), which also checks that `examples/imagekit` starts and draws.
Users point `PYXPO_WINDOWS_DIST` at the shell folder. See windows/README.md.

```
python tools/package_runtime.py ios dist/ios out/ --host-python .cache/Python-3.13.7/cross-build/build/python.exe
python tools/package_runtime.py android-arm64-v8a dist/android/arm64-v8a out/
python tools/package_runtime.py android-armeabi-v7a dist/android/armeabi-v7a out/
python tools/package_runtime.py android-x86_64 dist/android/x86_64 out/
gh release create runtime-3.13.7-1 out/*.tar.gz --title "pyxpo runtime 3.13.7-1"
```

A new ABI for the same CPython (like `armeabi-v7a`) can go into the current runtime release with
`gh release upload runtime-3.13.7-1 out/<file>`: the other assets and their hashes stay the same.

Copy each printed entry into `assets` of `src/pyxpo/build/runtime_manifest.json` and set `runtime` and `base_url` to
match. Then release a new core version, because the manifest is inside the core wheel. Never delete an old runtime
release: older pyxpo versions still download from it.

## Local dry run (before a big release)

```
.venv/bin/python -m build --outdir wheelhouse/ && .venv/bin/twine check wheelhouse/*
python3 -m venv /tmp/v && /tmp/v/bin/pip install wheelhouse/*.whl
PYXPO_CACHE_DIR=/tmp/c /tmp/v/bin/pyxpo create demo && cd demo && /tmp/v/bin/pyxpo build android
.venv/bin/python tools/build_packages.py          # every package, output in wheelhouse-packages/
```

Offline or mirrored use: `PYXPO_RUNTIME_ARCHIVES=<dir with the tarballs>`, `PYXPO_RUNTIME_BASE_URL=<https or file URL>`,
`PYXPO_OFFLINE=1`, `pyxpo runtime fetch|path|clean`.

## Release history

- 0.1.0a1 (2026-10-16): core `pyxpo` and all 7 packages, runtime `3.13.7-1`.
- 0.1.0a2 (2026-10-16): core `pyxpo` only (async handlers, module constants, module views, AppState events; native contract 2). Then the 11 Tier 1 packages at 0.1.0a1 (each needs `pyxpo>=0.1.0a2`): haptics, device, application, localization, network, fetch, sqlite, web-browser, location, notifications, camera.
- 0.1.0a3 (2026-10-16): core `pyxpo` (Android activity recreate no longer crashes: Python remounts on the new activity; native contract 3 with `PxModule.onNewIntent`). Then `pyxpo-notifications` 0.1.0a2 (remote push, needs `pyxpo>=0.1.0a3`).
- 0.1.0a4 (2026-10-18): core `pyxpo` (module build hooks, `ios.swiftPackages`, web target, themes, layout and Android/Mac fixes). Then the new packages `pyxpo-dot-env` 0.1.0a1 and `pyxpo-google-mobile-ads` 0.1.0a1 (each needs `pyxpo>=0.1.0a4`), one at a time because each needs a pending publisher.
- 0.1.0a5 (2026-10-19): core `pyxpo` only. Android ships `armeabi-v7a` for phones with a 32-bit Android (new `android-armeabi-v7a` asset in runtime `3.13.7-1`), `dot-env` module name.
- 0.1.0a9 (2026-10-29): core `pyxpo` only (tags `v0.1.0a6`, `v0.1.0a7` and `v0.1.0a8` never reached PyPI: no macOS runner picked up the a6 and a7 tests, and the a8 icon tests had no scaler on ubuntu, so release tests run on ubuntu-latest with Pillow now). `use_async(lambda: some_async())` awaits the coroutine the lambda returns. Native module contract 4 (needed by `keyboard`, `speech`, `translate`), Mac Catalyst fixes (`include`, build mode, UTF-8 mode, `_ssl`/`_hashlib` in the new Catalyst slice of runtime `3.13.7-2`), Mac app icon renditions, byte ranges for web `/file`.
