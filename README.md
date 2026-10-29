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

Devices: `pyxpo run android` uses the connected phone or emulator. With none connected, it starts your Android
emulator (AVD) and waits for it to boot; extra emulator flags go in `PYXPO_EMULATOR_ARGS` (for example `-no-audio`).
`pyxpo run ios` uses the booted iPhone simulator, else boots the newest one, and opens Simulator (DeviceHub on
Xcode 27). Pick one with `--device`: an Android serial or AVD name, or an iOS simulator name or UDID.
Android and iOS can run side by side: when the hot reload port (8765) is taken, the next run uses the next free one.

## Develop pyxpo itself
```
tools/dev_install.sh    # .venv with core + every module package in ../pyxpo-packages, all editable
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
packages = ["numpy"]      # extra packages the browser loads
```

`[tool.pyxpo] requires` load the same way, so they must be pure Python or built for Pyodide. Packages Pyodide builds (numpy, pillow, ...) load straight from its CDN while the runtime starts; the rest, and version specs like `"attrs>=23"`, go through micropip.

Python in the browser differs from Python on a phone in a few places:

- There are no threads. `asyncio.to_thread` and `use_async` with a plain function run the function on the page's
  only thread, so the page does not repaint until it returns. Loop callbacks it schedules run after it.
- numpy's `linalg.inv` and `linalg.solve` return NaN for a singular matrix instead of raising `LinAlgError`. Check
  the result with `numpy.isfinite` when the code depends on that exception.
- Files in the documents folder (file-system, sqlite) and storage values are kept in the browser's IndexedDB, so
  they outlive a reload. They are copied in before the app starts and written back about every 2 seconds after a
  change and when the page is hidden. `await window.PYXPO_WEB.persist()` in page code writes them at once. The cache
  folder is kept only until the page closes. Tabs of one site share the data, and the last one to write wins.

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
| `pyxpo-dot-env` | `from pyxpo_dot_env import env` | `env` |
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
Each one has its own repo, `pyxpo/pyxpo-<name>`; see its README. Third-party modules are pip packages that register a
`pyxpo.modules` entry point the same way.

### Dev tools

`pyxpo run web` shows a round button at the bottom right of the page. It opens a panel for building responsive UI
without an emulator. `pyxpo build web` never includes it; `--no-devtools` hides it during development.

- **View**: Desktop (the default), Mobile, Tablet or Custom. Mobile and Tablet show the app in a device body
  (iPhone 15 Pro, iPhone SE, Pixel 8, iPad, Galaxy Tab and more) with its status bar, notch or home indicator and
  safe area insets. Rotate turns the device. Custom takes any width and height, or drag the frame edges.
- In a device the screen behaves like a touch screen: no hover, a round touch cursor, drag to scroll with momentum
  and no scroll bars. The app gets the device size, pixel ratio and insets, so `use_window_dimensions`,
  `SafeAreaView` and breakpoints react as on the phone.
- **Breakpoint**: the active breakpoint and window size. Click a breakpoint to view the app at that width.
- **Appearance**: System, Light or Dark. **Behaviour**: Web, iOS or Android sets `Platform.OS`, so stacks slide and
  swipe like the phone app. On Android, Esc is the back button.
- A toolbar next to the device works like an emulator's: rotate, zoom in and out, fit, 1:1, light/dark, back,
  reload. Zoom goes from 20 to 300%: use the toolbar, the panel slider, Ctrl/Cmd + scroll or a trackpad pinch over
  the device, or drag the grip at its bottom right corner. Cmd/Ctrl+Shift+M turns the device view on and off.
  Settings are kept per browser.

## Responsive layout

Breakpoints work like CSS media queries, mobile first: `xs` 0, `sm` 576, `md` 768, `lg` 992, `xl` 1200, `xxl` 1400
(window width in dp). A breakpoint map such as `{"base": 1, "md": 3}` takes the value of the largest breakpoint at or
below the current one. Maps work as a style value, as a whole style block, and in every layout prop below. Crossing a
breakpoint updates only the affected views, without a re-render.

```python
from pyxpo import Container, Row, Col, Grid, GridItem, Flex, HStack, VStack, Spacer, Show, Hide, Text, View
from pyxpo import use_breakpoint, use_breakpoint_value, use_media_query

style = {"padding": {"base": 8, "lg": 24}, "flex_direction": {"base": "column", "md": "row"}}
block = {"base": {"padding": 8}, "md": {"padding": 24, "gap": 16}}   # like Tailwind md:

Container(                                        # centered column: 540 / 720 / 960 / 1140 / 1320 max width
    Row(                                          # 12-column grid, gutter between columns and lines
        Col(Text("Main"), span={"base": 12, "md": 8}),
        Col(Text("Side"), span={"base": 12, "md": 4}),
        Col(Text("Pushed"), span=4, offset=4),    # span="auto" = content width, None = equal share, 0 = hidden
        gutter=16,
    ),
    Grid(*cards, columns={"base": 1, "sm": 2, "lg": 4}, gap=12),   # CSS grid repeat(n, 1fr)
    Grid(*cards, min_item_width=220),             # auto-fill as many 220 dp columns as fit
    Grid(GridItem(hero, span=2), a, b, columns=3),
    Flex(a, Spacer(), b, direction={"base": "column", "md": "row"}, gap=12, align="center", wrap=True),
    Show(Sidebar(), above="lg"), Hide(MobileNav(), above="lg"),
)

bp = use_breakpoint()                             # "md"; re-renders only when the breakpoint changes
cols = use_breakpoint_value({"base": 1, "md": 2, "xl": 3})
wide = use_media_query("md", orientation="landscape")   # md and up; also down="lg", only="md", min_width=600
```

`pyxpo.responsive.set_breakpoints({"phone": 0, "tablet": 600, "desktop": 1024})` replaces the table. Every flexbox
style (`flex_direction`, `flex_wrap`, `flex_grow`, `flex_basis`, `align_content`, `gap`, `row_gap`, `column_gap`,
percent sizes) works on every target.

## Themes (light / dark)

The API follows [react-native-unistyles 3](https://www.unistyl.es). Register the themes once, then give
`StyleSheet.create` a function. Components need no hook. When the theme, the system color scheme, the safe-area
insets or the breakpoint change, pyxpo updates only the affected views. Components do not re-render.

```python
from pyxpo import StyleSheet, Text, View, component, useAppTheme

StyleSheet.configure(                             # once, e.g. in app/_theme.py
    themes={"light": {"colors": {"bg": "#fff", "text": "#111"}},
            "dark": {"colors": {"bg": "#000", "text": "#eee"}}},
    breakpoints={"phone": 0, "tablet": 600},      # optional, replaces the default table
)                                                 # adaptive: "light"/"dark" follow the system setting

styles = StyleSheet.create(lambda theme, rt: {    # rt: insets, breakpoint, colorScheme, themeName, fontScale
    "screen": {"flex": 1, "backgroundColor": theme.colors.bg, "paddingTop": rt.insets.top},
    "title": {"fontSize": {"base": 20, "tablet": 28}, "color": theme.colors.text},
    "avatar": lambda size: {"width": size, "height": size, "borderRadius": size / 2},   # dynamic style
})

@component
def Home():
    theme = useAppTheme()                         # only for values outside styles, like an icon color
    return View(Text("Hi", style=styles.title), View(style=styles.avatar(48)), style=styles.screen)

StyleSheet.setTheme("dark")                       # force a theme; StyleSheet.setAdaptiveThemes(True) follows the system again
```

`StyleSheet.create(lambda theme: {...})` works too when the sheet does not need `rt`. Themed styles still behave as
plain dicts, so `[styles.card, {"opacity": 0.5}]`, `{**styles.card}` and `StyleSheet.flatten` work as usual.

Reference:

- `StyleSheet.configure(themes=None, breakpoints=None, adaptive_themes=True, initial_theme=None)`. camelCase
  (`adaptiveThemes`, `initialTheme`) works too. With themes named `light` and `dark` and adaptive themes on, the app
  follows the system color scheme. Otherwise it starts on `initial_theme`, or on the first theme.
- `StyleSheet.set_theme(name)` / `setTheme` picks a theme and turns adaptive themes off. An unknown name raises
  `ValueError`. `StyleSheet.set_adaptive_themes(on)` / `setAdaptiveThemes` turns system following on or off.
- `theme` is the theme dict with attribute access: `theme.colors.bg` equals `theme["colors"]["bg"]`. A missing key
  raises `AttributeError` with the key name.
- `rt` fields: `insets` (`top`, `right`, `bottom`, `left`), `breakpoint`, `color_scheme` / `colorScheme`,
  `theme_name` / `themeName`, `font_scale` / `fontScale`.
- A dynamic style is a function entry (`"avatar": lambda size: {...}`). Call it in the component:
  `styles.avatar(48)`. Each argument set is validated once and cached. Plain `StyleSheet.create({...})` accepts
  function entries as well.
- `useAppTheme()` / `use_app_theme()` returns the current theme and re-renders the component when the theme changes.
  Use it only for values that are not styles, such as icon colors. (`router.useTheme` is the navigation theme.)
- The same calls exist as functions in `pyxpo.themes`: `configure`, `set_theme`, `set_adaptive_themes`,
  `theme_name()` and `get(name)`.

A full example is `examples/imagekit` (`app/_theme.py`, `app/_ui.py`).

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
- Files under `app/` are routes: `index`, `[id]` (dynamic), `[...rest]` (catch-all), `(group)/` (no URL segment), `_layout.py` (navigator), `+not-found.py`. Files and folders whose name starts with `_` (for example `_lib/`) are not routes, so put helpers and library code there. A route module exports `default` (or has a single `@component`).
- Layouts: `Stack`, `Tabs`, `Drawer`, `Slot`; configure with `Stack.Screen(name=..., options={...})` or `screenOptions`. Options follow react-navigation (`title`, `headerShown`, `headerRight`, `tabBarIcon`, ...). A layout may export `unstable_settings = {"initialRouteName": ...}`.
- `router.push/navigate/replace/back/dismiss/dismissAll/setParams`, `<Link href=...>`, `<Redirect href=...>`; hooks `useRouter`, `useLocalSearchParams`, `useGlobalSearchParams`, `usePathname`, `useSegments`, `useNavigation`, `useIsFocused`, `useFocusEffect`. Theme: `ThemeProvider`, `DefaultTheme`, `DarkTheme`, `useTheme`.
- Android hardware back, the stack edge-swipe and the drawer all go through one navigation store. iOS Swift controls and the native stack are not ported yet.
