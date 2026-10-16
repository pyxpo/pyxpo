using System;
using System.IO;
using System.Runtime.InteropServices;

namespace Pyxpo;

/// pyxpo_native.dll: the layout engine (pyxpo_layout.c, same C code as iOS and Android) and the embedded Python
/// host (pyxpo_host.c). The DLL sits next to the exe and links python313.dll, which lives in python/.
static unsafe class Native
{
    const string Dll = "pyxpo_native";

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    public delegate void MeasureFn(IntPtr ctx, int id, float w, int wMode, float h, int hMode, float* ow, float* oh);

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    public delegate void PostFn(IntPtr json);

    [DllImport(Dll)] public static extern IntPtr px_tree_new(MeasureFn fn, IntPtr ctx);
    [DllImport(Dll)] public static extern void px_tree_free(IntPtr t);
    [DllImport(Dll)] public static extern int px_node_create(IntPtr t, int id);
    [DllImport(Dll)] public static extern int px_node_delete(IntPtr t, int id);
    [DllImport(Dll)] public static extern int px_node_insert(IntPtr t, int parent, int child, int index);
    [DllImport(Dll)] public static extern int px_node_remove(IntPtr t, int parent, int child);
    [DllImport(Dll)] public static extern int px_node_set_measured(IntPtr t, int id, int measured);
    [DllImport(Dll)] public static extern int px_node_mark_dirty(IntPtr t, int id);
    [DllImport(Dll)] public static extern int px_prop_id([MarshalAs(UnmanagedType.LPUTF8Str)] string name);
    [DllImport(Dll)] public static extern int px_node_set_num(IntPtr t, int id, int prop, float value);
    [DllImport(Dll)] public static extern int px_node_set_str(IntPtr t, int id, int prop, [MarshalAs(UnmanagedType.LPUTF8Str)] string value);
    [DllImport(Dll)] public static extern int px_node_reset(IntPtr t, int id, int prop);
    [DllImport(Dll)] public static extern int px_tree_calc(IntPtr t, float width, float height);
    [DllImport(Dll)] public static extern int px_tree_changed_count(IntPtr t);
    [DllImport(Dll)] public static extern int px_tree_changed_at(IntPtr t, int i, float* xywh);
    [DllImport(Dll)] public static extern int px_node_frame(IntPtr t, int id, float* xywh);

    [DllImport(Dll, CharSet = CharSet.Unicode)]
    public static extern int pyxpo_host_start(string home, string paths, [MarshalAs(UnmanagedType.LPUTF8Str)] string module,
                                              [MarshalAs(UnmanagedType.LPUTF8Str)] string? envJson, PostFn post);

    [DllImport(Dll)] public static extern int pyxpo_host_dispatch([MarshalAs(UnmanagedType.LPUTF8Str)] string json);

    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool SetDllDirectoryW(string path);

    /// python313.dll is in <exe>\python, not on the DLL search path: load it first so pyxpo_native.dll resolves it.
    public static void Load(string exeDir)
    {
        var py = Path.Combine(exeDir, "python");
        SetDllDirectoryW(py);
        NativeLibrary.Load(Path.Combine(py, "python313.dll"));
        NativeLibrary.Load(Path.Combine(exeDir, "pyxpo_native.dll"));
    }
}
