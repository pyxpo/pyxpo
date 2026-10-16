# pyxpo for VS Code

Editor support for [pyxpo](https://github.com/pyxpo/pyxpo) apps. The extension works next to the Python
extension (Pylance) and adds what Pylance cannot know: style keys, component props, colors and `[tool.pyxpo]`.

Features run only in Python files that import pyxpo (`from pyxpo import ...`, `import pyxpo_notifications`, ...).

## Python files

- **Style completion** in `StyleSheet.create({...})`, `StyleSheet.create(box=dict(...))`, `style={...}`,
  `style=[styles.a, {...}]` and any `*_style` / `*Style` argument. Keys follow the file's spelling (camelCase like
  the project templates, or snake_case); set `pyxpo.styleNaming` to fix one.
- **Value completion** for enum keys (`justifyContent`, `alignItems`, `fontWeight`, ...) and color names.
- **Prop completion** inside component calls: `View(`, `Pressable(`, `TextInput(`, `FlatList(`, ...
- **Auto-import**: type `View`, `Text`, `useState`, `StyleSheet`, ... (anything in `pyxpo.__all__`) and pick it;
  the name is added to `from pyxpo import ...` (sorted like isort / Ruff), or a new import line is added. Works in
  files that import pyxpo and in any Python file of a pyxpo project.
- **Import quick fixes**: on a pyxpo name that is not imported (or a Pylance / Ruff "not defined" error),
  `Cmd+.` offers `Import 'X' from pyxpo`. `pyxpo: Add Missing pyxpo Imports` imports every one in the file.
- **Hovers** with the doc of each style key and component.
- **Color swatches and the color picker** for `#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa` (CSS order) and
  `rgb()` / `rgba()` strings, and for color names used as a color value (`"color": "red"`). The picker keeps the
  form you wrote.
- **Checks** in style dicts: unknown keys (with a quick fix for typos), React Native keys pyxpo does not support
  yet, values a key does not take, and bad colors.
- **Convert style keys**: `pyxpo: Convert Style Keys to camelCase` / `to snake_case` rewrites the keys of the
  current file.
- **Snippets**: `pxscreen`, `pxcomponent`, `pxstate`, `pxeffect`, `pxstyles`, `pxview`, `pxtext`, `pxpress`,
  `pxlist`, `pxgradient`.

## pyproject.toml

- Completion of `[tool.pyxpo]` keys, sub-tables (`[tool.pyxpo.android]`, ...) and enum values, from the same schema
  as `pyxpo config --schema`.
- Hovers with each key's type and description.
- Color swatches for hex colors.
- On open and save, the extension runs `python -m pyxpo config` and shows its errors on the matching lines (only in
  trusted workspaces; turn off with `pyxpo.validateConfig`).

## Commands

The status bar item `pyxpo` (shown in pyxpo projects) opens a menu. In the Command Palette:

| Command | Runs |
| --- | --- |
| pyxpo: Run App... | a menu of the commands below |
| pyxpo: Run on Android / iOS / Desktop | `python -m pyxpo run android` / `ios` / `desktop` |
| pyxpo: Prebuild Native Projects | `python -m pyxpo prebuild` |
| pyxpo: Doctor | `python -m pyxpo doctor` |
| pyxpo: Show Resolved App Config | `python -m pyxpo config` |
| pyxpo: Create New Project... | `python -m pyxpo create <name>` in a folder you pick |

| pyxpo: Add Missing pyxpo Imports | adds `from pyxpo import` for pyxpo names the file uses |

Commands run in a `pyxpo` terminal, in the folder whose `pyproject.toml` has `[tool.pyxpo]`.

## Restricted Mode

In a folder you have not trusted, completion, auto-import, hovers, colors and style checks work. Validating
`[tool.pyxpo]` and the run commands start the project's Python, so they wait until you trust the folder
(`Manage Workspace Trust`). `pyxpo.pythonPath` from an untrusted folder's settings is ignored.

## Python used

`pyxpo.pythonPath` if set; else the interpreter selected in the Python extension; else `.venv` or `venv` in the
project (or a parent folder); else `python3`.

## Formatting

Python formatting stays with your formatter (Ruff or Black, for example `charliermarsh.ruff`). pyxpo code is plain
Python, so they format it as is. The extension adds the style key conversion above.

## Settings

| Setting | Default | |
| --- | --- | --- |
| `pyxpo.pythonPath` | `""` | Python for `python -m pyxpo`. |
| `pyxpo.styleNaming` | `auto` | `auto`, `camelCase` or `snake_case` for completed style keys and props. |
| `pyxpo.diagnostics.enable` | `true` | Style checks in Python files. |
| `pyxpo.validateConfig` | `true` | Run `pyxpo config` on pyproject.toml. |
| `pyxpo.colorDecorators` | `true` | Color swatches and the picker. |
| `pyxpo.autoImport` | `true` | Suggest pyxpo names while typing and add their import. |

## Development

```sh
cd editors/vscode
npm install
npm test                         # compile + unit tests
npm run test:e2e                 # real VS Code on a fixture project, trusted and Restricted Mode (../../.venv python)
npm run test:e2e:vsix            # same on the packaged .vsix installed like a user's (trust applies to it)
python3 ../../tools/gen_vscode_data.py   # after style keys, components or the config schema change
npx vsce package                 # pyxpo-<version>.vsix
code --install-extension pyxpo-*.vsix
```

`data/pyxpo.json` is generated from pyxpo itself (style keys, components, config schema). A pytest in the main
repo fails when it is stale.
