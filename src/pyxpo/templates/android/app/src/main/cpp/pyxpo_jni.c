/* JNI glue: starts embedded CPython and relays the _pyxpo_bridge to Kotlin. */
#include <jni.h>
#include <Python.h>
#include <android/log.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include "pyxpo_bridge.h"
#include "pyxpo_utf.h"

#define TAG "pyxpo"
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

static JavaVM *g_vm;
static jobject g_runtime;       /* global ref to PyxpoRuntime instance */
static jmethodID g_on_ops;      /* void onOps(String) */

/* Java String -> real UTF-8 (malloc'd; free()). Not Get/NewStringUTF: JNI's modified UTF-8 encodes
 * non-BMP chars (emoji) as surrogate triplets, which Python's UTF-8 decoder rejects. */
static char *jstr_to_utf8(JNIEnv *env, jstring js) {
    if (js == NULL) return NULL;
    jsize n = (*env)->GetStringLength(env, js);
    const jchar *u = (*env)->GetStringChars(env, js, NULL);
    if (u == NULL) return NULL;
    char *out = pyxpo_utf16_to_utf8((const uint16_t *)u, (size_t)n, NULL);
    (*env)->ReleaseStringChars(env, js, u);
    return out;
}

static jstring utf8_to_jstr(JNIEnv *env, const char *s) {
    size_t n = 0;
    uint16_t *u = pyxpo_utf8_to_utf16(s, &n);
    if (u == NULL) return NULL;
    jstring out = (*env)->NewString(env, (const jchar *)u, (jsize)n);
    free(u);
    return out;
}

/* Called from the Python thread (GIL released by the bridge). */
static void post_to_java(const char *json) {
    JNIEnv *env = NULL;
    int attached = 0;
    if ((*g_vm)->GetEnv(g_vm, (void **)&env, JNI_VERSION_1_6) != JNI_OK) {
        if ((*g_vm)->AttachCurrentThread(g_vm, &env, NULL) != JNI_OK) return;
        attached = 1;
    }
    jstring s = utf8_to_jstr(env, json);
    if (s) {
        (*env)->CallVoidMethod(env, g_runtime, g_on_ops, s);
        (*env)->DeleteLocalRef(env, s);
    }
    if ((*env)->ExceptionCheck(env)) {
        (*env)->ExceptionDescribe(env);
        (*env)->ExceptionClear(env);
    }
    if (attached) (*g_vm)->DetachCurrentThread(g_vm);
}

static void setenv_utf8(JNIEnv *env, jstring k, jstring v) {
    char *ck = jstr_to_utf8(env, k);
    char *cv = jstr_to_utf8(env, v);
    if (ck && cv) setenv(ck, cv, 1);
    free(ck);
    free(cv);
}

JNIEXPORT void JNICALL
Java_dev_pyxpo_runtime_PyxpoRuntime_nativeSetEnv(JNIEnv *env, jobject thiz, jstring k, jstring v) {
    setenv_utf8(env, k, v);
}

/* Blocks until the Python app exits. Call from a dedicated thread (never the UI thread).
 * home: extracted dir holding lib/python3.13; sitePaths: ':'-separated extra sys.path entries. */
JNIEXPORT jint JNICALL
Java_dev_pyxpo_runtime_PyxpoRuntime_nativeStart(JNIEnv *env, jobject thiz, jstring jhome, jstring jpaths, jstring jmodule) {
    (*env)->GetJavaVM(env, &g_vm);
    g_runtime = (*env)->NewGlobalRef(env, thiz);
    jclass cls = (*env)->GetObjectClass(env, thiz);
    g_on_ops = (*env)->GetMethodID(env, cls, "onOps", "(Ljava/lang/String;)V");
    if (!g_on_ops) return -1;

    PyStatus status;
    int rc = 0;
    char *home = jstr_to_utf8(env, jhome);
    char *paths = jstr_to_utf8(env, jpaths);
    char *module = jstr_to_utf8(env, jmodule);
    if (!home || !paths || !module) { LOGE("out of memory"); rc = -2; goto out; }

    pyxpo_bridge_set_post_callback(post_to_java);
    if (pyxpo_bridge_register() != 0) { LOGE("bridge register failed"); rc = -2; goto out; }


    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);
    config.install_signal_handlers = 0;
    config.buffered_stdio = 0;
    config.module_search_paths_set = 1;

    wchar_t *whome = Py_DecodeLocale(home, NULL);
    status = PyConfig_SetString(&config, &config.home, whome);
    PyMem_RawFree(whome);
    if (PyStatus_Exception(status)) goto fail;

    /* module_search_paths: stdlib, lib-dynload, then app paths */
    char buf[4096];
    snprintf(buf, sizeof buf, "%s/lib/python3.13:%s/lib/python3.13/lib-dynload:%s", home, home, paths);
    for (char *tok = strtok(buf, ":"); tok; tok = strtok(NULL, ":")) {
        wchar_t *w = Py_DecodeLocale(tok, NULL);
        status = PyWideStringList_Append(&config.module_search_paths, w);
        PyMem_RawFree(w);
        if (PyStatus_Exception(status)) goto fail;
    }

    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) goto fail_nocfg;
    pyxpo_bridge_mark_running();

    /* Same as `python -m pyxpo.router.entry`: the entry calls run_app(). */
    PyObject *runpy = PyImport_ImportModule("runpy");
    if (!runpy) { PyErr_Print(); rc = -3; }
    else {
        PyObject *r = PyObject_CallMethod(runpy, "run_module", "sOs", module, Py_None, "__main__");
        if (!r) { PyErr_Print(); rc = -4; }
        Py_XDECREF(r);
        Py_DECREF(runpy);
    }
    /* Not plain Py_FinalizeEx(): events from the executor thread may be mid-flight. */
    pyxpo_bridge_finalize();
    goto out;

fail:
    PyConfig_Clear(&config);
fail_nocfg:
    LOGE("python init failed: %s", status.err_msg ? status.err_msg : "?");
    rc = -5;
out:
    free(home);
    free(paths);
    free(module);
    return rc;
}

/* Any thread (UI thread). Takes the GIL inside the bridge. */
JNIEXPORT void JNICALL
Java_dev_pyxpo_runtime_PyxpoRuntime_nativeDispatchEvent(JNIEnv *env, jobject thiz, jstring jjson) {
    char *json = jstr_to_utf8(env, jjson);
    if (json == NULL) return;
    pyxpo_bridge_dispatch_event(json);
    free(json);
}
