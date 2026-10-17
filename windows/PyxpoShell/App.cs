using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using System.Threading;
using Microsoft.UI;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.XamlTypeInfo;
using Windows.Foundation;
using Windows.Graphics;
using Windows.System;
using Windows.UI.ViewManagement;

namespace Pyxpo;

public static class Program
{
    [STAThread]
    static int Main()
    {
        WinRT.ComWrappersSupport.InitializeComWrappers();
        Application.Start(p =>
        {
            SynchronizationContext.SetSynchronizationContext(
                new DispatcherQueueSynchronizationContext(Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread()));
            _ = new App();
        });
        // The Python thread is not a .NET thread: end the process with the window.
        Environment.Exit(0);
        return 0;
    }
}

/// XAML-less application: no App.xaml, so the control templates come from XamlControlsResources added in code,
/// and type lookups go to the WinUI controls' metadata provider.
public sealed class App : Application, IXamlMetadataProvider
{
    readonly XamlControlsXamlMetaDataProvider provider = new();
    MainWindow? window;

    public App()
    {
        UnhandledException += (_, e) =>
        {
            Console.Error.WriteLine("pyxpo: unhandled " + e.Exception);
            e.Handled = true;
        };
    }

    public IXamlType GetXamlType(Type type) => provider.GetXamlType(type);
    public IXamlType GetXamlType(string fullName) => provider.GetXamlType(fullName);
    public XmlnsDefinition[] GetXmlnsDefinitions() => provider.GetXmlnsDefinitions();

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        Resources.MergedDictionaries.Add(new XamlControlsResources());
        window = new MainWindow();
        window.Activate();
    }
}

sealed class MainWindow : Window
{
    static readonly string ExeDir = AppContext.BaseDirectory;
    readonly AppConfig cfg = AppConfig.Load(ExeDir);
    readonly Grid host = new();
    readonly UISettings settings = new();
    readonly Runtime rt;
    bool started;

    [DllImport("user32")] static extern uint GetDpiForWindow(IntPtr hwnd);

    public MainWindow()
    {
        Title = cfg.Title;
        OpApplier.FontScale = settings.TextScaleFactor;
        if (cfg.Style == "light") host.RequestedTheme = ElementTheme.Light;
        else if (cfg.Style == "dark") host.RequestedTheme = ElementTheme.Dark;

        double dpi = GetDpiForWindow(WinRT.Interop.WindowNative.GetWindowHandle(this)) / 96.0;
        if (dpi <= 0) dpi = 1;
        AppWindow.Resize(new SizeInt32((int)(cfg.Width * dpi), (int)(cfg.Height * dpi)));
        var exeIcon = Path.Combine(ExeDir, "app.ico");
        if (File.Exists(exeIcon)) AppWindow.SetIcon(exeIcon);

        Native.Load(ExeDir);
        rt = new Runtime(DispatcherQueue);
        var app = rt.Applier;
        app.EnvSource = () => Env(false);
        host.Children.Add(app.View);
        Content = host;
        PaintBackground();

        host.Loaded += (_, _) =>
        {
            if (started) return;
            started = true;
            rt.Start(ExeDir, cfg.Module, Env(true));
            host.XamlRoot.Changed += (_, _) => app.ConfigChanged();
        };
        host.ActualThemeChanged += (_, _) => { PaintBackground(); app.ConfigChanged(); };
        settings.TextScaleFactorChanged += (_, _) => DispatcherQueue.TryEnqueue(() =>
        {
            OpApplier.FontScale = settings.TextScaleFactor;
            app.ConfigChanged();
        });

        // Escape and the mouse back button are the hardware back button; Ctrl+R reloads in dev.
        var back = new KeyboardAccelerator { Key = VirtualKey.Escape };
        back.Invoked += (_, e) => e.Handled = app.HardwareBack();
        var reload = new KeyboardAccelerator { Key = VirtualKey.R, Modifiers = VirtualKeyModifiers.Control };
        reload.Invoked += (_, e) => { e.Handled = true; app.DevReload(); };
        host.KeyboardAccelerators.Add(back);
        host.KeyboardAccelerators.Add(reload);
        host.KeyboardAcceleratorPlacementMode = KeyboardAcceleratorPlacementMode.Hidden;
        // R twice outside a text field reloads too, as in React Native.
        long lastR = 0;
        host.KeyDown += (_, e) =>
        {
            if (e.Key != VirtualKey.R || e.KeyStatus.WasKeyDown || e.OriginalSource is TextBox || e.OriginalSource is PasswordBox)
                return;
            if (Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(VirtualKey.Control)
                    .HasFlag(Windows.UI.Core.CoreVirtualKeyStates.Down))
                return;  // Ctrl+R is the accelerator above
            long now = Environment.TickCount64;
            if (now - lastR < 800) { lastR = 0; e.Handled = true; app.DevReload(); }
            else lastR = now;
        };
        host.AddHandler(UIElement.PointerPressedEvent, new PointerEventHandler((_, e) =>
        {
            if (e.GetCurrentPoint(host).Properties.IsXButton1Pressed && app.HardwareBack()) e.Handled = true;
        }), true);

        Activated += (_, e) => app.AppState(e.WindowActivationState == WindowActivationState.Deactivated ? "inactive" : "active");
        VisibilityChanged += (_, e) => app.AppState(e.Visible ? "active" : "background");

        Runtime.StartSnapshotHook(DispatcherQueue, () => host);
    }

    void PaintBackground()
    {
        bool dark = host.ActualTheme == ElementTheme.Dark;
        host.Background = new SolidColorBrush(Colors.Of(cfg.Background ?? (dark ? 0xFF000000u : 0xFFFFFFFFu)));
    }

    JsonObject Env(bool startup)
    {
        double scale = host.XamlRoot?.RasterizationScale
                       ?? GetDpiForWindow(WinRT.Interop.WindowNative.GetWindowHandle(this)) / 96.0;
        if (scale <= 0) scale = 1;
        var win = rt.Applier.RootSize;
        if (win.Width <= 0) win = new Size(host.ActualWidth > 0 ? host.ActualWidth : cfg.Width,
                                           host.ActualHeight > 0 ? host.ActualHeight : cfg.Height);
        var area = DisplayArea.GetFromWindowId(AppWindow.Id, DisplayAreaFallback.Primary).OuterBounds;
        var screen = new Size(area.Width / scale, area.Height / scale);
        return OpApplier.EnvJson(win, screen, scale, host.ActualTheme == ElementTheme.Dark, startup);
    }
}
