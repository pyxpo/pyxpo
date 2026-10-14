#import "PyxpoRuntime.h"
#include <Python.h>
#include "pyxpo_bridge.h"

static PyxpoRuntime *g_runtime;

/* Called on the Python thread. Copies the batch and hops to the main queue; never blocks. */
static void post_to_main(const char *json) {
    NSString *s = [NSString stringWithUTF8String:json];
    if (!s) return;
    dispatch_async(dispatch_get_main_queue(), ^{
        void (^cb)(NSString *) = g_runtime.onOps;
        if (cb) cb(s);
    });
}

@implementation PyxpoRuntime {
    dispatch_queue_t _eventQueue;
}

+ (instancetype)shared {
    static PyxpoRuntime *inst;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        inst = [PyxpoRuntime new];
        inst->_eventQueue = dispatch_queue_create("dev.pyxpo.events", DISPATCH_QUEUE_SERIAL);
        g_runtime = inst;
    });
    return inst;
}

- (void)startWithHome:(NSString *)home paths:(NSArray<NSString *> *)paths module:(NSString *)module {
    NSThread *t = [[NSThread alloc] initWithBlock:^{
        [self runWithHome:home paths:paths module:module];
    }];
    t.stackSize = 8 * 1024 * 1024;
    t.name = @"pyxpo-python";
    [t start];
}

- (void)runWithHome:(NSString *)home paths:(NSArray<NSString *> *)paths module:(NSString *)module {
    setenv("PYXPO_TARGET", "ios", 1);
    setenv("HOME", NSHomeDirectory().UTF8String, 1);
    setenv("TMPDIR", NSTemporaryDirectory().UTF8String, 1);

    pyxpo_bridge_set_post_callback(post_to_main);
    if (pyxpo_bridge_register() != 0) { NSLog(@"pyxpo: bridge register failed"); return; }

    PyStatus status;
    PyConfig config;
    NSMutableArray<NSString *> *all = nil;
    PyConfig_InitIsolatedConfig(&config);
    config.install_signal_handlers = 0;
    config.buffered_stdio = 0;
    config.write_bytecode = 0;
    config.module_search_paths_set = 1;

    wchar_t *whome = Py_DecodeLocale(home.UTF8String, NULL);
    status = PyConfig_SetString(&config, &config.home, whome);
    PyMem_RawFree(whome);
    if (PyStatus_Exception(status)) goto fail;

    all = [NSMutableArray arrayWithObjects:
        [home stringByAppendingPathComponent:@"lib/python3.13"],
        [home stringByAppendingPathComponent:@"lib/python3.13/lib-dynload"], nil];
    [all addObjectsFromArray:paths];
    for (NSString *p in all) {
        wchar_t *w = Py_DecodeLocale(p.UTF8String, NULL);
        status = PyWideStringList_Append(&config.module_search_paths, w);
        PyMem_RawFree(w);
        if (PyStatus_Exception(status)) goto fail;
    }

    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) goto fail_nocfg;

    /* Same as `python -m app.main`: apps call run_app() under `if __name__ == "__main__"`. */
    PyObject *runpy = PyImport_ImportModule("runpy");
    if (!runpy) { PyErr_Print(); }
    else {
        PyObject *r = PyObject_CallMethod(runpy, "run_module", "sOs", module.UTF8String, Py_None, "__main__");
        if (!r) PyErr_Print();
        Py_XDECREF(r);
        Py_DECREF(runpy);
    }
    Py_FinalizeEx();
    return;

fail:
    PyConfig_Clear(&config);
fail_nocfg:
    NSLog(@"pyxpo: python init failed: %s", status.err_msg ? status.err_msg : "?");
}

- (void)dispatchEvent:(NSString *)json {
    dispatch_async(_eventQueue, ^{
        pyxpo_bridge_dispatch_event(json.UTF8String);
    });
}

@end
