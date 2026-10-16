using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Text.Json.Nodes;
using System.Threading;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Graphics.Imaging;
using Windows.Storage.Streams;

namespace Pyxpo;

/// pyxpo-app.json, written by `pyxpo build desktop` next to the exe.
sealed class AppConfig
{
    public string Title = "Pyxpo";
    public int Width = 1024, Height = 768;
    public string Module = "pyxpo.router.entry";
    public uint? Background;
    public string? Style; // "light" / "dark" locks the theme

    public static AppConfig Load(string exeDir)
    {
        var c = new AppConfig();
        var p = Path.Combine(exeDir, "pyxpo-app.json");
        if (!File.Exists(p)) return c;
        try
        {
            if (JsonNode.Parse(File.ReadAllText(p)) is not JsonObject o) return c;
            c.Title = Js.Str(o["title"]) ?? c.Title;
            c.Width = Js.I(o["width"]) is > 0 and var w ? w : c.Width;
            c.Height = Js.I(o["height"]) is > 0 and var h ? h : c.Height;
            c.Module = Js.Str(o["module"]) ?? c.Module;
            c.Background = Js.Color(o["background_color"]);
            c.Style = Js.Str(o["user_interface_style"]);
        }
        catch (Exception e) { Console.Error.WriteLine("pyxpo: bad pyxpo-app.json: " + e.Message); }
        return c;
    }
}

/// Embedded Python and the event channel. Python runs on its own thread (pyxpo_host.c); ops batches come back
/// through the post callback and are applied on the UI thread. Events go to Python from one serial thread, in
/// order, and wait in a pending list until Python's first batch shows that it is listening.
sealed class Runtime
{
    static Native.PostFn? post; // kept alive: the bridge holds a pointer to it
    static Runtime? current;

    readonly DispatcherQueue ui;
    readonly BlockingCollection<string> outbox = new();
    readonly object gate = new();
    List<string>? pending = new();
    public readonly OpApplier Applier;

    public Runtime(DispatcherQueue ui)
    {
        this.ui = ui;
        current = this;
        Applier = new OpApplier(Send);
        new Thread(SendLoop) { IsBackground = true, Name = "pyxpo-events" }.Start();
    }

    public bool Start(string exeDir, string module, JsonObject env)
    {
        post = OnPost;
        var paths = Path.Combine(exeDir, "app") + ";" + Path.Combine(exeDir, "app_packages");
        int r = Native.pyxpo_host_start(Path.Combine(exeDir, "python"), paths, module, env.ToJsonString(), post);
        if (r != 0) Console.Error.WriteLine("pyxpo: python failed to start");
        return r == 0;
    }

    /// Python thread: copy the batch (the pointer is only valid during the call), then apply it on the UI thread.
    static void OnPost(IntPtr json)
    {
        var s = Marshal.PtrToStringUTF8(json);
        var rt = current;
        if (s == null || rt == null) return;
        rt.ui.TryEnqueue(() =>
        {
            rt.Applier.Apply(s);
            rt.Release();
        });
    }

    void Release()
    {
        List<string>? q;
        lock (gate)
        {
            q = pending;
            pending = null;
        }
        if (q != null) foreach (var j in q) outbox.Add(j);
    }

    void Send(string json)
    {
        lock (gate)
        {
            if (pending != null) { pending.Add(json); return; }
        }
        outbox.Add(json);
    }

    void SendLoop()
    {
        foreach (var j in outbox.GetConsumingEnumerable())
        {
            // -1: Python is not running (it stopped, or is restarting). Drop the event, as the iOS shell does.
            try { Native.pyxpo_host_dispatch(j); }
            catch (Exception e) { Console.Error.WriteLine("pyxpo: dispatch failed: " + e.Message); }
        }
    }

    // -- test hook -----------------------------------------------------------------------------------
    /// With PYXPO_SNAPSHOT_DIR set, writing a name into <dir>/req saves the window content as <dir>/<name>.png
    /// (same contract as the iOS and Mac shells; CI uses it).
    public static void StartSnapshotHook(DispatcherQueue ui, Func<UIElement> target)
    {
        var dir = Environment.GetEnvironmentVariable("PYXPO_SNAPSHOT_DIR");
        if (string.IsNullOrEmpty(dir)) return;
        var timer = ui.CreateTimer();
        timer.Interval = TimeSpan.FromSeconds(0.3);
        bool busy = false;
        timer.Tick += async (_, _) =>
        {
            var req = Path.Combine(dir, "req");
            if (busy || !File.Exists(req)) return;
            busy = true;
            try
            {
                var name = File.ReadAllText(req).Trim();
                File.Delete(req);
                if (name.Length == 0) return;
                var rtb = new RenderTargetBitmap();
                await rtb.RenderAsync(target());
                var px = await rtb.GetPixelsAsync();
                var tmp = Path.Combine(dir, name + ".png.tmp");
                using (var ras = new InMemoryRandomAccessStream())
                {
                    var enc = await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId, ras);
                    enc.SetPixelData(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied, (uint)rtb.PixelWidth,
                                     (uint)rtb.PixelHeight, 96, 96, px.ToArray());
                    await enc.FlushAsync();
                    var bytes = new byte[ras.Size];
                    ras.Seek(0);
                    await ras.ReadAsync(bytes.AsBuffer(), (uint)ras.Size, InputStreamOptions.None);
                    File.WriteAllBytes(tmp, bytes);
                }
                File.Move(tmp, Path.Combine(dir, name + ".png"), true);
            }
            catch (Exception e) { Console.Error.WriteLine("pyxpo: snapshot failed: " + e.Message); }
            finally { busy = false; }
        };
        timer.Start();
    }
}
