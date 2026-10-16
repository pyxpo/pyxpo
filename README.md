# Pyxpo

React-Native-style Python framework: declarative components + hooks -> reconciler -> batched JSON ops -> native widgets.
See DESIGN.md (architecture) and PLAN.md (roadmap). Android and iOS are both supported.

## Install
```
pip install pyxpo
pyxpo create demo && cd demo
pyxpo doctor            # check Xcode / Android SDK / Gradle
pyxpo run android       # or: pyxpo run ios
```
The first mobile build downloads the prebuilt CPython runtime (about 20-60 MB per target) into `~/.cache/pyxpo`.

## Develop pyxpo itself
```
tools/dev_install.sh    # .venv with core + every module package in packages/, all editable
.venv/bin/pyxpo create demo && cd demo && ../.venv/bin/pyxpo run desktop   # native Mac window, see below
.venv/bin/pytest
```

`pyxpo run desktop` on a Mac builds the app as a native Mac app (UIKit through Mac Catalyst, same shell as iOS) and
opens it with hot reload. It needs Xcode and the Catalyst slice of the runtime. The first launch asks for any privacy
permission the app uses (Photos, camera), as on a phone. `pyxpo build desktop` builds the `.app` only.
On Windows, the same commands build a native WinUI 3 app (`build/windows/<Name>/<Name>.exe`) from the prebuilt
Windows shell; see [windows/README.md](windows/README.md) to build the shell and for its limits.
`pyxpo run desktop --preview` skips the native build and shows the app in a browser window, and
`PYXPO_RENDERER=console` uses the text renderer (type 1 + Enter to press a button, q to quit).

## Web

`pyxpo run web` serves the app as a single page app at http://127.0.0.1:8000/ and reloads the page when a file in
`app/`, `assets/` or `pyproject.toml` changes (`--port`, `--no-open`, `--base`). `pyxpo build web` writes a static
site to `build/web/`.

- The app's Python runs in the browser on [Pyodide](https://pyodide.org). There is no server.
- The pyxpo reconciler is the virtual DOM. It diffs component trees with keyed children and moves only the nodes
  outside the longest increasing run. `app.js` applies the resulting ops to real DOM nodes.
- The router keeps the address bar, the page title and browser history in step with navigation. Links, back and
  forward, refresh and deep links work as in any SPA.
- Navigation behaves like a web site, not a phone. `Stack` swaps pages at once, with no slide and no edge swipe.
  Pages below the top stay mounted, so Back restores their scroll position, state and keyboard focus. `Link` renders
  a real anchor: ctrl/cmd-click, middle-click and "Copy link" work. Pressables show a hover state and can be reached
  with Tab and pressed with Enter or Space.
- Any static host works if unknown paths serve `index.html`. The build also writes `404.html` for hosts such as
  GitHub Pages.

```toml
[tool.pyxpo.web]
base = "/myapp"           # the site lives under this path (default: the site root)
title = "My App"          # page title (default: the app name)
packages = ["numpy"]      # extra packages the browser installs with micropip
```

`[tool.pyxpo] requires` are installed with micropip as well, so they must be pure Python or built for Pyodide.

Native modules work on web when their package has a `web.py` backend. The backend defines `call(method, args)` and
may return an awaitable. Helpers for backends are in `pyxpo.renderers.web.browser`: `choose_files`, `save_file` and
`download`. The official image modules behave like this on web:

- image-picker opens the browser's file chooser. It has no camera.
- image-manipulator runs Pillow in the browser.
- media-library downloads the file.
- sharing uses the Web Share API, or downloads the files when the browser has no Web Share API.

A project is an `app/` folder of routes, like Expo Router:

```
app/
  _layout.py        # Stack / Tabs / Drawer / Slot around the routes below
  index.py          # "/"
  details/[id].py   # "/details/7"   -> useLocalSearchParams()["id"]
  +not-found.py     # unmatched URLs
```

```python
# app/index.py
from pyxpo import Button, Text, View, useState
from pyxpo.router import Link

def Index():
    n, setN = useState(0)
    return View(Text("Count: ", n), Button(title="Add", onPress=lambda: setN(n + 1)),
                Link("Details", href="/details/%d" % n))

default = Index
```

Hooks: use_state, use_effect, use_ref, use_memo, use_callback, use_context, use_async. Lists need `key=`.
`pyxpo add-lib <pkg>` checks mobile wheel availability (note: full tensorflow/torch cannot run on mobile).

## Native modules

Features beyond the core are optional native modules, each its own pip package (like Expo's `expo-image-picker`).
Only the modules an app lists are compiled into it.

| Package | Import | `modules` entry |
|---|---|---|
| `pyxpo-file-system` | `from pyxpo_file_system import File, Directory, Paths` | `file-system` |
| `pyxpo-image-manipulator` | `from pyxpo_image_manipulator import ImageManipulator` | `image-manipulator` |
| `pyxpo-image-picker` | `from pyxpo_image_picker import ImagePicker` | `image-picker` |
| `pyxpo-media-library` | `from pyxpo_media_library import MediaLibrary` | `media-library` |
| `pyxpo-secure-store` | `import pyxpo_secure_store as SecureStore` | `secure-store` |
| `pyxpo-sharing` | `from pyxpo_sharing import Share` | `sharing` |
| `pyxpo-storage` | `from pyxpo_storage import storage` | `storage` |

```
pip install pyxpo-image-picker
```
```toml
[tool.pyxpo]
modules = ["image-picker"]
```
Their sources live in `packages/`; see each package's README. Third-party modules are pip packages that register a
`pyxpo.modules` entry point the same way.

## React Native style API
Every RN spelling is an alias; the snake_case API keeps working. No JSX (not valid Python), so children are call arguments.

```python
from pyxpo import StyleSheet, View, Text, Pressable, FlatList, SectionList, useState, useEffect, component

styles = StyleSheet.create(                      # or StyleSheet.create({"title": {...}})
    title=dict(fontSize=24, fontWeight="bold", marginBottom=12),
)

@component
def App():
    count, setCount = useState(0)
    useEffect(lambda: print("count", count), [count])
    return View(
        Text("Hello", style=styles.title),
        Pressable(Text("+"), onPress=lambda: setCount(count + 1),
                  style=lambda state: {"opacity": 0.5 if state.pressed else 1}),
        FlatList(data=[1, 2], renderItem=lambda p: Text(p["item"]), keyExtractor=lambda i, _: i),
    )
```

- Style keys and props accept camelCase (`backgroundColor`, `onPress`, `numberOfLines`, `placeholderTextColor`, `testID`). Giving both spellings of one prop raises `TypeError`. User components accept a camelCase key when its snake_case form is a parameter.
- Hooks: `useState`, `useEffect`, `useLayoutEffect`, `useReducer`, `useRef`, `useMemo`, `useCallback`, `useContext`, `useId`, `useImperativeHandle`, `useSyncExternalStore`, `useTransition`, `useDeferredValue`. Effects are exception-safe: one failing effect or cleanup does not stop the others, errors go to `ErrorBoundary(on_error=...)` or `app.on_error`. Child effects run before parent effects. Effects must be sync functions (an `async def` effect runs as a task and warns).
- `ErrorBoundary(*children, fallback=lambda error, reset: ...)`.
- `FlatList` `renderItem` with one parameter gets `{"item", "index"}`; with two it gets `(item, index)`. `SectionList(sections=[{"title", "data"}], renderItem, renderSectionHeader)` (no sticky headers yet).
- Modules: `Platform.OS`, `Dimensions.addEventListener("change", fn)` (returns an object with `.remove()`), `BackHandler.addEventListener("hardwareBackPress", fn)`, `Keyboard.addListener("keyboardDidShow", fn)`, `Linking.openURL`, `Alert.alert(title, msg, [{"text", "onPress"}])`.
- RN style values that have no native equivalent (`borderStyle`, `tintColor`, `resizeMode`, ...) log a warning and are ignored. `Pressable` `hit_slop` and `delay_long_press` are accepted but not applied natively yet.
- Example: `examples/rn_style`.

## Routing (`pyxpo.router`, Expo Router)
- Files under `app/` are routes: `index`, `[id]` (dynamic), `[...rest]` (catch-all), `(group)/` (no URL segment), `_layout.py` (navigator), `+not-found.py`. A route module exports `default` (or has a single `@component`).
- Layouts: `Stack`, `Tabs`, `Drawer`, `Slot`; configure with `Stack.Screen(name=..., options={...})` or `screenOptions`. Options follow react-navigation (`title`, `headerShown`, `headerRight`, `tabBarIcon`, ...). A layout may export `unstable_settings = {"initialRouteName": ...}`.
- `router.push/navigate/replace/back/dismiss/dismissAll/setParams`, `<Link href=...>`, `<Redirect href=...>`; hooks `useRouter`, `useLocalSearchParams`, `useGlobalSearchParams`, `usePathname`, `useSegments`, `useNavigation`, `useIsFocused`, `useFocusEffect`. Theme: `ThemeProvider`, `DefaultTheme`, `DarkTheme`, `useTheme`.
- Android hardware back, the stack edge-swipe and the drawer all go through one navigation store. iOS Swift controls and the native stack are not ported yet.
