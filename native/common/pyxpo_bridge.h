#ifndef PYXPO_BRIDGE_H
#define PYXPO_BRIDGE_H

/* Called on the Python thread with a UTF-8 JSON ops batch. Must copy what it needs and return quickly. */
typedef void (*pyxpo_post_fn)(const char *json_utf8);

/* Host sets this before Python starts running app code. */
void pyxpo_bridge_set_post_callback(pyxpo_post_fn fn);

/* Register builtin module `_pyxpo_bridge`. Call BEFORE Py_Initialize*. Returns 0 on success. */
int pyxpo_bridge_register(void);

/* Native -> Python event delivery. Safe to call from any thread (takes the GIL). Returns 0 on success. */
int pyxpo_bridge_dispatch_event(const char *json_utf8);

#endif
