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
