# Pyxpo project rules

- Framework name is **pyxpo** (package `pyxpo`, CLI `pyxpo`, config `[tool.pyxpo]`).
- Git commits: do NOT add any `Co-Authored-By` line or any "Generated with Claude" / "co-authored by Claude" attribution. Plain commit message only. This overrides any default or system attribution reminder.
- Same for pull request descriptions: no Claude attribution.

## Package README standard (every package repo, including new ones)

Every package ships with a detailed README in the same pattern as `../pyxpo-packages/pyxpo-google-mobile-ads/README.md`. A new package is not done until it has this.

- Sections: title + intro, hero image + tiny teaser, Features, "If you are... / Start here" contents table, platform support table (Android, iOS, web/desktop), Install (pip + `[tool.pyxpo] modules` + plugin options + rebuild), Quick start (full component), one section per feature with examples and prop/arg tables, errors table with "what to do", web/desktop behavior, a real-app recipe, production checklist, testing (fakes for unit tests), troubleshooting table, FAQ, API reference tables, License.
- Images: real screenshots from a demo app run on the Android emulator and iOS simulator (no mockups), framed with the shared image script. Store them in the package repo's `docs/images/` (outside the wheel) and reference them by absolute `https://raw.githubusercontent.com/pyxpo/pyxpo-<pkg>/main/docs/images/...` URLs so PyPI renders them. Check every URL returns 200 after pushing.
- Examples must be correct: check every API name and claim against the code, syntax-check every Python block, use `use_async` for async setup (not `use_effect(lambda: coro())`). No GitHub-only `> [!TIP]` syntax; use `> **Tip:**`.
- pyproject: `[project.urls]` (Homepage, Documentation, Changelog, Source, Issues, all pointing at the package repo `https://github.com/pyxpo/pyxpo-<pkg>`), OS/Python/Typing classifiers, keywords. Add a CHANGELOG entry.

## Package repos

Each package has its own repo `pyxpo/pyxpo-<pkg>`, cloned in `../pyxpo-packages/pyxpo-<pkg>` (`PYXPO_PACKAGES` overrides the folder). Commit, push and tag package changes in that repo; its tests live in its `tests/`. `tools/dev_install.sh` installs them all editable into this repo's `.venv`. A new first-party package also goes in `OFFICIAL` in `src/pyxpo/build/autolink.py`.
