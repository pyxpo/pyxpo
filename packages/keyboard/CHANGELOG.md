# Changelog

## 0.1.0a1 (unreleased)

- First release. Android: a system keyboard (`InputMethodService`) with native QWERTY, symbol, number and phone
  layouts, shift and caps lock, long-press alternates, delete repeat, double-space period, auto-capitals, the
  editor's enter action, a switch-keyboard key and an emoji panel. Password, PIN and incognito fields are marked
  private. App calls: `status`, `open_settings`, `show_picker`, `get_options`, `set_options`.
- iOS: `status` reports the keyboard as unsupported; `open_settings` opens the app's Settings page.
- Light/dark switches while the keyboard is open redraw the keys in place (Android 14+), and the keys stay above
  the navigation bar on edge-to-edge Android 15+.
- The web and the desktop return the defaults for every call.
- README with emulator screenshots.
- App toolbar buttons (Android): `set_toolbar_async`, `set_status_async`, `get_field_async`, `commit_text_async`,
  `get_text_async`, `add_toolbar_listener`, `add_input_listener`. A tap starts the app's Python headless; private
  fields hide the buttons and refuse text calls. `status` adds `showing`. Needs native contract 4.
