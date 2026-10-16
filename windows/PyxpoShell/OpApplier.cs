using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Foundation;
using Windows.System;
using Windows.UI.Text;
using Style = System.Collections.Generic.Dictionary<string, System.Text.Json.Nodes.JsonNode?>;

namespace Pyxpo;

/// TextInput: a TextBox, swapped for a PasswordBox while `secure` is on (a TextBox cannot mask its text).
sealed class TextField : Grid
{
    public readonly TextBox Box = new();
    public readonly PasswordBox Pwd = new() { Visibility = Visibility.Collapsed };
    public bool Secure { get; private set; }
    public bool SelectOnFocus;

    public TextField()
    {
        foreach (var c in new Control[] { Box, Pwd })
        {
            c.Padding = new Thickness(0);
            c.BorderThickness = new Thickness(0);
            c.MinHeight = 0;
            c.MinWidth = 0;
            c.Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent);
            c.VerticalAlignment = VerticalAlignment.Center;
            c.IsTextScaleFactorEnabled = false;
            // The control's own chrome (focus underline, hover fill) stays off: the app draws the field's box.
            foreach (var k in new[] { "TextControlBackground", "TextControlBackgroundPointerOver", "TextControlBackgroundFocused",
                                      "TextControlBackgroundDisabled", "TextControlBorderBrush", "TextControlBorderBrushPointerOver",
                                      "TextControlBorderBrushFocused", "TextControlBorderBrushDisabled" })
                c.Resources[k] = new SolidColorBrush(Microsoft.UI.Colors.Transparent);
            c.Resources["TextControlBorderThemeThicknessFocused"] = new Thickness(0);
            c.Resources["TextControlThemePadding"] = new Thickness(0);
            c.Resources["TextControlThemeMinHeight"] = 0.0;
            c.Resources["TextControlThemeMinWidth"] = 0.0;
            Children.Add(c);
        }
        Box.TextWrapping = TextWrapping.NoWrap;
        Box.GotFocus += (_, _) => { if (SelectOnFocus) Box.SelectAll(); };
        Pwd.GotFocus += (_, _) => { if (SelectOnFocus) Pwd.SelectAll(); };
    }

    public Control Active => Secure ? Pwd : Box;

    public string Text
    {
        get => Secure ? Pwd.Password : Box.Text;
        set { if (Box.Text != value) Box.Text = value; if (Pwd.Password != value) Pwd.Password = value; }
    }

    public void SetSecure(bool on)
    {
        if (on == Secure) return;
        var t = Text;
        Secure = on;
        Text = t;
        Box.Visibility = on ? Visibility.Collapsed : Visibility.Visible;
        Pwd.Visibility = on ? Visibility.Visible : Visibility.Collapsed;
    }
}

/// Applies JSON op batches (wire v2) on the UI thread. C# port of OpApplier.swift: same op contract, same style
/// rules. Layout is done by the shared C engine (pyxpo_native.dll); this class only places frames, measures leaves
/// and paints boxes with XAML elements.
sealed class OpApplier
{
    const int ContentBit = 0x40000000; // id bit for a ScrollView's synthetic content node
    static readonly HashSet<string> Leaves = new() { "Text", "Button", "TextInput", "Image" };
    static readonly HashSet<string> Controls = new() { "NativeSwitch", "NativeSlider", "NativeSpinner" };
    static readonly HashSet<string> TransformKeys = new() { "opacity", "rotate", "scale", "scale_x", "scale_y", "translate_x", "translate_y" };

    readonly Dictionary<int, Node> views = new();
    readonly Dictionary<int, string> types = new();
    readonly Dictionary<int, Style> styles = new();
    readonly Dictionary<int, Thickness> pads = new();
    readonly Dictionary<int, string> texts = new();
    readonly Dictionary<int, Style> ctl = new();
    readonly Dictionary<int, List<JsonObject>> spans = new();
    readonly Dictionary<int, NavHost> navs = new();
    readonly Dictionary<int, ScrollHost> scrolls = new();
    readonly Dictionary<int, Size> imgSize = new();
    readonly Dictionary<int, string> imgReq = new();
    readonly Dictionary<int, Style> a11y = new();
    readonly HashSet<int> layoutListeners = new();
    readonly Dictionary<int, HashSet<string>> touchKeys = new();
    readonly Dictionary<int, Dictionary<string, int>> binds = new();
    readonly Dictionary<int, HashSet<int>> depCache = new();
    readonly Dictionary<string, int> propIds = new();
    static readonly Dictionary<string, FontFamily> families = new();
    readonly HashSet<int> sliding = new();
    readonly HashSet<int> settingControl = new();
    readonly HashSet<int> exiting = new();

    readonly IntPtr tree;
    readonly Native.MeasureFn measureFn; // kept alive: the engine holds a pointer to it
    readonly Animated anim;
    readonly Action<string> sendEvent;
    readonly Node root;
    readonly Control focusSink = new ContentControl { Width = 0, Height = 0, IsTabStop = true, Opacity = 0 };
    readonly SemaphoreSlim alertGate = new(1, 1);
    Size rootSize;
    string? sentEnv;
    bool batching;

    /// Text scale from Settings > Accessibility > Text size (1.0 to 2.25).
    public static double FontScale = 1;
    public bool BackEnabled;
    public Func<JsonObject>? EnvSource;

    public FrameworkElement View => root.Frame;

    public OpApplier(Action<string> sendEvent)
    {
        this.sendEvent = sendEvent;
        unsafe { measureFn = MeasureCb; }
        tree = Native.px_tree_new(measureFn, IntPtr.Zero);
        anim = new Animated((n, id, pl) => Event(n, id, pl), OnAnimFrame);
        // Root id 1 is implicit in the ops protocol: it is never created by the reconciler.
        root = new Node(1, "Root", null, true);
        root.Frame.Children.Add(focusSink);
        views[1] = root;
        types[1] = "Root";
        root.Frame.SizeChanged += (_, e) => OnRootSize(e.NewSize);
    }

    // -- ops -----------------------------------------------------------------------------------------
    public void Apply(string batch)
    {
        JsonArray? ops;
        try { ops = JsonNode.Parse(batch) as JsonArray; }
        catch (Exception e) { Debug.WriteLine("pyxpo: bad batch " + e.Message); return; }
        if (ops == null) return;
        batching = true;
        foreach (var n in ops)
        {
            if (n is not JsonObject o || Js.Str(o["op"]) is not string op) continue;
            int id = Js.I(o["id"]);
            try
            {
                switch (op)
                {
                    case "create": Create(id, Js.Str(o["type"]) ?? "View", Js.Obj(o["props"]) ?? new JsonObject()); break;
                    case "update": Update(id, Js.Obj(o["props"]) ?? new JsonObject(), Strs(o["removed"])); break;
                    case "insert": Insert(Js.I(o["parent"]), id, Js.I(o["index"])); break;
                    case "remove": Remove(Js.I(o["parent"]), id); break;
                    case "delete": Delete(id); break;
                    case "anode": anim.ANode(id, Js.Obj(o["node"]) ?? new JsonObject()); depCache.Clear(); break;
                    case "anode_del": anim.ANodeDel(id); depCache.Clear(); break;
                    case "alisten": anim.AListen(id, Js.B(o["on"])); break;
                    case "animate": anim.Animate(id, Js.Obj(o["anim"]) ?? new JsonObject()); break;
                    case "astop": anim.AStop(id); break;
                    case "aset": anim.ASet(Js.Obj(o["vals"]) ?? new JsonObject()); break;
                    case "call":
                        Call(id, Js.Str(o["module"]) ?? "", Js.Str(o["method"]) ?? "", Js.Arr(o["args"]) ?? new JsonArray(),
                             Js.B(o["reply"]));
                        break;
                }
            }
            catch (Exception e) { Console.Error.WriteLine($"pyxpo: op {op} {id} failed: {e}"); }
        }
        batching = false;
        Flush();
    }

    static List<string> Strs(JsonNode? n)
    {
        var l = new List<string>();
        if (n is JsonArray a) foreach (var x in a) if (Js.Str(x) is string s) l.Add(s);
        return l;
    }

    public void DevReload() => Event("dev_reload", 0);

    /// Escape / mouse back button. Python only listens after Back.set_enabled(true) (BackHandler).
    public bool HardwareBack()
    {
        if (!BackEnabled) return false;
        Event("hardware_back", 0);
        return true;
    }

    public void AppState(string state) => Event("app_state", 0, new JsonObject { ["state"] = state });

    void Event(string name, int id, JsonObject? payload = null)
    {
        var o = new JsonObject { ["event"] = name, ["id"] = id, ["payload"] = payload ?? new JsonObject() };
        sendEvent(o.ToJsonString());
    }

    static JsonObject Value(JsonNode? v) => new() { ["value"] = v };

    static JsonObject Rect4(double x, double y, double w, double h) =>
        new() { ["x"] = x, ["y"] = y, ["width"] = w, ["height"] = h };

    void Create(int id, string type, JsonObject props)
    {
        FrameworkElement? content = null;
        bool container = false;
        switch (type)
        {
            case "Text":
                content = new TextBlock { TextWrapping = TextWrapping.Wrap, IsTextScaleFactorEnabled = false };
                break;
            case "Button":
            {
                var b = new Button
                {
                    HorizontalAlignment = HorizontalAlignment.Stretch, VerticalAlignment = VerticalAlignment.Stretch,
                    HorizontalContentAlignment = HorizontalAlignment.Center, IsTextScaleFactorEnabled = false,
                    MinWidth = 0, MinHeight = 0,
                };
                b.Click += (_, _) => Event("press", id);
                content = b;
                break;
            }
            case "TextInput":
            {
                var t = new TextField();
                t.Box.TextChanged += (_, _) => { if (!t.Secure) Event("change_text", id, Value(t.Box.Text)); };
                t.Pwd.PasswordChanged += (_, _) => { if (t.Secure) Event("change_text", id, Value(t.Pwd.Password)); };
                foreach (var c in new Control[] { t.Box, t.Pwd })
                {
                    c.GotFocus += (_, _) => Event("focus", id);
                    c.LostFocus += (_, _) => Event("blur", id);
                    c.KeyDown += (_, e) =>
                    {
                        if (e.Key != VirtualKey.Enter) return;
                        e.Handled = true;
                        Event("submit", id, Value(t.Text));
                    };
                }
                content = t;
                break;
            }
            case "Image":
                content = new Image { Stretch = Stretch.UniformToFill };
                break;
            case "NativeSwitch":
            {
                var sw = new ToggleSwitch { OnContent = null, OffContent = null, MinWidth = 0 };
                sw.Resources["ToggleSwitchThemeMinWidth"] = 0.0;
                sw.Resources["ToggleSwitchPreContentMargin"] = 0.0;
                sw.Resources["ToggleSwitchPostContentMargin"] = 0.0;
                sw.Toggled += (_, _) => { if (!settingControl.Contains(id)) Event("value_change", id, Value(sw.IsOn)); };
                content = sw;
                break;
            }
            case "NativeSlider":
            {
                var sl = new Slider { Height = 32, VerticalAlignment = VerticalAlignment.Center, IsThumbToolTipEnabled = false };
                sl.ValueChanged += (_, _) => { if (!settingControl.Contains(id)) Event("value_change", id, Value(SliderValue(id, sl))); };
                sl.AddHandler(UIElement.PointerPressedEvent, new PointerEventHandler((_, _) => sliding.Add(id)), true);
                void End(object _, PointerRoutedEventArgs __)
                {
                    if (!sliding.Remove(id)) return;
                    Event("sliding_complete", id, Value(SliderValue(id, sl)));
                }
                sl.AddHandler(UIElement.PointerReleasedEvent, new PointerEventHandler(End), true);
                sl.AddHandler(UIElement.PointerCaptureLostEvent, new PointerEventHandler(End), true);
                content = sl;
                break;
            }
            case "NativeSpinner":
                content = new ProgressRing
                {
                    IsActive = true, Width = 20, Height = 20, IsIndeterminate = true,
                    HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center,
                };
                break;
            case "Path":
                content = new PathView();
                break;
            case "ScrollView":
            {
                var sh = new ScrollHost();
                scrolls[id] = sh;
                content = sh.View;
                break;
            }
            default:
                // NavStack, Modal, View, Pressable and any module view type (no native module views on Windows).
                container = true;
                break;
        }
        var node = new Node(id, type, content, container);
        node.Frame.Tag = node;
        views[id] = node;
        types[id] = type;
        if (type == "NavStack") navs[id] = new NavHost(node);
        Native.px_node_create(tree, id);
        if (Leaves.Contains(type) || Controls.Contains(type)) Native.px_node_set_measured(tree, id, 1);
        if (type == "ScrollView")
        {
            int c = id | ContentBit;
            Native.px_node_create(tree, c);
            Native.px_node_insert(tree, id, c, 0);
            Native.px_node_set_num(tree, c, Prop("flex_shrink"), 0);
            Native.px_node_set_num(tree, id, Prop("scroll"), 1);
            bool horiz = Js.B(props["horizontal"]);
            if (horiz)
            {
                Native.px_node_set_str(tree, id, Prop("flex_direction"), "row");
                Native.px_node_set_str(tree, c, Prop("flex_direction"), "row");
            }
            var sh = scrolls[id];
            sh.SetHorizontal(horiz);
            sh.OnEvent = (n, p) =>
            {
                var o = new JsonObject();
                foreach (var (k, v) in p) o[k] = v is Dictionary<string, object> d ? ToJson(d) : JsonValue.Create(Convert.ToDouble(v));
                Event(n, id, o);
            };
            sh.OnAE = vals =>
            {
                var j = new JsonObject();
                foreach (var (k, x) in vals) j[k.ToString()] = x;
                anim.ASet(j);
            };
        }
        if (type == "Modal") Canvas.SetZIndex(node.Frame, 10000);
        Update(id, props, new List<string>());
    }

    static JsonObject ToJson(Dictionary<string, object> d)
    {
        var o = new JsonObject();
        foreach (var (k, v) in d) o[k] = JsonValue.Create(Convert.ToDouble(v));
        return o;
    }

    void Update(int id, JsonObject props, List<string> removed)
    {
        if (!views.TryGetValue(id, out var v)) return;
        bool a11yDirty = removed.Any(k => k.StartsWith("accessib"));
        if (removed.Contains("style")) ApplyStyle(id, v, new JsonObject());
        if (removed.Contains("spans"))
        {
            spans.Remove(id);
            if (v.Content is TextBlock tb) RenderText(id, tb, StyleOf(id));
            Native.px_node_mark_dirty(tree, id);
        }
        foreach (var (k, val) in props)
        {
            switch (k)
            {
                case "text":
                {
                    var s = Js.Str(val) ?? "";
                    texts[id] = s;
                    if (v.Content is Button b) b.Content = s;
                    else if (v.Content is TextBlock tb) RenderText(id, tb, StyleOf(id));
                    Native.px_node_mark_dirty(tree, id);
                    break;
                }
                case "spans":
                    spans[id] = (val as JsonArray)?.OfType<JsonObject>().ToList() ?? new List<JsonObject>();
                    if (v.Content is TextBlock t2) RenderText(id, t2, StyleOf(id));
                    Native.px_node_mark_dirty(tree, id);
                    break;
                case "value":
                    if (v.Content is TextField tf)
                    {
                        var s = Js.Str(val) ?? "";
                        if (tf.Text != s) { tf.Text = s; Native.px_node_mark_dirty(tree, id); }
                    }
                    break;
                case "placeholder":
                    if (v.Content is TextField tp) { tp.Box.PlaceholderText = Js.Str(val) ?? ""; tp.Pwd.PlaceholderText = Js.Str(val) ?? ""; }
                    break;
                case "placeholder_color":
                    if (v.Content is TextField tc && Js.Color(val) is uint pc)
                    {
                        var br = new SolidColorBrush(Colors.Of(pc));
                        tc.Box.PlaceholderForeground = br;
                        tc.Pwd.Resources["TextControlPlaceholderForeground"] = br;
                    }
                    break;
                case "keyboard_type": case "secure": case "auto_capitalize": case "auto_correct": case "return_key":
                case "max_length": case "editable": case "auto_focus": case "select_on_focus":
                    if (v.Content is TextField ti) ApplyInput(ti, k, val);
                    break;
                case "style": ApplyStyle(id, v, Js.Obj(val) ?? new JsonObject()); break;
                case "on_press": case "on_press_in": case "on_press_out": case "on_long_press":
                {
                    Keys(id).Add(k);
                    var t = TouchOf(v);
                    if (t != null && t.OnTouch == null)
                    {
                        t.OnTouch = (name, p) => Event(name, id, p is Point q ? new JsonObject { ["x"] = q.X, ["y"] = q.Y } : null);
                        v.SetHittable(true);
                    }
                    break;
                }
                case "on_touch_start": case "on_touch_move": case "on_touch_end":
                {
                    Keys(id).Add(k);
                    var t = TouchOf(v);
                    if (t != null && t.OnRaw == null)
                    {
                        t.OnRaw = (name, p, w) => Event(name, id, Value(new JsonObject
                        {
                            ["x"] = p.X, ["y"] = p.Y, ["page_x"] = w.X, ["page_y"] = w.Y,
                        }));
                        v.SetHittable(true);
                    }
                    break;
                }
                case "test_id":
                    // testID, as in React Native: UI Automation's AutomationId (WinAppDriver, Appium).
                    AutomationProperties.SetAutomationId(v.Frame, Js.Str(val) ?? "");
                    break;
                case "on_layout": layoutListeners.Add(id); break;
                case "source": case "resize_mode": case "tint_color":
                    if (v.Content is Image img) ApplyImage(id, img, props, removed);
                    break;
                default:
                    if (k.StartsWith("accessib")) a11yDirty = true;
                    else if (scrolls.TryGetValue(id, out var sh)) ScrollProp(sh, k, val);
                    break;
            }
        }
        if (Controls.Contains(types.GetValueOrDefault(id) ?? "")) ApplyControl(id, v, props, removed);
        foreach (var k in removed)
        {
            if (k == "on_layout") layoutListeners.Remove(id);
            if (k == "test_id") v.Frame.ClearValue(AutomationProperties.AutomationIdProperty);
            if (k.StartsWith("on_touch_") || k.StartsWith("on_press") || k == "on_long_press")
            {
                // Handlers removed (e.g. a disabled Slider): stop swallowing touches.
                var left = Keys(id);
                left.Remove(k);
                if (v.Touch != null)
                {
                    if (!left.Any(x => x.StartsWith("on_touch_"))) v.Touch.OnRaw = null;
                    if (!left.Any(x => x.StartsWith("on_press") || x == "on_long_press")) v.Touch.OnTouch = null;
                    v.SetHittable(v.Touch.Active);
                }
            }
            if (scrolls.TryGetValue(id, out var sh)) ScrollProp(sh, k, null);
            if (v.Content is Image img && (k == "source" || k == "resize_mode" || k == "tint_color") && !props.ContainsKey(k))
                ApplyImage(id, img, new JsonObject(), removed);
        }
        if (v.Content is PathView pv)
        {
            if (props["path"] is JsonArray cmds) pv.SetCommands(cmds.Select(c => Js.Nums(c).ToArray()).ToList());
            else if (removed.Contains("path")) pv.SetCommands(new List<double[]>());
            if (Js.Num(props["viewbox"]) is double vb) pv.SetBox(vb);
            if (Js.Num(props["stroke_width"]) is double sw) { pv.StrokeWidth = sw; pv.Rebuild(); }
            if (props.ContainsKey("stroke") || props.ContainsKey("fill") || removed.Contains("stroke") || removed.Contains("fill"))
            {
                var c = Ctl(id);
                foreach (var key in new[] { "stroke", "fill" })
                {
                    if (props.ContainsKey(key)) c[key] = props[key]?.DeepClone();
                    else if (removed.Contains(key)) c.Remove(key);
                }
                pv.SetColors(Js.Color(c.GetValueOrDefault("stroke")), Js.Color(c.GetValueOrDefault("fill")));
            }
        }
        if (a11yDirty)
        {
            var a = a11y.TryGetValue(id, out var cur) ? cur : new Style();
            foreach (var k in removed) if (k.StartsWith("accessib")) a.Remove(k);
            foreach (var (k, val) in props) if (k.StartsWith("accessib")) a[k] = val?.DeepClone();
            a11y[id] = a;
            ApplyA11y(v, a);
        }
        if (!batching) Flush();
    }

    HashSet<string> Keys(int id)
    {
        if (!touchKeys.TryGetValue(id, out var s)) touchKeys[id] = s = new HashSet<string>();
        return s;
    }

    Style Ctl(int id)
    {
        if (!ctl.TryGetValue(id, out var c)) ctl[id] = c = new Style();
        return c;
    }

    Style StyleOf(int id) => styles.TryGetValue(id, out var s) ? s : new Style();

    /// Press / touch handlers live on container nodes, as PxGroup on iOS.
    Touch? TouchOf(Node v)
    {
        if (v.Kids == null) return null;
        return v.Touch ??= new Touch(v, root.Frame);
    }

    static void ScrollProp(ScrollHost s, string k, JsonNode? val)
    {
        switch (k)
        {
            case "scroll_enabled": s.Enabled = Js.B(val, true); s.Apply(); break;
            case "shows_scroll_indicator": s.Indicator = Js.B(val, true); s.Apply(); break;
            case "scroll_event_throttle": s.Throttle = Js.Num(val) is double ms ? ms / 1000 : 0.016; break;
            case "on_scroll":
                if (val is JsonObject o)
                {
                    s.AE = Js.Obj(o["$ae"]) is JsonObject ae ? ae.ToDictionary(kv => kv.Key, kv => Js.I(kv.Value)) : null;
                    s.Emit = Js.B(o["emit"]);
                }
                else { s.AE = null; s.Emit = Js.B(val); }
                break;
            case "on_scroll_begin_drag": s.OnBegin = val != null; break;
            case "on_scroll_end_drag": s.OnEnd = val != null; break;
            case "on_momentum_scroll_end": s.OnMomentum = val != null; break;
            // paging_enabled and bounces: ScrollViewer has no paging or bounce switch (see windows/README.md).
        }
    }

    double SliderValue(int id, Slider s)
    {
        double v = s.Value, lo = s.Minimum;
        double step = Js.D(Ctl(id).GetValueOrDefault("step"));
        if (step > 0) v = lo + Math.Round((v - lo) / step) * step;
        return Math.Clamp(v, lo, Math.Max(lo, s.Maximum));
    }

    /// Merges props into the control's config and applies it (same prop contract as iOS and Android).
    void ApplyControl(int id, Node v, JsonObject props, List<string> removed)
    {
        var c = Ctl(id);
        foreach (var k in removed) c.Remove(k);
        foreach (var (k, val) in props) c[k] = val?.DeepClone();
        SolidColorBrush? Brush(string k) => Js.Color(c.GetValueOrDefault(k)) is uint u ? new SolidColorBrush(Colors.Of(u)) : null;
        double Dbl(string k, double d) => Js.Num(c.GetValueOrDefault(k)) ?? d;
        if ((props.ContainsKey("disabled") || removed.Contains("disabled")) && v.Content is Control ctrl)
            ctrl.IsEnabled = !Js.B(c.GetValueOrDefault("disabled"));
        settingControl.Add(id);
        try
        {
            switch (v.Content)
            {
                case ToggleSwitch sw:
                    sw.IsOn = Js.B(c.GetValueOrDefault("value"));
                    SetRes(sw, Brush("track_on"), "ToggleSwitchFillOn", "ToggleSwitchFillOnPointerOver", "ToggleSwitchFillOnPressed");
                    SetRes(sw, Brush("track_off"), "ToggleSwitchFillOff", "ToggleSwitchFillOffPointerOver", "ToggleSwitchFillOffPressed");
                    SetRes(sw, Brush("thumb_on") ?? Brush("thumb_off"), "ToggleSwitchKnobFillOn", "ToggleSwitchKnobFillOnPointerOver",
                           "ToggleSwitchKnobFillOnPressed");
                    SetRes(sw, Brush("thumb_off"), "ToggleSwitchKnobFillOff", "ToggleSwitchKnobFillOffPointerOver",
                           "ToggleSwitchKnobFillOffPressed");
                    break;
                case Slider sl:
                {
                    double lo = Dbl("minimum", 0), hi = Math.Max(lo, Dbl("maximum", 1)), step = Dbl("step", 0);
                    sl.Minimum = lo;
                    sl.Maximum = hi;
                    // The control's default step is 1, which would snap a 0..1 slider to its ends.
                    sl.StepFrequency = step > 0 ? step : Math.Max((hi - lo) / 1000, 1e-6);
                    if (!sliding.Contains(id)) sl.Value = Dbl("value", lo);
                    SetRes(sl, Brush("min_track_color"), "SliderTrackValueFill", "SliderTrackValueFillPointerOver", "SliderTrackValueFillPressed");
                    SetRes(sl, Brush("max_track_color"), "SliderTrackFill", "SliderTrackFillPointerOver", "SliderTrackFillPressed");
                    SetRes(sl, Brush("thumb_color"), "SliderThumbBackground", "SliderThumbBackgroundPointerOver", "SliderThumbBackgroundPressed");
                    break;
                }
                case ProgressRing pr:
                    if (Brush("color") is SolidColorBrush b) pr.Foreground = b; else pr.ClearValue(Control.ForegroundProperty);
                    pr.IsActive = Js.Bool(c.GetValueOrDefault("animating")) != false;
                    break;
            }
        }
        finally { settingControl.Remove(id); }
    }

    /// Lightweight styling: the control's template reads these theme resources; a missing colour restores the default.
    static void SetRes(Control c, Brush? b, params string[] keys)
    {
        foreach (var k in keys)
        {
            if (b != null) c.Resources[k] = b; else c.Resources.Remove(k);
        }
    }

    void ApplyImage(int id, Image v, JsonObject props, List<string> removed)
    {
        if (props.ContainsKey("resize_mode") || removed.Contains("resize_mode"))
        {
            v.Stretch = (Js.Str(props["resize_mode"]) ?? "cover") switch
            {
                "contain" => Stretch.Uniform,
                "stretch" => Stretch.Fill,
                "center" => Stretch.None,
                _ => Stretch.UniformToFill,
            };
        }
        // tint_color: no template-image rendering for bitmaps in XAML (see windows/README.md).
        if (!props.ContainsKey("source") && !removed.Contains("source")) return;
        var uri = Js.Str(Js.Obj(props["source"])?["uri"]) ?? "";
        if (uri.Length == 0)
        {
            imgReq.Remove(id);
            imgSize.Remove(id);
            v.Source = null;
            Native.px_node_mark_dirty(tree, id);
            return;
        }
        if (imgReq.GetValueOrDefault(id) == uri) return;
        imgReq[id] = uri;
        _ = LoadImage(id, v, uri);
    }

    async Task LoadImage(int id, Image v, string uri)
    {
        try
        {
            var data = await Images.Load(uri);
            if (imgReq.GetValueOrDefault(id) != uri) return;
            var bmp = new BitmapImage();
            using (var ms = new System.IO.MemoryStream(data))
                await bmp.SetSourceAsync(ms.AsRandomAccessStream());
            if (imgReq.GetValueOrDefault(id) != uri) return;
            v.Source = bmp;
            imgSize[id] = new Size(bmp.PixelWidth, bmp.PixelHeight);
            Native.px_node_mark_dirty(tree, id);
            Flush();
            Event("load", id, Value(new JsonObject { ["width"] = (double)bmp.PixelWidth, ["height"] = (double)bmp.PixelHeight }));
        }
        catch (Exception e)
        {
            if (imgReq.GetValueOrDefault(id) == uri) Event("error", id, Value(new JsonObject { ["message"] = e.Message }));
        }
    }

    static void ApplyA11y(Node v, Style a)
    {
        var el = v.Frame;
        var st = Js.Obj(a.GetValueOrDefault("accessibility_state"));
        var role = Js.Str(a.GetValueOrDefault("accessibility_role")) ?? "";
        var label = Js.Str(a.GetValueOrDefault("accessibility_label"));
        if (Js.Bool(a.GetValueOrDefault("accessible")) is bool acc)
            AutomationProperties.SetAccessibilityView(el, acc ? AccessibilityView.Content : AccessibilityView.Raw);
        else el.ClearValue(AutomationProperties.AccessibilityViewProperty);
        if (label != null) AutomationProperties.SetName(el, label); else el.ClearValue(AutomationProperties.NameProperty);
        if (Js.Str(a.GetValueOrDefault("accessibility_hint")) is string hint) AutomationProperties.SetHelpText(el, hint);
        else el.ClearValue(AutomationProperties.HelpTextProperty);
        var parts = new List<string>();
        if (role.Length > 0) parts.Add(role);
        if (Js.Bool(st?["checked"]) is bool c) parts.Add(c ? "checked" : "not checked");
        if (Js.B(st?["selected"])) parts.Add("selected");
        if (Js.B(st?["disabled"])) parts.Add("disabled");
        if (Js.Str(a.GetValueOrDefault("accessibility_value")) is string val) parts.Add(val);
        if (parts.Count > 0) AutomationProperties.SetItemStatus(el, string.Join(", ", parts));
        else el.ClearValue(AutomationProperties.ItemStatusProperty);
        if (role == "header") AutomationProperties.SetHeadingLevel(el, AutomationHeadingLevel.Level1);
        else el.ClearValue(AutomationProperties.HeadingLevelProperty);
    }

    int ParentNode(int parent) => types.GetValueOrDefault(parent) == "ScrollView" ? parent | ContentBit : parent;

    Panel? GroupOf(int parent)
    {
        if (scrolls.TryGetValue(parent, out var s)) return s.Content;
        return views.TryGetValue(parent, out var p) ? p.Kids : null;
    }

    static IEnumerable<Node> NodesIn(Panel p) => p.Children.OfType<FrameworkElement>().Select(e => e.Tag).OfType<Node>();

    void Insert(int parent0, int id, int index0)
    {
        // Modals live on the root so they cover the whole window whatever their Python parent is.
        int parent = types.GetValueOrDefault(id) == "Modal" ? 1 : parent0;
        int index = parent == parent0 ? index0 : int.MaxValue;
        if (GroupOf(parent) is not Panel g || !views.TryGetValue(id, out var v)) return;
        exiting.Remove(id);
        if (v.Frame.Parent is Panel old) old.Children.Remove(v.Frame);
        if (navs.TryGetValue(parent, out var nh0)) nh0.Lingering.Remove(v);
        g.Children.Insert(Math.Min(index, g.Children.Count), v.Frame);
        if (navs.TryGetValue(parent, out var nh)) nh.Pushed(v, NodesIn(g));
        Native.px_node_remove(tree, ParentNode(parent), id);
        Native.px_node_insert(tree, ParentNode(parent), id, index);
    }

    void Remove(int parent0, int id)
    {
        int parent = types.GetValueOrDefault(id) == "Modal" ? 1 : parent0;
        if (views.TryGetValue(id, out var v) && v.Frame.Parent is Panel g)
        {
            // A popped screen stays until its slide-out ends, unless it was inserted again meanwhile.
            exiting.Add(id);
            bool lingering = navs.TryGetValue(parent, out var nh) &&
                             nh.Popped(v, NodesIn(g), () => { if (exiting.Remove(id)) g.Children.Remove(v.Frame); });
            if (!lingering)
            {
                exiting.Remove(id);
                g.Children.Remove(v.Frame);
            }
        }
        Native.px_node_remove(tree, ParentNode(parent), id);
    }

    void Delete(int id)
    {
        // A screen still sliding out is removed by its animation's end.
        if (views.Remove(id, out var v) && !exiting.Contains(id) && v.Frame.Parent is Panel g) g.Children.Remove(v.Frame);
        binds.Remove(id);
        layoutListeners.Remove(id);
        imgReq.Remove(id);
        imgSize.Remove(id);
        touchKeys.Remove(id);
        navs.Remove(id);
        scrolls.Remove(id);
        sliding.Remove(id);
        if (types.Remove(id, out var t) && t == "ScrollView") Native.px_node_delete(tree, id | ContentBit);
        Native.px_node_delete(tree, id);
        styles.Remove(id);
        pads.Remove(id);
        texts.Remove(id);
        ctl.Remove(id);
        spans.Remove(id);
        a11y.Remove(id);
    }

    // -- TextInput -----------------------------------------------------------------------------------
    void ApplyInput(TextField t, string k, JsonNode? val)
    {
        switch (k)
        {
            case "keyboard_type":
            {
                var name = (Js.Str(val) ?? "default") switch
                {
                    "number" or "number-pad" or "numeric" or "decimal" or "decimal-pad" => InputScopeNameValue.Number,
                    "phone" or "phone-pad" => InputScopeNameValue.TelephoneNumber,
                    "email" or "email-address" => InputScopeNameValue.EmailSmtpAddress,
                    "url" => InputScopeNameValue.Url,
                    _ => InputScopeNameValue.Default,
                };
                var scope = new InputScope();
                scope.Names.Add(new InputScopeName(name));
                t.Box.InputScope = scope;
                break;
            }
            case "secure": t.SetSecure(Js.B(val)); break;
            case "auto_capitalize": break; // no auto-capitalization on desktop keyboards
            case "auto_correct":
                t.Box.IsSpellCheckEnabled = Js.B(val, true);
                t.Box.IsTextPredictionEnabled = Js.B(val, true);
                break;
            case "return_key": break; // no on-screen return key
            case "max_length":
                t.Box.MaxLength = Math.Max(0, Js.I(val));
                t.Pwd.MaxLength = Math.Max(0, Js.I(val));
                break;
            case "editable":
                t.Box.IsReadOnly = !Js.B(val, true);
                t.Pwd.IsEnabled = Js.B(val, true);
                break;
            case "select_on_focus": t.SelectOnFocus = Js.B(val); break;
            case "auto_focus":
                if (Js.B(val))
                {
                    void Focus() => t.Active.Focus(FocusState.Programmatic);
                    if (t.IsLoaded) t.DispatcherQueue.TryEnqueue(Focus);
                    else t.Loaded += (_, _) => Focus();
                }
                break;
        }
    }

    // -- calls ---------------------------------------------------------------------------------------
    void Reply(int id, JsonNode? value, string? error = null)
    {
        if (error != null) Event("call_result", id, new JsonObject { ["error"] = error });
        else Event("call_result", id, new JsonObject { ["value"] = value });
    }

    static JsonNode? Arg(JsonArray a, int i) => i < a.Count ? a[i] : null;

    void Call(int id, string module, string method, JsonArray args, bool wantReply)
    {
        switch (module + "." + method)
        {
            case "Scroll.to":
                if (scrolls.TryGetValue(Js.I(Arg(args, 0)), out var s1))
                    s1.ScrollTo(Js.Num(Arg(args, 1)), Js.Num(Arg(args, 2)), Js.B(Arg(args, 3), true));
                break;
            case "Scroll.to_end":
                if (scrolls.TryGetValue(Js.I(Arg(args, 0)), out var s2)) s2.ScrollTo(null, null, Js.B(Arg(args, 1), true));
                break;
            case "StatusBar.set_hidden": case "StatusBar.set_style": break; // no status bar on a desktop window
            case "Back.set_enabled": BackEnabled = Js.B(Arg(args, 0)); break;
            case "Back.exit": Application.Current.Exit(); break;
            case "Keyboard.dismiss": focusSink.Focus(FocusState.Programmatic); break;
            case "Clipboard.set_string":
            {
                var p = new Windows.ApplicationModel.DataTransfer.DataPackage();
                p.SetText(Js.Str(Arg(args, 0)) ?? "");
                Windows.ApplicationModel.DataTransfer.Clipboard.SetContent(p);
                break;
            }
            case "Clipboard.get_string":
                if (wantReply) { _ = ClipboardText(id); return; }
                break;
            case "Linking.open_url":
                if (Uri.TryCreate(Js.Str(Arg(args, 0)) ?? "", UriKind.Absolute, out var u))
                    _ = Launcher.LaunchUriAsync(u);
                break;
            case "SplashScreen.prevent_auto_hide": case "SplashScreen.hide": break; // the window shows the app at once
            case "Vibration.vibrate": break; // no vibration motor
            case "Alert.alert":
                _ = ShowAlert(id, Js.Str(Arg(args, 0)), Js.Str(Arg(args, 1)),
                              Arg(args, 2) is JsonArray ls ? ls.Select(x => Js.Str(x) ?? "").ToList() : null, wantReply);
                return;
            default:
                if (wantReply)
                    Reply(id, null, $"unknown native call {module}.{method} (is native module '{module}' listed in [tool.pyxpo] modules?)");
                return;
        }
        if (wantReply) Reply(id, null);
    }

    async Task ClipboardText(int id)
    {
        try
        {
            var c = Windows.ApplicationModel.DataTransfer.Clipboard.GetContent();
            var s = c.Contains(Windows.ApplicationModel.DataTransfer.StandardDataFormats.Text) ? await c.GetTextAsync() : "";
            Reply(id, s);
        }
        catch (Exception e) { Reply(id, null, e.Message); }
    }

    /// One dialog at a time (a XamlRoot shows one ContentDialog). Up to three buttons, in label order.
    async Task ShowAlert(int id, string? title, string? message, List<string>? labels0, bool wantReply)
    {
        var labels = labels0 is { Count: > 0 } ? labels0 : new List<string> { "OK" };
        await alertGate.WaitAsync();
        try
        {
            var d = new ContentDialog
            {
                Title = title, Content = message, XamlRoot = root.Frame.XamlRoot, RequestedTheme = root.Frame.ActualTheme,
            };
            int n = Math.Min(3, labels.Count);
            if (n == 1) d.CloseButtonText = labels[0];
            else
            {
                d.PrimaryButtonText = labels[0];
                if (n == 3) d.SecondaryButtonText = labels[1];
                d.CloseButtonText = labels[n - 1];
                d.DefaultButton = ContentDialogButton.Primary;
            }
            var r = await d.ShowAsync();
            int index = r switch
            {
                ContentDialogResult.Primary => 0,
                ContentDialogResult.Secondary => 1,
                _ => n - 1,
            };
            if (wantReply) Reply(id, index);
        }
        catch (Exception e) { if (wantReply) Reply(id, null, e.Message); }
        finally { alertGate.Release(); }
    }

    // -- style ---------------------------------------------------------------------------------------
    int Prop(string name)
    {
        if (propIds.TryGetValue(name, out var p)) return p;
        p = Native.px_prop_id(name);
        propIds[name] = p;
        return p;
    }

    JsonNode AnimVal(string k, int node)
    {
        double x = anim.Resolve(node);
        if (k == "color" || k.EndsWith("_color")) return JsonValue.Create((double)(uint)(long)x);
        return JsonValue.Create(x);
    }

    /// Replaces `{"$a": node}` bindings with the node's current value and records the bindings for the frame loop.
    Style ResolveBinds(int id, JsonObject s)
    {
        var o = new Style();
        Dictionary<string, int>? b = null;
        foreach (var (k, v) in s)
        {
            if (v is JsonObject m && Js.Num(m["$a"]) is double n)
            {
                (b ??= new Dictionary<string, int>())[k] = (int)n;
                o[k] = AnimVal(k, (int)n);
            }
            else o[k] = v;
        }
        if (b == null) binds.Remove(id); else binds[id] = b;
        return o;
    }

    HashSet<int> DepsOf(int node)
    {
        if (depCache.TryGetValue(node, out var d)) return d;
        d = new HashSet<int>();
        anim.Deps(node, d);
        depCache[node] = d;
        return d;
    }

    /// Per-frame: write the changed animated values straight onto views. Layout keys re-run the engine once.
    void OnAnimFrame(HashSet<int> touched)
    {
        bool relayout = false;
        foreach (var (id, b) in binds.ToList())
        {
            if (!views.TryGetValue(id, out var v) || !styles.TryGetValue(id, out var s)) continue;
            bool tr = false, box = false, txt = false;
            foreach (var (k, n) in b)
            {
                if (!touched.Overlaps(DepsOf(n))) continue;
                var nv = AnimVal(k, n);
                s[k] = nv;
                if (TransformKeys.Contains(k)) tr = true;
                else if (k == "color") txt = true;
                else
                {
                    if (k.StartsWith("shadow") || k == "elevation" || k.StartsWith("background") || k.StartsWith("border")) box = true;
                    if (Prop(k) >= 0)
                    {
                        Native.px_node_set_num(tree, id, Prop(k), (float)Js.D(nv));
                        Native.px_node_mark_dirty(tree, id);
                        relayout = true;
                    }
                }
            }
            if (tr) PaintTransform(v, s);
            if (box) PaintBox(v, s);
            if (txt) PaintText(id, v, s);
        }
        if (relayout) Flush();
    }

    void ApplyStyle(int id, Node v, JsonObject raw)
    {
        var s = ResolveBinds(id, raw);
        var old = StyleOf(id);
        foreach (var (k, nv) in s)
        {
            if (old.TryGetValue(k, out var ov) && ov?.ToJsonString() == nv?.ToJsonString()) continue;
            int p = Prop(k);
            if (p < 0) continue;
            if (Js.Num(nv) is double d) Native.px_node_set_num(tree, id, p, (float)d);
            else if (Js.Str(nv) is string str) Native.px_node_set_str(tree, id, p, str);
        }
        foreach (var k in old.Keys)
        {
            if (s.ContainsKey(k)) continue;
            int p = Prop(k);
            if (p >= 0) Native.px_node_reset(tree, id, p);
        }
        styles[id] = s;
        v.SetHidden(Js.Str(s.GetValueOrDefault("display")) == "none");
        Paint(id, v, s);
        Native.px_node_mark_dirty(tree, id);
    }

    static double Num(Style s, string k, double d = 0) => Js.Num(s.GetValueOrDefault(k)) ?? d;
    static uint? Col(Style s, string k) => Js.Color(s.GetValueOrDefault(k));

    void Paint(int id, Node v, Style s)
    {
        // Leaf views draw their own content, so padding + border become content insets.
        if (Leaves.Contains(types.GetValueOrDefault(id) ?? ""))
        {
            double E(string side) => Num(s, "padding_" + side) + Num(s, "border_" + side + "_width");
            var p = new Thickness(E("left"), E("top"), E("right"), E("bottom"));
            pads[id] = p;
            switch (v.Content)
            {
                case TextBlock tb: tb.Padding = p; break;
                case Button b: b.Padding = p; break;
                case FrameworkElement fe: fe.Margin = p; break;
            }
        }
        PaintBox(v, s);
        PaintTransform(v, s);
        PaintText(id, v, s);
    }

    static void PaintTransform(Node v, Style s) =>
        v.SetTransform(Num(s, "opacity", 1), Num(s, "scale", 1), Num(s, "scale_x", 1), Num(s, "scale_y", 1), Num(s, "rotate"),
                       Num(s, "translate_x"), Num(s, "translate_y"));

    static void PaintBox(Node v, Style s)
    {
        var spec = new BoxSpec { Bg = Col(s, "background_color") };
        var corners = new[] { "top_left", "top_right", "bottom_right", "bottom_left" };
        for (int i = 0; i < 4; i++) spec.Radii[i] = Num(s, "border_" + corners[i] + "_radius");
        var sides = new[] { "left", "top", "right", "bottom" };
        for (int i = 0; i < 4; i++) spec.Bw[i] = Num(s, "border_" + sides[i] + "_width");
        // XAML borders take one brush: the first side with a width and a colour decides it.
        for (int i = 0; i < 4; i++)
        {
            if (spec.Bw[i] > 0 && Col(s, "border_" + sides[i] + "_color") is uint bc) { spec.Bc = bc; break; }
        }
        spec.Clip = Js.Str(s.GetValueOrDefault("overflow")) == "hidden";
        if (Js.Obj(s.GetValueOrDefault("linear_gradient")) is JsonObject g && g["colors"] is JsonArray cs)
        {
            spec.GradColors = cs.Select(c => Js.Color(c) ?? 0).ToArray();
            spec.GradStops = g["stops"] is JsonArray st ? Js.Nums(st).ToArray() : null;
            spec.GradAngle = Js.D(g["angle"], 180);
        }
        bool hasShadowKey = s.ContainsKey("shadow_radius") || s.ContainsKey("shadow_color");
        double op = Num(s, "shadow_opacity", hasShadowKey ? 1 : 0);
        double elev = Num(s, "elevation");
        spec.ShadowColor = Col(s, "shadow_color") ?? 0xFF000000;
        spec.ShadowOpacity = Math.Clamp(op > 0 || elev > 0 ? Math.Max(op, elev > 0 ? 0.25 : 0) : 0, 0, 1);
        spec.ShadowRadius = Math.Max(Num(s, "shadow_radius"), elev);
        spec.ShadowX = Num(s, "shadow_offset_x");
        spec.ShadowY = Num(s, "shadow_offset_y") + (elev > 0 && !s.ContainsKey("shadow_offset_y") ? elev / 2 : 0);
        v.SetBox(spec);
    }

    static int Weight(JsonNode? w)
    {
        if (Js.Str(w) is string s) return s == "bold" ? 700 : int.TryParse(s, out var n) ? n : 400;
        return Js.Num(w) is double d ? (int)d : 400;
    }

    static FontFamily? Family(Style s)
    {
        var name = Js.Str(s.GetValueOrDefault("font_family")) switch
        {
            "monospace" => "Consolas",
            "serif" => "Cambria",
            "sans-serif" or "system" or null or "" => null,
            var other => other,
        };
        if (name == null) return null;
        if (!families.TryGetValue(name, out var f)) families[name] = f = new FontFamily(name);
        return f;
    }

    static double FontSize(Style s)
    {
        double b = Num(s, "font_size", 14);
        return Js.B(s.GetValueOrDefault("allow_font_scaling"), true) ? b * FontScale : b;
    }

    static TextDecorations Decorations(Style s)
    {
        var d = Js.Str(s.GetValueOrDefault("text_decoration")) ?? "";
        var r = TextDecorations.None;
        if (d.Contains("underline")) r |= TextDecorations.Underline;
        if (d.Contains("line-through")) r |= TextDecorations.Strikethrough;
        return r;
    }

    static int Spacing(Style s, double size) =>
        Js.Num(s.GetValueOrDefault("letter_spacing")) is double ls && size > 0 ? (int)Math.Round(ls / size * 1000) : 0;

    static void Font(TextElement e, Style s)
    {
        double size = FontSize(s);
        e.FontSize = size;
        e.FontWeight = new FontWeight((ushort)Math.Clamp(Weight(s.GetValueOrDefault("font_weight")), 1, 999));
        e.FontStyle = Js.Str(s.GetValueOrDefault("font_style")) == "italic" ? FontStyle.Italic : FontStyle.Normal;
        if (Family(s) is FontFamily f) e.FontFamily = f;
        if (Col(s, "color") is uint c) e.Foreground = new SolidColorBrush(Colors.Of(c));
        e.CharacterSpacing = Spacing(s, size);
        e.TextDecorations = Decorations(s);
    }

    static void Font(Control e, Style s)
    {
        double size = FontSize(s);
        e.FontSize = size;
        e.FontWeight = new FontWeight((ushort)Math.Clamp(Weight(s.GetValueOrDefault("font_weight")), 1, 999));
        e.FontStyle = Js.Str(s.GetValueOrDefault("font_style")) == "italic" ? FontStyle.Italic : FontStyle.Normal;
        if (Family(s) is FontFamily f) e.FontFamily = f; else e.ClearValue(Control.FontFamilyProperty);
        if (Col(s, "color") is uint c) e.Foreground = new SolidColorBrush(Colors.Of(c)); else e.ClearValue(Control.ForegroundProperty);
        e.CharacterSpacing = Spacing(s, size);
    }

    static TextAlignment Align(Style s) => Js.Str(s.GetValueOrDefault("text_align")) switch
    {
        "center" => TextAlignment.Center,
        "right" => TextAlignment.Right,
        "justify" => TextAlignment.Justify,
        _ => TextAlignment.Left,
    };

    /// Text node: one Run per span (nested Text) or one Run for the text, with the node style as the base.
    void RenderText(int id, TextBlock tb, Style s)
    {
        tb.TextAlignment = Align(s);
        int lines = (int)Num(s, "number_of_lines");
        tb.MaxLines = Math.Max(0, lines);
        tb.TextTrimming = lines > 0 ? TextTrimming.CharacterEllipsis : TextTrimming.None;
        if (Js.Num(s.GetValueOrDefault("line_height")) is double lh)
        {
            tb.LineHeight = lh * (Js.B(s.GetValueOrDefault("allow_font_scaling"), true) ? FontScale : 1);
            tb.LineStackingStrategy = LineStackingStrategy.BlockLineHeight;
        }
        else
        {
            tb.ClearValue(TextBlock.LineHeightProperty);
            tb.LineStackingStrategy = LineStackingStrategy.MaxHeight;
        }
        tb.FontSize = FontSize(s);
        if (Family(s) is FontFamily f) tb.FontFamily = f; else tb.ClearValue(TextBlock.FontFamilyProperty);
        if (Col(s, "color") is uint c) tb.Foreground = new SolidColorBrush(Colors.Of(c));
        else tb.ClearValue(TextBlock.ForegroundProperty);
        tb.Inlines.Clear();
        tb.TextHighlighters.Clear();
        if (spans.TryGetValue(id, out var sp) && sp.Count > 0)
        {
            int at = 0;
            foreach (var o in sp)
            {
                var st = new Style(s);
                if (Js.Obj(o["style"]) is JsonObject ov) foreach (var (k, val) in ov) st[k] = val;
                var text = Js.Str(o["text"]) ?? "";
                var r = new Run { Text = text };
                Font(r, st);
                tb.Inlines.Add(r);
                if (Col(st, "background_color") is uint bg && text.Length > 0)
                {
                    var h = new TextHighlighter { Background = new SolidColorBrush(Colors.Of(bg)) };
                    h.Ranges.Add(new TextRange { StartIndex = at, Length = text.Length });
                    tb.TextHighlighters.Add(h);
                }
                at += text.Length;
            }
        }
        else
        {
            var r = new Run { Text = texts.GetValueOrDefault(id) ?? "" };
            Font(r, s);
            tb.Inlines.Add(r);
        }
    }

    void PaintText(int id, Node v, Style s)
    {
        switch (v.Content)
        {
            case TextBlock tb: RenderText(id, tb, s); break;
            case Button b: Font(b, s); break;
            case TextField t:
                Font(t.Box, s);
                Font(t.Pwd, s);
                t.Box.TextAlignment = Align(s);
                break;
        }
    }

    // -- layout --------------------------------------------------------------------------------------
    unsafe void MeasureCb(IntPtr ctx, int id, float w, int wMode, float h, int hMode, float* ow, float* oh)
    {
        Size r;
        try { r = Measure(id, w, wMode, h, hMode); }
        catch (Exception e) { Console.Error.WriteLine("pyxpo: measure failed: " + e.Message); r = default; }
        *ow = (float)r.Width;
        *oh = (float)r.Height;
    }

    /// Leaf measure callback from the engine. w/h are inner sizes (without padding and border) in DIPs.
    Size Measure(int id, float w, int wm, float h, int hm)
    {
        if (!views.TryGetValue(id, out var v)) return default;
        double inf = double.PositiveInfinity;
        double lw = wm == 2 || float.IsNaN(w) || w > 1e6 ? inf : Math.Max(0, w);
        double lh = hm == 2 || float.IsNaN(h) || h > 1e6 ? inf : Math.Max(0, h);
        var p = pads.GetValueOrDefault(id);
        double pw = p.Left + p.Right, ph = p.Top + p.Bottom;
        double sw = 0, sh = 0;
        switch (v.Content)
        {
            case TextBlock tb:
            {
                tb.Measure(new Size(lw + pw, lh + ph));
                sw = tb.DesiredSize.Width - pw;
                sh = tb.DesiredSize.Height - ph;
                break;
            }
            case Button b:
            {
                b.Measure(new Size(lw + pw, lh + ph));
                sw = b.DesiredSize.Width - pw;
                sh = b.DesiredSize.Height - ph;
                break;
            }
            case TextField t:
            {
                var c = t.Active;
                c.Measure(new Size(inf, inf));
                sh = Math.Max(c.DesiredSize.Height, Math.Ceiling(c.FontSize * 1.33));
                break;
            }
            case Image:
                var n = imgSize.GetValueOrDefault(id);
                sw = n.Width;
                sh = n.Height;
                break;
            case ToggleSwitch sw0:
                sw0.Measure(new Size(inf, inf));
                sw = sw0.DesiredSize.Width > 0 ? sw0.DesiredSize.Width : 40;
                sh = sw0.DesiredSize.Height > 0 ? sw0.DesiredSize.Height : 32;
                break;
            case Slider: sh = 32; break;
            case ProgressRing: sw = 20; sh = 20; break;
        }
        if (wm == 0) sw = lw;
        if (hm == 0) sh = lh;
        double sc = Math.Max(1, root.Frame.XamlRoot?.RasterizationScale ?? 1);
        return new Size(Math.Ceiling(Math.Max(0, sw) * sc) / sc, Math.Ceiling(Math.Max(0, sh) * sc) / sc);
    }

    void OnRootSize(Size s)
    {
        if (s.Width <= 0 || s.Height <= 0 || s == rootSize) return;
        rootSize = s;
        root.Rect = new Rect(0, 0, s.Width, s.Height);
        SendEnv();
        Flush();
    }

    public Size RootSize => rootSize;

    /// Env snapshot for the Python side. Sizes in DIPs; Windows has no safe-area insets or soft keyboard.
    public static JsonObject EnvJson(Size window, Size screen, double scale, bool dark, bool startup)
    {
        var j = new JsonObject
        {
            ["insets"] = new JsonObject { ["left"] = 0.0, ["top"] = 0.0, ["right"] = 0.0, ["bottom"] = 0.0 },
            ["keyboard"] = new JsonObject { ["visible"] = false, ["height"] = 0.0 },
            ["os"] = "windows",
            ["window"] = new JsonObject { ["width"] = window.Width, ["height"] = window.Height },
            ["screen"] = new JsonObject { ["width"] = screen.Width, ["height"] = screen.Height },
            ["scale"] = scale,
            ["font_scale"] = FontScale,
            ["color_scheme"] = dark ? "dark" : "light",
            // Module calls run in Python on Windows (desktop.py backends): the shell links no native modules.
            ["modules"] = new JsonArray(),
        };
        if (startup) j["module_constants"] = new JsonObject();
        return j;
    }

    /// Sends the current window / scale / colour scheme to Python when it changed.
    public void SendEnv()
    {
        if (rootSize.Width <= 0 || EnvSource == null) return;
        var j = EnvSource();
        j.Remove("os");
        var sorted = Sorted(j)!.ToJsonString();
        if (sorted == sentEnv) return;
        sentEnv = sorted;
        Event("env", 0, j);
    }

    static JsonNode? Sorted(JsonNode? n)
    {
        if (n is not JsonObject o) return n?.DeepClone();
        var r = new JsonObject();
        foreach (var (k, v) in o.OrderBy(kv => kv.Key, StringComparer.Ordinal)) r[k] = Sorted(v);
        return r;
    }

    /// Text size, dark mode or DPI change: fonts and leaf sizes may differ.
    public void ConfigChanged()
    {
        SendEnv();
        foreach (var (id, s) in styles) if (views.TryGetValue(id, out var v)) PaintText(id, v, s);
        foreach (var (id, t) in types) if (Leaves.Contains(t)) Native.px_node_mark_dirty(tree, id);
        Flush();
    }

    readonly float[] frame = new float[4];

    unsafe void Flush()
    {
        if (rootSize.Width <= 0) return;
        Native.px_tree_calc(tree, (float)rootSize.Width, (float)rootSize.Height);
        int n = Native.px_tree_changed_count(tree);
        fixed (float* f = frame)
        {
            for (int i = 0; i < n; i++)
            {
                int id = Native.px_tree_changed_at(tree, i, f);
                var r = new Rect(f[0], f[1], Math.Max(0, f[2]), Math.Max(0, f[3]));
                if (id == 1) continue;
                if ((id & ContentBit) != 0)
                {
                    if (scrolls.TryGetValue(id & ~ContentBit, out var sh)) sh.SetContentSize(r.Width, r.Height);
                    continue;
                }
                if (layoutListeners.Contains(id)) Event("layout", id, Value(Rect4(r.X, r.Y, r.Width, r.Height)));
                if (views.TryGetValue(id, out var v)) v.SetFrame(r);
            }
        }
    }
}
