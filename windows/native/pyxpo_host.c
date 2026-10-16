/* pyxpo_native.dll host part: starts the embedded CPython on its own thread for the WinUI shell.
 *
 * The shell (C#) calls pyxpo_host_start() once with the paths it worked out, then sends events with
 * pyxpo_host_dispatch(). Ops batches come back on the Python thread through the post callback; the shell
 * copies the string and hands it to its UI thread. The layout engine (pyxpo_layout.c) is exported from the
 * same DLL, see pyxpo_native.def. */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <windows.h>
#include <stdlib.h>
#include <wchar.h>

#include "pyxpo_bridge.h"

typedef struct {
    wchar_t *home;
    wchar_t *paths; /* ';'-separated, extra to the stdlib */
    char *module;
} StartArgs;

static wchar_t *wdup(const wchar_t *s) { return s ? _wcsdup(s) : NULL; }
static char *dup(const char *s) { return s ? _strdup(s) : NULL; }

static void report(const char *what, PyStatus st) {
    fprintf(stderr, "pyxpo: %s: %s\n", what, st.err_msg ? st.err_msg : "?");
    fflush(stderr);
}

static PyStatus append_path(PyConfig *c, const wchar_t *a, const wchar_t *b) {
    wchar_t buf[4096];
    if (b) _snwprintf_s(buf, 4096, _TRUNCATE, L"%s\\%s", a, b);
    else wcsncpy_s(buf, 4096, a, _TRUNCATE);
    return PyWideStringList_Append(&c->module_search_paths, buf);
}

/* Same steps as PyxpoRuntime.m on iOS. */
static DWORD WINAPI python_main(LPVOID arg) {
    StartArgs *a = (StartArgs *)arg;
    PyStatus st;
    PyConfig config;
    PyPreConfig pre;

    if (pyxpo_bridge_register() != 0) { fprintf(stderr, "pyxpo: bridge register failed\n"); goto done; }

    PyPreConfig_InitIsolatedConfig(&pre);
    pre.utf8_mode = 1; /* file and console text is UTF-8, not the ANSI code page */
    st = Py_PreInitialize(&pre);
    if (PyStatus_Exception(st)) { report("python preinit failed", st); goto done; }

    PyConfig_InitIsolatedConfig(&config);
    config.install_signal_handlers = 0;
    config.buffered_stdio = 0;
    config.write_bytecode = 0;
    config.module_search_paths_set = 1;
    st = PyConfig_SetString(&config, &config.home, a->home);
    if (PyStatus_Exception(st)) goto fail;
    /* The embeddable distribution: stdlib in python313.zip, extension modules (.pyd) next to it. */
    st = append_path(&config, a->home, L"python313.zip");
    if (PyStatus_Exception(st)) goto fail;
    st = append_path(&config, a->home, NULL);
    if (PyStatus_Exception(st)) goto fail;
    if (a->paths) {
        wchar_t *ctx = NULL;
        for (wchar_t *p = wcstok_s(a->paths, L";", &ctx); p; p = wcstok_s(NULL, L";", &ctx)) {
            st = append_path(&config, p, NULL);
            if (PyStatus_Exception(st)) goto fail;
        }
    }
    st = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(st)) { report("python init failed", st); goto done; }
    pyxpo_bridge_mark_running();

    /* `pyxpo run desktop` reads the app's output through a pipe; line buffering shows each print at once. */
    if (getenv("PYXPO_STDIO")) {
        PyRun_SimpleString("import io, sys\n"
                           "try:\n"
                           "    sys.stdout = io.TextIOWrapper(io.FileIO(1, 'w', closefd=False), 'utf-8', line_buffering=True)\n"
                           "    sys.stderr = io.TextIOWrapper(io.FileIO(2, 'w', closefd=False), 'utf-8', line_buffering=True)\n"
                           "except OSError:\n"
                           "    pass\n");
    }

    {
        PyObject *runpy = PyImport_ImportModule("runpy");
        if (!runpy) PyErr_Print();
        else {
            PyObject *r = PyObject_CallMethod(runpy, "run_module", "sOs", a->module, Py_None, "__main__");
            if (!r) PyErr_Print();
            Py_XDECREF(r);
            Py_DECREF(runpy);
        }
    }
    pyxpo_bridge_finalize();
    goto done;

fail:
    PyConfig_Clear(&config);
    report("python config failed", st);
done:
    free(a->home);
    free(a->paths);
    free(a->module);
    free(a);
    return 0;
}

/* Starts Python. home: the CPython directory; paths: app search paths, ';'-separated; module: entry module run
 * as __main__; env_json: first environment snapshot (PYXPO_ENV) or NULL; post: receives every ops batch.
 * Returns 0 when the thread started. */
__declspec(dllexport) int pyxpo_host_start(const wchar_t *home, const wchar_t *paths, const char *module,
                                           const char *env_json, pyxpo_post_fn post) {
    StartArgs *a;
    HANDLE t;
    _putenv_s("PYXPO_TARGET", "windows");
    if (env_json) _putenv_s("PYXPO_ENV", env_json);
    pyxpo_bridge_set_post_callback(post);
    a = (StartArgs *)calloc(1, sizeof(StartArgs));
    if (!a) return -1;
    a->home = wdup(home);
    a->paths = wdup(paths);
    a->module = dup(module ? module : "pyxpo.router.entry");
    t = CreateThread(NULL, 8 * 1024 * 1024, python_main, a, STACK_SIZE_PARAM_IS_A_RESERVATION, NULL);
    if (!t) { free(a->home); free(a->paths); free(a->module); free(a); return -1; }
    CloseHandle(t);
    return 0;
}

/* Native -> Python event. Any thread; -1 while Python is not running. */
__declspec(dllexport) int pyxpo_host_dispatch(const char *json) { return pyxpo_bridge_dispatch_event(json); }
