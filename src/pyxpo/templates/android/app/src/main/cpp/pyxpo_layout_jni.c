/* JNI wrapper for the shared flexbox engine. Every call comes from the UI thread. */
#include <jni.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "pyxpo_layout.h"

typedef struct {
    JavaVM *vm;
    jobject obj;        /* global ref to NativeLayout */
    jmethodID measure;  /* long measure(int id, float w, int wm, float h, int hm) */
    PxTree *tree;
} Ctx;

static void measure_cb(void *p, int id, float w, int wm, float h, int hm, float *ow, float *oh) {
    Ctx *c = (Ctx *)p;
    JNIEnv *env = NULL;
    *ow = *oh = 0;
    if ((*c->vm)->GetEnv(c->vm, (void **)&env, JNI_VERSION_1_6) != JNI_OK) return;
    jlong r = (*env)->CallLongMethod(env, c->obj, c->measure, id, w, wm, h, hm);
    if ((*env)->ExceptionCheck(env)) { (*env)->ExceptionClear(env); return; }
    uint32_t wb = (uint32_t)((uint64_t)r >> 32), hb = (uint32_t)((uint64_t)r & 0xffffffffu);
    memcpy(ow, &wb, 4);
    memcpy(oh, &hb, 4);
}

#define FN(name) Java_dev_pyxpo_runtime_NativeLayout_##name
#define TREE(p) (((Ctx *)(intptr_t)(p))->tree)

JNIEXPORT jlong JNICALL FN(nCreate)(JNIEnv *env, jobject thiz) {
    Ctx *c = (Ctx *)calloc(1, sizeof *c);
    if (!c) return 0;
    (*env)->GetJavaVM(env, &c->vm);
    c->obj = (*env)->NewGlobalRef(env, thiz);
    jclass cls = (*env)->GetObjectClass(env, thiz);
    c->measure = (*env)->GetMethodID(env, cls, "measure", "(IFIFI)J");
    c->tree = px_tree_new(measure_cb, c);
    if (!c->measure || !c->tree) { free(c); return 0; }
    return (jlong)(intptr_t)c;
}

JNIEXPORT void JNICALL FN(nFree)(JNIEnv *env, jobject thiz, jlong p) {
    Ctx *c = (Ctx *)(intptr_t)p;
    if (!c) return;
    px_tree_free(c->tree);
    (*env)->DeleteGlobalRef(env, c->obj);
    free(c);
}

JNIEXPORT jint JNICALL FN(nNodeCreate)(JNIEnv *env, jobject t, jlong p, jint id) { return px_node_create(TREE(p), id); }
JNIEXPORT jint JNICALL FN(nNodeDelete)(JNIEnv *env, jobject t, jlong p, jint id) { return px_node_delete(TREE(p), id); }
JNIEXPORT jint JNICALL FN(nInsert)(JNIEnv *env, jobject t, jlong p, jint parent, jint child, jint idx) {
    return px_node_insert(TREE(p), parent, child, idx);
}
JNIEXPORT jint JNICALL FN(nRemove)(JNIEnv *env, jobject t, jlong p, jint parent, jint child) {
    return px_node_remove(TREE(p), parent, child);
}
JNIEXPORT jint JNICALL FN(nSetMeasured)(JNIEnv *env, jobject t, jlong p, jint id, jint f) {
    return px_node_set_measured(TREE(p), id, f);
}
JNIEXPORT jint JNICALL FN(nMarkDirty)(JNIEnv *env, jobject t, jlong p, jint id) { return px_node_mark_dirty(TREE(p), id); }
JNIEXPORT jint JNICALL FN(nSetNum)(JNIEnv *env, jobject t, jlong p, jint id, jint prop, jfloat v) {
    return px_node_set_num(TREE(p), id, prop, v);
}
JNIEXPORT jint JNICALL FN(nSetStr)(JNIEnv *env, jobject t, jlong p, jint id, jint prop, jstring s) {
    const char *cs = (*env)->GetStringUTFChars(env, s, NULL);
    int r = px_node_set_str(TREE(p), id, prop, cs);
    (*env)->ReleaseStringUTFChars(env, s, cs);
    return r;
}
JNIEXPORT jint JNICALL FN(nReset)(JNIEnv *env, jobject t, jlong p, jint id, jint prop) {
    return px_node_reset(TREE(p), id, prop);
}
JNIEXPORT jint JNICALL FN(nPropId)(JNIEnv *env, jobject t, jstring s) {
    const char *cs = (*env)->GetStringUTFChars(env, s, NULL);
    int r = px_prop_id(cs);
    (*env)->ReleaseStringUTFChars(env, s, cs);
    return r;
}

/* Runs layout and copies changed frames to out as [id, x, y, w, h] * n. Returns n (capped by out size). */
JNIEXPORT jint JNICALL FN(nCalc)(JNIEnv *env, jobject t, jlong p, jfloat w, jfloat h, jfloatArray out) {
    PxTree *tr = TREE(p);
    int n = px_tree_calc(tr, w, h);
    if (n <= 0) return n;
    int cap = (*env)->GetArrayLength(env, out) / 5;
    if (n > cap) return -n; /* caller grows the array and calls nChanged */
    float *buf = (*env)->GetFloatArrayElements(env, out, NULL);
    for (int i = 0; i < n; i++) {
        float f[4];
        buf[i * 5] = (float)px_tree_changed_at(tr, i, f);
        memcpy(&buf[i * 5 + 1], f, sizeof f);
    }
    (*env)->ReleaseFloatArrayElements(env, out, buf, 0);
    return n;
}

JNIEXPORT jint JNICALL FN(nChanged)(JNIEnv *env, jobject t, jlong p, jfloatArray out) {
    PxTree *tr = TREE(p);
    int n = px_tree_changed_count(tr);
    int cap = (*env)->GetArrayLength(env, out) / 5;
    if (n > cap) n = cap;
    float *buf = (*env)->GetFloatArrayElements(env, out, NULL);
    for (int i = 0; i < n; i++) {
        float f[4];
        buf[i * 5] = (float)px_tree_changed_at(tr, i, f);
        memcpy(&buf[i * 5 + 1], f, sizeof f);
    }
    (*env)->ReleaseFloatArrayElements(env, out, buf, 0);
    return n;
}
