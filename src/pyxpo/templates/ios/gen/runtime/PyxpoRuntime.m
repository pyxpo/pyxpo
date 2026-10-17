#import <UIKit/UIKit.h>
#import "PyxpoRuntime.h"
#include <Python.h>
#include "pyxpo_bridge.h"

@interface PyxpoRuntime ()
- (void)markReady;
@end

static PyxpoRuntime *g_runtime;

/* Called on the Python thread. Copies the batch and hops to the main queue; never blocks. */
static void post_to_main(const char *json) {
    NSString *s = [NSString stringWithUTF8String:json];
    if (!s) return;
    dispatch_async(dispatch_get_main_queue(), ^{
        [g_runtime markReady];
        void (^cb)(NSString *) = g_runtime.onOps;
        if (cb) cb(s);
    });
}

@implementation PyxpoRuntime {
    dispatch_queue_t _eventQueue;
    BOOL _ready;                       /* guarded by @synchronized(self) */
    NSMutableArray<NSString *> *_pending;
}

/* Runs before main: lets linked modules start with the app (Swift `PxAppLaunchObserver`), whatever the user's AppDelegate. */
+ (void)load {
    [[NSNotificationCenter defaultCenter] addObserverForName:UIApplicationDidFinishLaunchingNotification object:nil
                                                       queue:nil usingBlock:^(NSNotification *n) {
        Class hooks = NSClassFromString(@"PxAppLaunch");
        SEL run = NSSelectorFromString(@"run:");
        if ([hooks respondsToSelector:run]) {
            void (*send)(id, SEL, id) = (void (*)(id, SEL, id))[hooks methodForSelector:run];
            send(hooks, run, n.userInfo);
        }
#if DEBUG
        [PyxpoRuntime startSnapshotWatcher];
#endif
    }];
}

#if DEBUG
/* Test hook: with PYXPO_SNAPSHOT_DIR set, writing a name into <dir>/req saves the key window as <dir>/<name>.png.
   Lets tools see the Mac app without screen-recording permission. */
+ (void)startSnapshotWatcher {
    const char *d = getenv("PYXPO_SNAPSHOT_DIR");
    if (!d) return;
    NSString *dir = [NSString stringWithUTF8String:d];
    NSString *req = [dir stringByAppendingPathComponent:@"req"];
    [NSTimer scheduledTimerWithTimeInterval:0.3 repeats:YES block:^(NSTimer *t) {
        NSString *name = [[NSString stringWithContentsOfFile:req encoding:NSUTF8StringEncoding error:nil]
                          stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
        if (!name.length) return;
        [[NSFileManager defaultManager] removeItemAtPath:req error:nil];
        UIWindow *w = nil;
        for (UIScene *s in UIApplication.sharedApplication.connectedScenes)
            if ([s isKindOfClass:UIWindowScene.class])
                for (UIWindow *x in ((UIWindowScene *)s).windows) if (x.isKeyWindow || !w) w = x;
        if (!w) return;
        UIGraphicsImageRenderer *r = [[UIGraphicsImageRenderer alloc] initWithBounds:w.bounds];
        UIImage *img = [r imageWithActions:^(UIGraphicsImageRendererContext *c) {
            [w drawViewHierarchyInRect:w.bounds afterScreenUpdates:NO];
        }];
        [UIImagePNGRepresentation(img) writeToFile:[dir stringByAppendingPathComponent:[name stringByAppendingString:@".png"]]
                                        atomically:YES];
    }];
}
#endif

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

// The folder Python sees as HOME, laid out like an iOS app container (Documents, Library/Caches,
// Library/Application Support). On iOS that is the app's sandbox. A Mac Catalyst build outside the App Sandbox
// gets the user's real home folder from NSHomeDirectory(), so it uses ~/Library/Application Support/<bundle id>.
static NSString *PyxpoAppHome(void) {
    NSString *home = NSHomeDirectory();
#if TARGET_OS_MACCATALYST
    if (!NSProcessInfo.processInfo.environment[@"APP_SANDBOX_CONTAINER_ID"]) {
        NSString *support = NSSearchPathForDirectoriesInDomains(NSApplicationSupportDirectory, NSUserDomainMask, YES).firstObject;
        NSString *bundle = NSBundle.mainBundle.bundleIdentifier ?: @"pyxpo.app";
        if (support) home = [support stringByAppendingPathComponent:bundle];
    }
    NSFileManager *fm = NSFileManager.defaultManager;
    for (NSString *sub in @[@"Documents", @"Library/Caches", @"Library/Application Support"]) {
        [fm createDirectoryAtPath:[home stringByAppendingPathComponent:sub] withIntermediateDirectories:YES
                       attributes:nil error:NULL];
    }
#endif
    return home;
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
    if (self.envJSON) setenv("PYXPO_ENV", self.envJSON.UTF8String, 1);
    setenv("HOME", PyxpoAppHome().UTF8String, 1);
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
    pyxpo_bridge_mark_running();
    /* Python sends print() to the unified log on Apple platforms. `pyxpo run desktop` starts the Mac app from a
       terminal and sets PYXPO_STDIO, so output goes to that terminal instead. */
    if (getenv("PYXPO_STDIO")) {
        PyRun_SimpleString("import io, sys\n"
                           "sys.stdout = io.TextIOWrapper(io.FileIO(1, 'w', closefd=False), line_buffering=True)\n"
                           "sys.stderr = io.TextIOWrapper(io.FileIO(2, 'w', closefd=False), line_buffering=True)\n");
    }

    /* Same as `python -m pyxpo.router.entry`: the entry calls run_app(). */
    PyObject *runpy = PyImport_ImportModule("runpy");
    if (!runpy) { PyErr_Print(); }
    else {
        PyObject *r = PyObject_CallMethod(runpy, "run_module", "sOs", module.UTF8String, Py_None, "__main__");
        if (!r) PyErr_Print();
        Py_XDECREF(r);
        Py_DECREF(runpy);
    }
    /* Not plain Py_FinalizeEx(): events on _eventQueue may be mid-flight. */
    pyxpo_bridge_finalize();
    return;

fail:
    PyConfig_Clear(&config);
fail_nocfg:
    NSLog(@"pyxpo: python init failed: %s", status.err_msg ? status.err_msg : "?");
}

/* Events before the first ops batch would hit an uninitialised interpreter: hold them until Python is up. */
- (void)markReady {
    NSArray<NSString *> *q;
    @synchronized (self) {
        if (_ready) return;
        _ready = YES;
        q = _pending;
        _pending = nil;
    }
    for (NSString *j in q) [self dispatchEvent:j];
}

- (void)dispatchEvent:(NSString *)json {
    @synchronized (self) {
        if (!_ready) {
            if (!_pending) _pending = [NSMutableArray new];
            [_pending addObject:json];
            return;
        }
    }
    dispatch_async(_eventQueue, ^{
        /* UTF8String is NULL for strings with lone surrogates; fall back to a lossy (U+FFFD) copy. */
        const char *utf8 = json.UTF8String;
        if (utf8) {
            pyxpo_bridge_dispatch_event(utf8);
        } else {
            NSMutableData *d = [[json dataUsingEncoding:NSUTF8StringEncoding allowLossyConversion:YES] mutableCopy];
            if (!d) return;
            [d appendBytes:"" length:1];
            pyxpo_bridge_dispatch_event(d.bytes);
        }
    });
}

@end
