using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Numerics;
using Microsoft.UI.Composition;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Input;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.Foundation;
using Windows.UI;
using Path = Microsoft.UI.Xaml.Shapes.Path;

namespace Pyxpo;

/// Box look of a node, the same fields as BoxSpec in the iOS shell. Sides are left, top, right, bottom; corners
/// top-left, top-right, bottom-right, bottom-left.
sealed class BoxSpec
{
    public uint? Bg;
    public double[] Radii = new double[4];
    public double[] Bw = new double[4];
    public uint Bc = 0xFF000000;
    public bool Clip;
    public uint[]? GradColors;
    public double[]? GradStops;
    public double GradAngle = 180;
    public uint ShadowColor = 0xFF000000;
    public double ShadowOpacity, ShadowRadius, ShadowX, ShadowY;

    public bool HasRadius => Radii[0] > 0 || Radii[1] > 0 || Radii[2] > 0 || Radii[3] > 0;
}

/// One node of the native tree. `Frame` is a Grid with an explicit size, placed with Canvas.Left/Top in the
/// parent's `Kids` canvas from the layout engine's frame. Inside: an optional shadow host, the box (background,
/// border, corners), then the content: a leaf control, or the `Kids` canvas that holds child nodes.
class Node
{
    public readonly int Id;
    public readonly string Type;
    public readonly Grid Frame = new();
    public readonly Border Box = new();
    /// Leaf control (TextBlock, Button, TextBox, Image, ...) or the ScrollViewer; null for plain containers.
    public FrameworkElement? Content;
    /// Child nodes go here. Null for leaves.
    public Canvas? Kids;
    public Rect Rect;
    public bool Hidden;
    public Touch? Touch;
    /// Translation.X set by a NavStack transition (screens only).
    public float Tx;

    Canvas? shadowHost;
    LayerVisual? shadowLayer;
    BoxSpec spec = new();
    double scale = 1, sx = 1, sy = 1, rot, tx, ty;

    public Node(int id, string type, FrameworkElement? content, bool container)
    {
        Id = id;
        Type = type;
        Frame.Children.Add(Box);
        Content = content;
        if (container && content == null)
        {
            Kids = new Canvas();
            Frame.Children.Add(Kids);
        }
        else if (content != null) Frame.Children.Add(content);
    }

    public void SetFrame(Rect r)
    {
        bool sized = r.Width != Rect.Width || r.Height != Rect.Height;
        Rect = r;
        Frame.Width = Math.Max(0, r.Width);
        Frame.Height = Math.Max(0, r.Height);
        Canvas.SetLeft(Frame, r.X);
        Canvas.SetTop(Frame, r.Y);
        if (sized)
        {
            ApplyTransform();
            LayoutBox();
            (Content as PathView)?.Rebuild();
        }
    }

    public void SetHidden(bool h)
    {
        Hidden = h;
        Frame.Visibility = h ? Visibility.Collapsed : Visibility.Visible;
    }

    /// Hit testing: a Grid without a background only hits its children. Touch handlers need the whole frame.
    public void SetHittable(bool on) => Frame.Background = on ? new SolidColorBrush(Microsoft.UI.Colors.Transparent) : null;

    // -- transform -----------------------------------------------------------------------------------
    public void SetTransform(double opacity, double scale, double scaleX, double scaleY, double rotate, double translateX,
                             double translateY)
    {
        Frame.Opacity = Math.Clamp(opacity, 0, 1);
        this.scale = scale; sx = scaleX; sy = scaleY; rot = rotate; tx = translateX; ty = translateY;
        ApplyTransform();
    }

    void ApplyTransform()
    {
        bool identity = scale == 1 && sx == 1 && sy == 1 && rot == 0 && tx == 0 && ty == 0;
        if (identity) { Frame.RenderTransform = null; return; }
        Frame.RenderTransform = new CompositeTransform
        {
            CenterX = Rect.Width / 2, CenterY = Rect.Height / 2,
            ScaleX = scale * sx, ScaleY = scale * sy, Rotation = rot, TranslateX = tx, TranslateY = ty,
        };
    }

    // -- box -----------------------------------------------------------------------------------------
    public void SetBox(BoxSpec s)
    {
        spec = s;
        Box.CornerRadius = new CornerRadius(s.Radii[0], s.Radii[1], s.Radii[2], s.Radii[3]);
        Box.BorderThickness = new Thickness(s.Bw[0], s.Bw[1], s.Bw[2], s.Bw[3]);
        Box.BorderBrush = new SolidColorBrush(Colors.Of(s.Bc));
        if (s.GradColors is { Length: > 0 } cs) Box.Background = Gradient(cs, s.GradStops, s.GradAngle);
        else Box.Background = s.Bg is uint bg ? new SolidColorBrush(Colors.Of(bg)) : null;
        if (Content is FrameworkElement leaf && Kids == null && Content is not ScrollViewer)
        {
            // A rounded leaf (an Image with border_radius) is cut to the box like a clipped container.
            if (s.HasRadius || s.Clip) leaf.Clip = null;
        }
        LayoutBox();
    }

    /// CSS linear-gradient angle (0 = to top, 90 = to right, 180 = to bottom) in the box's relative space.
    static LinearGradientBrush Gradient(uint[] colors, double[]? stops, double angle)
    {
        double a = angle * Math.PI / 180, dx = Math.Sin(a), dy = -Math.Cos(a);
        double len = Math.Abs(dx) + Math.Abs(dy);
        var g = new LinearGradientBrush
        {
            MappingMode = BrushMappingMode.RelativeToBoundingBox,
            StartPoint = new Point(0.5 - dx * len / 2, 0.5 - dy * len / 2),
            EndPoint = new Point(0.5 + dx * len / 2, 0.5 + dy * len / 2),
        };
        for (int i = 0; i < colors.Length; i++)
        {
            double off = stops != null && i < stops.Length ? stops[i] : (colors.Length == 1 ? 0 : (double)i / (colors.Length - 1));
            g.GradientStops.Add(new GradientStop { Color = Colors.Of(colors[i]), Offset = off });
        }
        return g;
    }

    /// Re-applies size-dependent parts of the box: the shadow shape and the clip.
    public void LayoutBox()
    {
        float w = (float)Rect.Width, h = (float)Rect.Height;
        LayoutShadow(w, h);
        var clipTarget = (UIElement?)Kids ?? (Content is ScrollViewer ? null : Content);
        if (clipTarget == null) return;
        var v = ElementCompositionPreview.GetElementVisual(clipTarget);
        bool leaf = Kids == null;
        if ((spec.Clip || (leaf && spec.HasRadius)) && w > 0 && h > 0)
        {
            var c = v.Compositor;
            var geo = c.CreateRoundedRectangleGeometry();
            // A leaf has its insets as margin: its visual starts inside the padding + border.
            var m = (clipTarget as FrameworkElement)?.Margin ?? default;
            geo.Offset = new Vector2((float)-m.Left, (float)-m.Top);
            geo.Size = new Vector2(w, h);
            // Composition rounds all corners alike: the largest radius is the closest match.
            float r = (float)Math.Max(Math.Max(spec.Radii[0], spec.Radii[1]), Math.Max(spec.Radii[2], spec.Radii[3]));
            geo.CornerRadius = new Vector2(r, r);
            v.Clip = c.CreateGeometricClip(geo);
        }
        else v.Clip = null;
    }

    void LayoutShadow(float w, float h)
    {
        bool on = spec.ShadowOpacity > 0 && w > 0 && h > 0 && (spec.Bg is uint bg && (bg >> 24) > 0 || spec.GradColors != null);
        if (!on)
        {
            if (shadowHost != null) { ElementCompositionPreview.SetElementChildVisual(shadowHost, null); Frame.Children.Remove(shadowHost); }
            shadowHost = null; shadowLayer = null;
            return;
        }
        if (shadowHost == null)
        {
            shadowHost = new Canvas { IsHitTestVisible = false };
            Frame.Children.Insert(0, shadowHost);
        }
        var comp = ElementCompositionPreview.GetElementVisual(Frame).Compositor;
        if (shadowLayer == null)
        {
            shadowLayer = comp.CreateLayerVisual();
            ElementCompositionPreview.SetElementChildVisual(shadowHost, shadowLayer);
        }
        shadowLayer.Size = new Vector2(w, h);
        shadowLayer.Children.RemoveAll();
        // The shadow is cast by a rounded rect of the box's shape; the box itself draws on top of it.
        var geo = comp.CreateRoundedRectangleGeometry();
        geo.Size = new Vector2(w, h);
        float r = (float)Math.Max(Math.Max(spec.Radii[0], spec.Radii[1]), Math.Max(spec.Radii[2], spec.Radii[3]));
        geo.CornerRadius = new Vector2(r, r);
        var shape = comp.CreateSpriteShape(geo);
        shape.FillBrush = comp.CreateColorBrush(Colors.Of(spec.Bg ?? 0xFFFFFFFF));
        var sv = comp.CreateShapeVisual();
        sv.Size = new Vector2(w, h);
        sv.Shapes.Add(shape);
        shadowLayer.Children.InsertAtTop(sv);
        var ds = comp.CreateDropShadow();
        ds.Color = Colors.Of(spec.ShadowColor);
        ds.Opacity = (float)spec.ShadowOpacity;
        ds.BlurRadius = (float)(spec.ShadowRadius * 2);
        ds.Offset = new Vector3((float)spec.ShadowX, (float)spec.ShadowY, 0);
        shadowLayer.Shadow = ds;
    }
}

static class Colors
{
    public static Color Of(uint argb) => Color.FromArgb((byte)(argb >> 24), (byte)(argb >> 16), (byte)(argb >> 8), (byte)argb);
}

/// on_press* and on_touch_* handlers, as PxGroup on iOS: press_in(point), press_out, press, long_press after 0.5 s
/// (a long press sends no press), and raw touch_start/move/end with the point in the node and in the window.
sealed class Touch
{
    public Action<string, Point?>? OnTouch;
    public Action<string, Point, Point>? OnRaw;
    readonly Node n;
    readonly UIElement root;
    bool down, longFired;
    uint? pointer;
    DispatcherQueueTimer? timer;

    public Touch(Node n, UIElement root)
    {
        this.n = n;
        this.root = root;
        var f = n.Frame;
        f.PointerPressed += Pressed;
        f.PointerMoved += Moved;
        f.PointerReleased += Released;
        f.PointerCanceled += Cancelled;
        f.PointerCaptureLost += Cancelled;
    }

    public bool Active => OnTouch != null || OnRaw != null;

    void Raw(string name, PointerRoutedEventArgs e)
    {
        if (OnRaw is { } r) r(name, e.GetCurrentPoint(n.Frame).Position, e.GetCurrentPoint(root).Position);
    }

    void Pressed(object sender, PointerRoutedEventArgs e)
    {
        if (!Active || pointer != null) return;
        var p = e.GetCurrentPoint(n.Frame);
        if (e.Pointer.PointerDeviceType == PointerDeviceType.Mouse && !p.Properties.IsLeftButtonPressed) return;
        e.Handled = true;
        pointer = e.Pointer.PointerId;
        n.Frame.CapturePointer(e.Pointer);
        Raw("touch_start", e);
        if (OnTouch is not { } cb) return;
        down = true;
        longFired = false;
        timer?.Stop();
        timer = n.Frame.DispatcherQueue.CreateTimer();
        timer.Interval = TimeSpan.FromSeconds(0.5);
        timer.IsRepeating = false;
        timer.Tick += (_, _) =>
        {
            if (!down) return;
            longFired = true;
            OnTouch?.Invoke("long_press", null);
        };
        timer.Start();
        cb("press_in", p.Position);
    }

    void Moved(object sender, PointerRoutedEventArgs e)
    {
        if (pointer != e.Pointer.PointerId) return;
        e.Handled = true;
        Raw("touch_move", e);
        if (OnTouch is not { } cb || !down) return;
        var p = e.GetCurrentPoint(n.Frame).Position;
        const double slop = 24;
        if (p.X < -slop || p.Y < -slop || p.X > n.Rect.Width + slop || p.Y > n.Rect.Height + slop)
        {
            down = false;
            timer?.Stop();
            cb("press_out", null);
        }
    }

    void Released(object sender, PointerRoutedEventArgs e)
    {
        if (pointer != e.Pointer.PointerId) return;
        e.Handled = true;
        pointer = null;
        Raw("touch_end", e);
        timer?.Stop();
        if (down)
        {
            down = false;
            OnTouch?.Invoke("press_out", null);
            if (!longFired) OnTouch?.Invoke("press", null);
        }
        n.Frame.ReleasePointerCapture(e.Pointer);
    }

    void Cancelled(object sender, PointerRoutedEventArgs e)
    {
        if (pointer != e.Pointer.PointerId) return;
        pointer = null;
        Raw("touch_end", e);
        timer?.Stop();
        if (down) { down = false; OnTouch?.Invoke("press_out", null); }
    }
}

/// ScrollView: a ScrollViewer whose content is the canvas placed by the engine's synthetic content node.
sealed class ScrollHost
{
    public readonly ScrollViewer View = new()
    {
        ZoomMode = ZoomMode.Disabled,
        IsTabStop = false,
        HorizontalScrollMode = ScrollMode.Disabled,
        HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
        VerticalScrollMode = ScrollMode.Enabled,
        VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
    };
    public readonly Canvas Content = new();
    public bool Emit, OnBegin, OnEnd, OnMomentum, Horizontal, Enabled = true, Indicator = true;
    public double Throttle = 0.016;
    public Dictionary<string, int>? AE;
    public Action<Dictionary<int, double>>? OnAE;
    public Action<string, Dictionary<string, object>>? OnEvent;
    readonly Stopwatch clock = Stopwatch.StartNew();
    double last = -1;

    public ScrollHost()
    {
        View.Content = Content;
        View.ViewChanged += (_, e) =>
        {
            Scrolled();
            if (!e.IsIntermediate) Settled();
        };
        View.DirectManipulationStarted += (_, _) => { if (OnBegin) Send("scroll_begin_drag"); };
        View.DirectManipulationCompleted += (_, _) => { if (OnEnd) Send("scroll_end_drag"); };
    }

    public void SetHorizontal(bool h)
    {
        Horizontal = h;
        Apply();
    }

    /// scroll_enabled, shows_scroll_indicator and horizontal decide the modes of both axes.
    public void Apply()
    {
        var on = Enabled ? ScrollMode.Enabled : ScrollMode.Disabled;
        var bar = Indicator ? ScrollBarVisibility.Auto : ScrollBarVisibility.Hidden;
        View.HorizontalScrollMode = Horizontal ? on : ScrollMode.Disabled;
        View.VerticalScrollMode = Horizontal ? ScrollMode.Disabled : on;
        View.HorizontalScrollBarVisibility = Horizontal ? bar : ScrollBarVisibility.Disabled;
        View.VerticalScrollBarVisibility = Horizontal ? ScrollBarVisibility.Disabled : bar;
    }

    public void SetContentSize(double w, double h)
    {
        Content.Width = Math.Max(0, w);
        Content.Height = Math.Max(0, h);
    }

    public Dictionary<string, object> Info() => new()
    {
        ["x"] = View.HorizontalOffset, ["y"] = View.VerticalOffset,
        ["width"] = View.ViewportWidth, ["height"] = View.ViewportHeight,
        ["content_width"] = Content.Width is double cw && !double.IsNaN(cw) ? cw : 0.0,
        ["content_height"] = Content.Height is double ch && !double.IsNaN(ch) ? ch : 0.0,
    };

    void Send(string name) => OnEvent?.Invoke(name, new Dictionary<string, object> { ["value"] = Info() });

    void Scrolled()
    {
        if (AE != null && OnAE != null)
        {
            var i = Info();
            var vals = new Dictionary<int, double>();
            foreach (var (k, id) in AE) if (i.TryGetValue(k, out var v) && v is double d) vals[id] = d;
            OnAE(vals);
        }
        double now = clock.Elapsed.TotalSeconds;
        if (Emit && now - last >= Throttle) { last = now; Send("scroll"); }
    }

    void Settled()
    {
        if (Emit) Send("scroll");
        if (OnMomentum) Send("momentum_scroll_end");
    }

    /// Scroll.to / Scroll.to_end: a missing axis keeps its offset, or goes to the end along the scroll axis.
    public void ScrollTo(double? x, double? y, bool animated)
    {
        double maxX = Math.Max(0, View.ExtentWidth - View.ViewportWidth), maxY = Math.Max(0, View.ExtentHeight - View.ViewportHeight);
        double tx = x ?? (Horizontal ? maxX : View.HorizontalOffset);
        double ty = y ?? (Horizontal ? View.VerticalOffset : maxY);
        View.ChangeView(Math.Clamp(tx, 0, maxX), Math.Clamp(ty, 0, maxY), null, !animated);
    }
}

/// Path node: commands [0 x y] move, [1 x y] line, [2 c1x c1y c2x c2y x y] cubic, [3] close, in a square
/// `viewbox` (24 by default) scaled to fit and centred in the node.
sealed class PathView : Grid
{
    readonly Path shape = new()
    {
        StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round, StrokeLineJoin = PenLineJoin.Round,
        IsHitTestVisible = false,
    };
    List<double[]> cmds = new();
    double box = 24;
    public double StrokeWidth = 2;

    public PathView()
    {
        IsHitTestVisible = false;
        Children.Add(shape);
    }

    public void SetCommands(List<double[]> c) { cmds = c; Rebuild(); }
    public void SetBox(double b) { box = b > 0 ? b : 24; Rebuild(); }

    public void SetColors(uint? stroke, uint? fill)
    {
        shape.Stroke = stroke is uint s ? new SolidColorBrush(Colors.Of(s)) : null;
        shape.Fill = fill is uint f ? new SolidColorBrush(Colors.Of(f)) : null;
    }

    public void Rebuild()
    {
        double w = Parent is FrameworkElement p && !double.IsNaN(p.Width) ? p.Width : ActualWidth;
        double h = Parent is FrameworkElement q && !double.IsNaN(q.Height) ? q.Height : ActualHeight;
        double s = Math.Min(w, h) / box;
        if (!(s > 0)) { shape.Data = null; return; }
        shape.StrokeThickness = StrokeWidth * s;
        double ox = (w - box * s) / 2, oy = (h - box * s) / 2;
        Point Pt(double x, double y) => new(ox + x * s, oy + y * s);
        var geo = new PathGeometry();
        PathFigure? fig = null;
        foreach (var c in cmds)
        {
            if (c.Length == 0) continue;
            switch ((int)c[0])
            {
                case 0:
                    fig = new PathFigure { StartPoint = Pt(At(c, 1), At(c, 2)), IsFilled = true, IsClosed = false };
                    geo.Figures.Add(fig);
                    break;
                case 1:
                    fig ??= Start(geo);
                    fig.Segments.Add(new LineSegment { Point = Pt(At(c, 1), At(c, 2)) });
                    break;
                case 2:
                    fig ??= Start(geo);
                    fig.Segments.Add(new BezierSegment
                    {
                        Point1 = Pt(At(c, 1), At(c, 2)), Point2 = Pt(At(c, 3), At(c, 4)), Point3 = Pt(At(c, 5), At(c, 6)),
                    });
                    break;
                default:
                    if (fig != null) fig.IsClosed = true;
                    fig = null;
                    break;
            }
        }
        shape.Data = geo;
    }

    static double At(double[] c, int i) => i < c.Length ? c[i] : 0;

    static PathFigure Start(PathGeometry g)
    {
        var f = new PathFigure { StartPoint = new Point(0, 0), IsFilled = true };
        g.Figures.Add(f);
        return f;
    }
}

/// NavStack: screens are the children of its canvas (last = top). A push slides the new screen in from the right
/// over the previous one, which moves left by a quarter width; a pop slides the top screen out and keeps it until
/// that animation ends. Motion is a composition animation of Translation.X, so the layout engine keeps owning frames.
sealed class NavHost
{
    readonly Node nav;
    public readonly HashSet<Node> Lingering = new();
    public bool Animated = true;

    public NavHost(Node nav) { this.nav = nav; }

    List<Node> Live(IEnumerable<Node> screens)
    {
        var l = new List<Node>();
        foreach (var s in screens) if (!Lingering.Contains(s)) l.Add(s);
        return l;
    }

    public void Pushed(Node v, IEnumerable<Node> screens)
    {
        var l = Live(screens);
        int i = l.IndexOf(v);
        float w = (float)nav.Rect.Width;
        if (!Animated || w <= 0 || i <= 0) return;
        v.Tx = w;
        Slide(v, 0, 0.32);
        Slide(l[i - 1], -w * 0.25f, 0.32);
    }

    /// True when the screen stays until its exit animation ends; `done` then removes it.
    public bool Popped(Node v, IEnumerable<Node> screens, Action done)
    {
        float w = (float)nav.Rect.Width;
        if (!Animated || w <= 0 || v.Tx >= w * 0.99f) return false;
        Lingering.Add(v);
        Slide(v, w, 0.26, () => { Lingering.Remove(v); done(); });
        var l = Live(screens);
        if (l.Count > 0) Slide(l[^1], 0, 0.26);
        return true;
    }

    static void Slide(Node n, float to, double secs, Action? done = null)
    {
        ElementCompositionPreview.SetIsTranslationEnabled(n.Frame, true);
        var v = ElementCompositionPreview.GetElementVisual(n.Frame);
        var c = v.Compositor;
        var a = c.CreateScalarKeyFrameAnimation();
        var ease = c.CreateCubicBezierEasingFunction(new Vector2(0, 0), new Vector2(0.58f, 1));
        a.InsertKeyFrame(0, n.Tx);
        a.InsertKeyFrame(1, to, ease);
        a.Duration = TimeSpan.FromSeconds(secs);
        n.Tx = to;
        var batch = c.CreateScopedBatch(CompositionBatchTypes.Animation);
        v.StartAnimation("Translation.X", a);
        batch.End();
        if (done != null) batch.Completed += (_, _) => done();
    }
}
