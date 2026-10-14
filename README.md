# Pyxpo (working name)

React-Native-style Python framework: declarative components + hooks -> reconciler -> batched JSON ops -> native widgets.
See DESIGN.md (architecture) and PLAN.md (roadmap). **Milestone 1 (pure-Python core + desktop console preview) is implemented.** Android/iOS shells are not yet built.

## Quickstart
```
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pyxpo create demo && cd demo && ../.venv/bin/pyxpo run desktop   # type 1 + Enter to press the button, q to quit
.venv/bin/pytest
```

```python
from pyxpo import component, use_state, View, Text, Button, run_app

@component
def Counter():
    n, set_n = use_state(0)
    return View(Text("Count: ", n), Button("Add", on_press=lambda: set_n(lambda c: c + 1)))

run_app(Counter)
```

Hooks: use_state, use_effect, use_ref, use_memo, use_callback, use_context, use_async. Lists need `key=`.
`pyxpo add-lib <pkg>` checks mobile wheel availability (note: full tensorflow/torch cannot run on mobile).

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
- RN style values that have no native equivalent (`borderStyle`, `tintColor`, `resizeMode`, ...) log a warning and are ignored. `Pressable` `hit_slop` and `delay_long_press` are not supported.
- Example: `examples/rn_style`.
