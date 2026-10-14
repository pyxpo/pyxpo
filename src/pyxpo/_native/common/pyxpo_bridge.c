#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <pthread.h>
#include "pyxpo_bridge.h"

static pyxpo_post_fn g_post = NULL;
static PyObject *g_handler = NULL; /* guarded by the GIL */

/* Runtime lifecycle, so event delivery from other threads never touches a runtime that is
 * still initialising or already finalizing/finalized. All guarded by g_lock. */
enum { RT_DOWN = 0, RT_RUNNING, RT_FINALIZING };
static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t g_idle = PTHREAD_COND_INITIALIZER;
static int g_state = RT_DOWN;
static int g_inflight = 0; /* dispatch_event calls past the state check */

void pyxpo_bridge_set_post_callback(pyxpo_post_fn fn) { g_post = fn; }

static PyObject *bridge_post(PyObject *self, PyObject *arg) {
    if (g_post == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "pyxpo: no native post callback registered");
        return NULL;
    }
    const char *s = PyUnicode_AsUTF8(arg); /* buffer owned by arg */
    if (s == NULL) return NULL;
    /* Hold arg so its UTF-8 buffer outlives the GIL-free callback (which copies what it keeps). */
    Py_INCREF(arg);
    Py_BEGIN_ALLOW_THREADS
    g_post(s);
    Py_END_ALLOW_THREADS
    Py_DECREF(arg);
    Py_RETURN_NONE;
}

static PyObject *bridge_set_event_handler(PyObject *self, PyObject *fn) {
    if (fn != Py_None && !PyCallable_Check(fn)) {
        PyErr_SetString(PyExc_TypeError, "handler must be callable or None");
        return NULL;
    }
    Py_XDECREF(g_handler);
    g_handler = NULL;
    if (fn != Py_None) {
        Py_INCREF(fn);
        g_handler = fn;
    }
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"post", bridge_post, METH_O, "post(json: str) -> None: send an ops batch to native."},
    {"set_event_handler", bridge_set_event_handler, METH_O, "set_event_handler(fn | None): receive native events."},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "_pyxpo_bridge", NULL, -1, methods};

static PyObject *init_module(void) { return PyModule_Create(&module); }

int pyxpo_bridge_register(void) { return PyImport_AppendInittab("_pyxpo_bridge", init_module); }

void pyxpo_bridge_mark_running(void) {
    pthread_mutex_lock(&g_lock);
    g_state = RT_RUNNING;
    pthread_mutex_unlock(&g_lock);
}

int pyxpo_bridge_finalize(void) {
    pthread_mutex_lock(&g_lock);
    g_state = RT_FINALIZING;
    pthread_mutex_unlock(&g_lock);
    /* In-flight dispatchers may be waiting for the GIL we hold: release it while draining. */
    Py_BEGIN_ALLOW_THREADS
    pthread_mutex_lock(&g_lock);
    while (g_inflight > 0) pthread_cond_wait(&g_idle, &g_lock);
    pthread_mutex_unlock(&g_lock);
    Py_END_ALLOW_THREADS
    Py_CLEAR(g_handler); /* never leave a dangling pointer across finalize */
    int rc = Py_FinalizeEx();
    pthread_mutex_lock(&g_lock);
    g_state = RT_DOWN;
    pthread_mutex_unlock(&g_lock);
    return rc;
}

int pyxpo_bridge_dispatch_event(const char *json_utf8) {
    int rc = 0;
    if (json_utf8 == NULL) return -1;
    pthread_mutex_lock(&g_lock);
    if (g_state != RT_RUNNING) { /* not started yet, or finalizing: drop, never touch Python */
        pthread_mutex_unlock(&g_lock);
        return -1;
    }
    g_inflight++;
    pthread_mutex_unlock(&g_lock);

    PyGILState_STATE gil = PyGILState_Ensure();
    if (g_handler == NULL) {
        rc = -1;
    } else {
        PyObject *arg = PyUnicode_FromString(json_utf8);
        PyObject *res = arg ? PyObject_CallOneArg(g_handler, arg) : NULL;
        Py_XDECREF(arg);
        if (res == NULL) {
            PyErr_Print();
            rc = -1;
        }
        Py_XDECREF(res);
    }
    PyGILState_Release(gil);

    pthread_mutex_lock(&g_lock);
    if (--g_inflight == 0) pthread_cond_broadcast(&g_idle);
    pthread_mutex_unlock(&g_lock);
    return rc;
}
