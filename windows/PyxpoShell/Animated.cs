using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json.Nodes;
using Microsoft.UI.Xaml.Media;

namespace Pyxpo;

/// Native animation driver. C# port of pyxpo/animated/engine.py (the reference, same as Animated.swift); numbers
/// are pinned by tests/data/anim_golden.json. CompositionTarget.Rendering evaluates every running animation per
/// frame on the UI thread and hands the changed value ids to `onFrame`, which writes view properties directly.
/// No Python per frame.
sealed class Animated
{
    readonly Action<string, int, JsonObject> emit;
    readonly Action<HashSet<int>> onFrame;

    public Animated(Action<string, int, JsonObject> emit, Action<HashSet<int>> onFrame)
    {
        this.emit = emit;
        this.onFrame = onFrame;
    }

    // -- easing --------------------------------------------------------------------------------------
    static Func<double, double> Bezier(double x1, double y1, double x2, double y2)
    {
        static double Coord(double a, double b, double t)
        {
            var u = 1 - t;
            return 3 * u * u * t * a + 3 * u * t * t * b + t * t * t;
        }
        return x =>
        {
            if (x <= 0) return 0;
            if (x >= 1) return 1;
            double lo = 0, hi = 1, t = x;
            for (var k = 0; k < 40; k++)
            {
                var cx = Coord(x1, x2, t);
                if (Math.Abs(cx - x) < 1e-7) break;
                if (cx < x) lo = t; else hi = t;
                t = (lo + hi) / 2;
            }
            return Coord(y1, y2, t);
        };
    }

    static double Bounce(double t)
    {
        if (t < 1 / 2.75) return 7.5625 * t * t;
        if (t < 2 / 2.75) { t -= 1.5 / 2.75; return 7.5625 * t * t + 0.75; }
        if (t < 2.5 / 2.75) { t -= 2.25 / 2.75; return 7.5625 * t * t + 0.9375; }
        t -= 2.625 / 2.75;
        return 7.5625 * t * t + 0.984375;
    }

    public static Func<double, double> Easing(JsonObject? spec)
    {
        if (spec == null) return Easing(new JsonObject { ["e"] = "in_out", ["f"] = new JsonObject { ["e"] = "quad" } });
        switch (Js.Str(spec["e"]) ?? "")
        {
            case "linear": return x => x;
            case "ease": return Bezier(0.42, 0, 1, 1);
            case "quad": return x => x * x;
            case "cubic": return x => x * x * x;
            case "poly": { var n = Js.D(spec["n"], 4); return x => Math.Pow(x, n); }
            case "sin": return x => 1 - Math.Cos(x * Math.PI / 2);
            case "circle": return x => 1 - Math.Sqrt(Math.Max(0, 1 - x * x));
            case "exp": return x => Math.Pow(2, 10 * (x - 1));
            case "elastic": { var p = Js.D(spec["b"], 1) * Math.PI; return x => 1 - Math.Pow(Math.Cos(x * Math.PI / 2), 3) * Math.Cos(x * p); }
            case "back": { var s = Js.D(spec["s"], 1.70158); return x => x * x * (x * (s + 1) - s); }
            case "bounce": return Bounce;
            case "bezier": { var p = Js.Nums(spec["p"]); return Bezier(p[0], p[1], p[2], p[3]); }
            case "in": return Easing(Js.Obj(spec["f"]));
            case "out": { var f = Easing(Js.Obj(spec["f"])); return x => 1 - f(1 - x); }
            case "in_out":
            {
                var f = Easing(Js.Obj(spec["f"]));
                return x => x < 0.5 ? f(2 * x) / 2 : 1 - f(2 * (1 - x)) / 2;
            }
            default: return x => x;
        }
    }

    // -- node graph ----------------------------------------------------------------------------------
    abstract record N;
    sealed record ValueN : N;
    sealed record InterpN(int Src, List<double> Inp, List<double> Out, string Left, string Right, bool Color,
                          Func<double, double>? Ease) : N;
    sealed record BinN(bool Add, int A, int B) : N;

    sealed class Anim
    {
        public int Id;
        public Run Run = null!;
        public HashSet<int> Nodes = null!;
    }

    readonly Dictionary<int, N> nodes = new();
    readonly Dictionary<int, double> values = new();
    readonly Dictionary<int, double> vel = new();
    readonly Dictionary<int, (double t, double v)> prev = new();
    readonly HashSet<int> listen = new();
    readonly Dictionary<int, double> lastSent = new();
    readonly List<Anim> anims = new();
    bool running;
    readonly Stopwatch clock = Stopwatch.StartNew();

    public void ANode(int id, JsonObject o)
    {
        switch (Js.Str(o["t"]) ?? "")
        {
            case "value": nodes[id] = new ValueN(); values[id] = Js.D(o["v"]); break;
            case "interp":
            {
                var ex = (o["ex"] as JsonArray)?.Select(x => Js.Str(x) ?? "extend").ToList() ?? new List<string> { "extend", "extend" };
                nodes[id] = new InterpN(Js.I(o["src"]), Js.Nums(o["in"]), Js.Nums(o["out"]), ex[0], ex[1],
                                        Js.B(o["color"]), Js.Obj(o["easing"]) is JsonObject e ? Easing(e) : null);
                break;
            }
            case "add": nodes[id] = new BinN(true, Js.I(o["a"]), Js.I(o["b"])); break;
            case "mul": nodes[id] = new BinN(false, Js.I(o["a"]), Js.I(o["b"])); break;
        }
    }

    public void ANodeDel(int id)
    {
        StopTouching(new HashSet<int> { id }, false);
        nodes.Remove(id); values.Remove(id); vel.Remove(id); prev.Remove(id); lastSent.Remove(id); listen.Remove(id);
    }

    public void AListen(int id, bool on)
    {
        if (on) { listen.Add(id); lastSent[id] = values.GetValueOrDefault(id); }
        else listen.Remove(id);
    }

    public void AStop(int aid)
    {
        var k = anims.FindIndex(a => a.Id == aid);
        if (k >= 0)
        {
            var r = anims[k];
            anims.RemoveAt(k);
            EmitEnd(aid, false, r.Nodes);
        }
    }

    public void ASet(JsonObject vals)
    {
        var ids = new HashSet<int>();
        foreach (var kv in vals) if (int.TryParse(kv.Key, out var id)) ids.Add(id);
        StopTouching(ids, false);
        foreach (var id in ids) { values[id] = Js.D(vals[id.ToString()]); vel[id] = 0; prev.Remove(id); }
        ValueEvents(ids);
        onFrame(ids);
    }

    public void Animate(int aid, JsonObject spec)
    {
        var ns = NodesOf(spec);
        StopTouching(ns, false);
        anims.Add(new Anim { Id = aid, Run = Build(spec), Nodes = ns });
        Start();
    }

    public double Resolve(int id)
    {
        if (!nodes.TryGetValue(id, out var n)) return 0;
        return n switch
        {
            ValueN => values.GetValueOrDefault(id),
            InterpN i => Interpolate(Resolve(i.Src), i),
            BinN b => b.Add ? Resolve(b.A) + Resolve(b.B) : Resolve(b.A) * Resolve(b.B),
            _ => 0,
        };
    }

    /// Value-node ids a node depends on (itself if it is a value).
    public void Deps(int id, HashSet<int> out_)
    {
        if (!nodes.TryGetValue(id, out var n)) return;
        switch (n)
        {
            case ValueN: out_.Add(id); break;
            case InterpN i: Deps(i.Src, out_); break;
            case BinN b: Deps(b.A, out_); Deps(b.B, out_); break;
        }
    }

    static double LerpColor(uint a, uint b, double f)
    {
        uint out_ = 0;
        foreach (var shift in new[] { 24, 16, 8, 0 })
        {
            double ca = (a >> shift) & 255, cb = (b >> shift) & 255;
            var v = Math.Min(255, Math.Max(0, Math.Round(ca + (cb - ca) * f, MidpointRounding.ToEven)));
            out_ |= (uint)v << shift;
        }
        return out_;
    }

    static double Interpolate(double x, InterpN n)
    {
        var inp = n.Inp;
        var outv = n.Out;
        var len = inp.Count;
        int i;
        if (x < inp[0])
        {
            if (n.Left == "clamp") return outv[0];
            if (n.Left == "identity") return x;
            i = 0;
        }
        else if (x > inp[len - 1])
        {
            if (n.Right == "clamp") return outv[len - 1];
            if (n.Right == "identity") return x;
            i = len - 2;
        }
        else
        {
            i = 0;
            while (i < len - 2 && x > inp[i + 1]) i++;
        }
        double a = inp[i], b = inp[i + 1];
        var f = b == a ? 0 : (x - a) / (b - a);
        if (n.Ease != null && f >= 0 && f <= 1) f = n.Ease(f);
        if (n.Color) return LerpColor((uint)outv[i], (uint)outv[i + 1], Math.Min(1, Math.Max(0, f)));
        return outv[i] + (outv[i + 1] - outv[i]) * f;
    }

    /// Displacement and velocity (per second) of a damped spring dt seconds after release.
    static (double, double) SpringAt(double dt, double x0, double v0, double k, double c, double m)
    {
        var w0 = Math.Sqrt(k / m);
        var z = c / (2 * Math.Sqrt(k * m));
        if (Math.Abs(z - 1) < 1e-9)
        {
            double e = Math.Exp(-w0 * dt), b = v0 + w0 * x0;
            return (e * (x0 + b * dt), e * (v0 - w0 * b * dt));
        }
        if (z < 1)
        {
            double wd = w0 * Math.Sqrt(1 - z * z), e = Math.Exp(-z * w0 * dt), b = (v0 + z * w0 * x0) / wd;
            double cs = Math.Cos(wd * dt), sn = Math.Sin(wd * dt);
            return (e * (x0 * cs + b * sn), e * ((b * wd - z * w0 * x0) * cs - (x0 * wd + z * w0 * b) * sn));
        }
        var s = w0 * Math.Sqrt(z * z - 1);
        double r1 = -z * w0 + s, r2 = -z * w0 - s;
        double c2 = (v0 - r1 * x0) / (r2 - r1), c1 = x0 - c2;
        double e1 = Math.Exp(r1 * dt), e2 = Math.Exp(r2 * dt);
        return (c1 * e1 + c2 * e2, c1 * r1 * e1 + c2 * r2 * e2);
    }

    // -- running animations --------------------------------------------------------------------------
    double Get(int n) => values.GetValueOrDefault(n);

    void SetV(int n, double v, double t)
    {
        if (prev.TryGetValue(n, out var p) && t > p.t) vel[n] = (v - p.v) / ((t - p.t) / 1000);
        prev[n] = (t, v);
        values[n] = v;
    }

    class Run { public virtual bool Update(double t) => true; }

    sealed class Timing : Run
    {
        readonly Animated a; readonly JsonObject s; readonly int node; readonly Func<double, double> ease;
        double t0 = double.NaN, from;
        public Timing(Animated a, JsonObject s) { this.a = a; this.s = s; node = Js.I(s["node"]); ease = Easing(Js.Obj(s["easing"])); }
        public override bool Update(double t)
        {
            if (double.IsNaN(t0)) { t0 = t; from = a.Get(node); a.prev[node] = (t, from); }
            double ms = Js.D(s["ms"]), to = Js.D(s["to"]);
            var p = ms <= 0 ? 1 : Math.Min(1, (t - t0) / ms);
            a.SetV(node, p >= 1 ? to : from + (to - from) * ease(p), t);
            return p >= 1;
        }
    }

    sealed class Spring : Run
    {
        readonly Animated a; readonly JsonObject s; readonly int node;
        double t0 = double.NaN, x0, v0;
        public Spring(Animated a, JsonObject s) { this.a = a; this.s = s; node = Js.I(s["node"]); }
        public override bool Update(double t)
        {
            var to = Js.D(s["to"]);
            if (double.IsNaN(t0))
            {
                t0 = t;
                var cur = a.Get(node);
                x0 = cur - to;
                v0 = Js.Num(s["v0"]) ?? a.vel.GetValueOrDefault(node);
                a.prev[node] = (t, cur);
            }
            var (x, v) = SpringAt((t - t0) / 1000, x0, v0, Js.D(s["k"]), Js.D(s["c"]), Js.D(s["m"]));
            var done = Math.Abs(x) <= Js.D(s["rest_d"], 0.001) && Math.Abs(v) <= Js.D(s["rest_v"], 0.001);
            if (Js.B(s["clamp"]) && t > t0 && x0 != 0 && x * x0 <= 0) done = true;
            if (x0 == 0 && v0 == 0) done = true;
            a.SetV(node, done ? to : to + x, t);
            if (done) a.vel[node] = 0;
            return done;
        }
    }

    sealed class Decay : Run
    {
        readonly Animated a; readonly JsonObject s; readonly int node;
        double t0 = double.NaN, from, v0;
        public Decay(Animated a, JsonObject s) { this.a = a; this.s = s; node = Js.I(s["node"]); }
        public override bool Update(double t)
        {
            var dec = Js.D(s["decel"], 0.998);
            if (double.IsNaN(t0))
            {
                t0 = t; from = a.Get(node);
                v0 = Js.Num(s["v0"]) ?? a.vel.GetValueOrDefault(node) / 1000;
                a.prev[node] = (t, from);
            }
            double k = 1 - dec, dt = t - t0;
            a.SetV(node, from + v0 / k * (1 - Math.Exp(-k * dt)), t);
            var done = Math.Abs(v0 * Math.Exp(-k * dt)) * 16.67 < 0.1;
            if (done) a.vel[node] = 0;
            return done;
        }
    }

    sealed class DelayRun : Run
    {
        readonly double ms;
        double t0 = double.NaN;
        public DelayRun(double ms) { this.ms = ms; }
        public override bool Update(double t) { if (double.IsNaN(t0)) t0 = t; return t - t0 >= ms; }
    }

    sealed class Seq : Run
    {
        readonly List<Run> items;
        int i;
        public Seq(Animated a, JsonObject s) { items = Items(a, s); }
        public override bool Update(double t)
        {
            while (i < items.Count) { if (!items[i].Update(t)) return false; i++; }
            return true;
        }
    }

    sealed class Par : Run
    {
        readonly List<Run> items;
        readonly bool[] done;
        public Par(Animated a, JsonObject s) { items = Items(a, s); done = new bool[items.Count]; }
        public override bool Update(double t)
        {
            for (var k = 0; k < items.Count; k++) if (!done[k]) done[k] = items[k].Update(t);
            return done.All(x => x);
        }
    }

    static List<Run> Items(Animated a, JsonObject s) =>
        (s["items"] as JsonArray)?.OfType<JsonObject>().Select(a.Build).ToList() ?? new List<Run>();

    sealed class Loop : Run
    {
        readonly Animated a; readonly JsonObject s; readonly int n;
        int i;
        Run? cur;
        Dictionary<int, double>? snap;
        public Loop(Animated a, JsonObject s) { this.a = a; this.s = s; n = Js.Num(s["n"]) is double d ? (int)d : -1; }
        public override bool Update(double t)
        {
            for (var k = 0; k < 2; k++)
            {
                if (cur == null)
                {
                    if (n >= 0 && i >= n) return true;
                    var item = Js.Obj(s["item"]) ?? new JsonObject();
                    if (snap == null)
                    {
                        snap = new Dictionary<int, double>();
                        foreach (var x in a.NodesOf(item)) snap[x] = a.Get(x);
                    }
                    else if (Js.B(s["reset"], true))
                    {
                        foreach (var kv in snap) a.SetV(kv.Key, kv.Value, t);
                    }
                    cur = a.Build(item); i++;
                }
                if (!cur.Update(t)) return false;
                cur = null;
            }
            return n >= 0 && i >= n;
        }
    }

    Run Build(JsonObject s) => (Js.Str(s["t"]) ?? "") switch
    {
        "timing" => new Timing(this, s),
        "spring" => new Spring(this, s),
        "decay" => new Decay(this, s),
        "delay" => new DelayRun(Js.D(s["ms"])),
        "seq" => new Seq(this, s),
        "par" => new Par(this, s),
        "loop" => new Loop(this, s),
        _ => new Run(),
    };

    HashSet<int> NodesOf(JsonObject s)
    {
        if (Js.Num(s["node"]) is double n) return new HashSet<int> { (int)n };
        var out_ = new HashSet<int>();
        switch (Js.Str(s["t"]) ?? "")
        {
            case "seq":
            case "par":
                if (s["items"] is JsonArray items) foreach (var x in items.OfType<JsonObject>()) out_.UnionWith(NodesOf(x));
                break;
            case "loop": out_.UnionWith(NodesOf(Js.Obj(s["item"]) ?? new JsonObject())); break;
        }
        return out_;
    }

    // -- events + frame loop -------------------------------------------------------------------------
    void EmitEnd(int aid, bool finished, HashSet<int> ns)
    {
        var vals = new JsonObject();
        foreach (var n in ns) vals[n.ToString()] = Get(n);
        emit("anim_end", aid, new JsonObject { ["finished"] = finished, ["values"] = vals });
    }

    void StopTouching(HashSet<int> ns, bool finished)
    {
        var hit = anims.Where(a => a.Nodes.Overlaps(ns)).ToList();
        anims.RemoveAll(a => hit.Contains(a));
        foreach (var h in hit) EmitEnd(h.Id, finished, h.Nodes);
    }

    void ValueEvents(HashSet<int> touched)
    {
        var ch = new JsonObject();
        foreach (var n in touched)
        {
            if (!listen.Contains(n)) continue;
            var v = Get(n);
            if (!lastSent.TryGetValue(n, out var last) || last != v) { lastSent[n] = v; ch[n.ToString()] = v; }
        }
        if (ch.Count > 0) emit("anim_value", 0, ch);
    }

    void Start()
    {
        if (running) return;
        running = true;
        CompositionTarget.Rendering += OnRendering;
    }

    void Stop()
    {
        if (!running) return;
        running = false;
        CompositionTarget.Rendering -= OnRendering;
    }

    void OnRendering(object? sender, object e) => Tick(clock.Elapsed.TotalMilliseconds);

    public void Tick(double now)
    {
        var touched = new HashSet<int>();
        var ended = new List<int>();
        foreach (var a in anims.ToList())
        {
            touched.UnionWith(a.Nodes);
            if (a.Run.Update(now)) ended.Add(a.Id);
        }
        onFrame(touched);
        ValueEvents(touched);
        foreach (var aid in ended)
        {
            var k = anims.FindIndex(a => a.Id == aid);
            if (k >= 0)
            {
                var r = anims[k];
                anims.RemoveAt(k);
                EmitEnd(aid, true, r.Nodes);
            }
        }
        if (anims.Count == 0) Stop();
    }

    public void Clear() { anims.Clear(); Stop(); }
}
