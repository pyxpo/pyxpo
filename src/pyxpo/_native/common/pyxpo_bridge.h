#ifndef PYXPO_BRIDGE_H
#define PYXPO_BRIDGE_H

/* Called on the Python thread with a UTF-8 JSON ops batch. Must copy what it needs and return quickly. */
typedef void (*pyxpo_post_fn)(const char *json_utf8);

/* Host sets this before Python starts running app code. */
void pyxpo_bridge_set_post_callback(pyxpo_post_fn fn);

/* Register builtin module `_pyxpo_bridge`. Call BEFORE Py_Initialize*. Returns 0 on success. */
int pyxpo_bridge_register(void);

/* Call on the Python thread right after Py_Initialize* succeeded: enables event delivery.
 * Until then pyxpo_bridge_dispatch_event() refuses (returns -1) instead of touching a half-built runtime. */
void pyxpo_bridge_mark_running(void);

/* Use INSTEAD of Py_FinalizeEx(), on the thread that initialised Python (holding the GIL).
 * Stops new event deliveries, waits (GIL released) for in-flight ones, drops the handler, then
 * finalizes. Returns Py_FinalizeEx()'s result. */
int pyxpo_bridge_finalize(void);

/* Native -> Python event delivery. Safe to call from any thread at any time (takes the GIL);
 * returns -1 without touching Python when the runtime is not running. Returns 0 on success. */
int pyxpo_bridge_dispatch_event(const char *json_utf8);

#endif
