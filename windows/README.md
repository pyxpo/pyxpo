# Windows shell

The native Windows desktop app. `pyxpo run desktop` and `pyxpo build desktop` on Windows use it.

## How it works

`PyxpoShell.exe` is a WinUI 3 app written in C# (.NET 8, Windows App SDK 1.6). It is unpackaged and self-contained,
so a build runs from any folder and needs no installer.

- `pyxpo_native.dll` (`native/`) holds the C bridge, the layout engine and the Python host. The host starts CPython
  3.13 (the embeddable distribution in `python/`) on its own thread, with `PYXPO_TARGET=windows`.
- Python sends the same ops JSON as the iOS and Android shells. `OpApplier.cs` applies the ops to XAML controls:
  `Canvas` frames placed by the C layout engine, `TextBlock`, `TextBox` / `PasswordBox`, `Image`, `ScrollViewer`,
  `ToggleSwitch`, `Slider`, `ProgressRing`, `Button`.
- Events (press, text, scroll, layout, env) go back to Python on one serial thread, in order.
- Module calls: the shell answers `Scroll`, `StatusBar`, `Back`, `Keyboard`, `Clipboard`, `Linking`, `SplashScreen`,
  `Vibration` and `Alert` itself. Every other module call runs in Python, in the package's `desktop.py` backend
  (the same backend as `pyxpo run desktop --preview`). The build writes the linked modules to
  `app/pyxpo/desktop_modules.json`.

A build (`src/pyxpo/build/windows.py`) copies the shell to `build/windows/<Name>/`, renames the exe after the app and
adds:

```
app/              the project's app/ and assets/, the pyxpo package, linked module packages
app_packages/     [tool.pyxpo] requires, installed as win_amd64 wheels for CPython 3.13
pyxpo-app.json    window title and size, entry module, background colour, light / dark lock
```

## Build the shell

Needs Windows x64, Visual Studio 2022 C++ tools, CMake 3.20+, the .NET 8 SDK and Python 3.13 x64.

```
pwsh tools/build_windows_shell.ps1                  # writes dist\windows
pwsh tools/build_windows_shell.ps1 -Out C:\shell    # then set PYXPO_WINDOWS_DIST=C:\shell
```

In a dev checkout, `pyxpo build desktop` finds `dist\windows`. Elsewhere, set `PYXPO_WINDOWS_DIST` to the shell folder.
The pyxpo runtime release does not ship a Windows shell yet.

The `windows` GitHub Actions workflow builds the shell on `windows-latest`, builds `examples/imagekit`, runs it, and
uploads a screenshot (`windows-desktop` artifact).

## App config

```toml
[tool.pyxpo.windows]
title = "My App"        # default: the app name
size = [1024, 768]      # window size at 100% display scale
```

`background_color` and `user_interface_style` (`light` / `dark` lock) come from `[tool.pyxpo]`, as on iOS.

## Keys and mouse

- Escape and the mouse back button (XButton1) act as the hardware back button.
- Ctrl+R reloads the app in dev.

## Debugging

- `PYXPO_STDIO=1` sends Python's stdout and stderr to the process's stdout. `pyxpo run desktop` sets it and prints
  the output in the terminal.
- `PYXPO_SNAPSHOT_DIR=<dir>`: write a name to `<dir>\req` and the shell saves the window as `<dir>\<name>.png`.

## Known limits

These props have no effect on Windows:

- `font_file` (custom fonts). Text uses the system font families.
- `tint_color` on images. XAML has no template-image rendering for bitmaps.
- `text_shadow_*`.
- `paging_enabled` and `bounces` on ScrollView. `ScrollViewer` has no paging or bounce switch.
- Different colours per border side. The shell uses one colour for all sides.
- A shadow (`shadow_*`, `elevation`) needs a `background_color` on the same view.

Also:

- No edge-swipe back gesture on stack screens. Use Escape, the mouse back button or a back button in the app.
- Native module views (a module's own UI view) are not available. Module calls work through `desktop.py`.
- The shell has only been checked on the CI runner (screenshot). Test on a real Windows machine before a release.
