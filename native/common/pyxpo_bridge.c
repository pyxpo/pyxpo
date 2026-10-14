#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "pyxpo_bridge.h"

static pyxpo_post_fn g_post = NULL;
static PyObject *g_handler = NULL; /* guarded by the GIL */

void pyxpo_bridge_set_post_callback(pyxpo_post_fn fn) { g_post = fn; }

static PyObject *bridge_post(PyObject *self, PyObject *arg) {
    const char *s = PyUnicode_AsUTF8(arg);
    if (s == NULL) return NULL;
    if (g_post == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "pyxpo: no native post callback registered");
        return NULL;
    }
    /* Copy so native can keep the string after we return; callback runs without the GIL. */
    char *copy = PyMem_RawMalloc(strlen(s) + 1);
    if (copy == NULL) return PyErr_NoMemory();
    strcpy(copy, s);
    Py_BEGIN_ALLOW_THREADS
    g_post(copy);
    Py_END_ALLOW_THREADS
    PyMem_RawFree(copy);
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

int pyxpo_bridge_dispatch_event(const char *json_utf8) {
    int rc = 0;
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
    return rc;
}
