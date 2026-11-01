# R8 rules for the pyxpo runtime (regenerated on every build).
# C calls these by name through JNI (pyxpo_jni.c, pyxpo_layout_jni.c).
-keepclasseswithmembernames,includedescriptorclasses class * { native <methods>; }
-keep class dev.pyxpo.runtime.PyxpoRuntime { void onOps(java.lang.String); }
-keep class dev.pyxpo.runtime.NativeLayout { long measure(int, float, int, float, int); }
# PxProcess.start finds this by reflection (module-api PxModule.kt).
-keep class dev.pyxpo.runtime.PyxpoRuntime { public static void startHeadless(android.content.Context); }
