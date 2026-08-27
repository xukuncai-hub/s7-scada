using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using Microsoft.Web.WebView2.Core;
using S7Scada.Models;
using S7Scada.Services;

namespace S7Scada.Views;

public partial class MainWindow : Window
{
    private readonly PlcService _plc;
    private readonly TagConfigService _configService;
    private readonly ScreenConfigService _screenConfig = new();
    private readonly List<TagConfig> _tags = [];

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
    };

    // 原生标题栏随主题配色（深色模式 / 标题栏背景与文字颜色）
    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int attrValue, int attributeSize);
    private const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;
    private const int DWMWA_CAPTION_COLOR = 35;
    private const int DWMWA_TEXT_COLOR = 36;

    public MainWindow(PlcService plc, TagConfigService configService)
    {
        _plc = plc;
        _configService = configService;
        InitializeComponent();
        SourceInitialized += (s, e) => SetTitlebarTheme(false); // 默认浅色，theme 消息会再设置
    }

    private void SetTitlebarTheme(bool dark)
    {
        var hwnd = new WindowInteropHelper(this).Handle;

        // 沉浸式深色标题栏（Win10 1809+）
        if (Environment.OSVersion.Version.Build >= 17763)
        {
            int darkMode = dark ? 1 : 0;
            DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ref darkMode, sizeof(int));
        }

        // Win11 专属：标题栏背景色 / 文字颜色与主题对齐（值格式为 0x00BBGGRR）
        if (Environment.OSVersion.Version.Build >= 22000)
        {
            int caption = dark ? 0x17110D : 0xFBF9F8; // #0d1117 / #f8f9fb
            int text = dark ? 0xF3EDE6 : 0x6A6057;    // #e6edf3 / #57606a
            DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR, ref caption, sizeof(int));
            DwmSetWindowAttribute(hwnd, DWMWA_TEXT_COLOR, ref text, sizeof(int));
        }
    }

    // ── Initialization ──────────────────────────────────────
    // Called from App.OnStartup after Show(). Full sequence:
    // load tags -> init WebView2 -> wait for page navigation (so the
    // JS message listener is registered) -> push the tag list.

    public async Task InitializeAsync()
    {
        // Load saved tags
        var tags = _configService.Load();
        _tags.Clear();
        _tags.AddRange(tags);
        _plc.SetTags([.. _tags]);

        await InitializeWebView();

        // Now the frontend is listening; push the initial tag list and screens.
        await PushTagsToJs();
        PushScreensToJs();
    }

    /// <summary>把保存的画面配置推给前端</summary>
    private void PushScreensToJs()
    {
        try
        {
            var raw = _screenConfig.Load();
            var screens = JsonDocument.Parse(raw).RootElement;
            SendToJs(new { type = "screensChanged", screens });
        }
        catch
        {
            SendToJs(new { type = "screensChanged", screens = Array.Empty<object>() });
        }
    }

    private async Task InitializeWebView()
    {
        var env = await CoreWebView2Environment.CreateAsync(
            null,
            Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "WebView2Data"));

        await WebView.EnsureCoreWebView2Async(env);

        // Handle messages from JS
        WebView.WebMessageReceived += OnWebMessageReceived;

        // Subscribe to PLC events
        _plc.Connected += () => Dispatcher.Invoke(() => OnPlcConnected());
        _plc.Disconnected += msg => Dispatcher.Invoke(() => OnPlcDisconnected(msg));
        _plc.ConnectionError += err => Dispatcher.Invoke(() => OnPlcError(err));
        _plc.PlcInfoReceived += info => Dispatcher.Invoke(() => OnPlcInfo(info));
        _plc.DataUpdated += results => Dispatcher.Invoke(() => OnDataUpdated(results));
        _plc.ScanTime += ms => Dispatcher.Invoke(() => OnScanTime(ms));

        // Navigate to the local HTML file and wait for it to finish loading
        // so that app.js (which registers the 'message' listener) is ready.
        var htmlPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "wwwroot", "index.html");
        var navigationDone = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        EventHandler<CoreWebView2NavigationCompletedEventArgs> onNav = (_, __) =>
            navigationDone.TrySetResult(true);
        WebView.CoreWebView2.NavigationCompleted += onNav;
        WebView.CoreWebView2.Navigate(new Uri(htmlPath).AbsoluteUri);
        await navigationDone.Task;
        WebView.CoreWebView2.NavigationCompleted -= onNav;
    }

    // ── PLC Event Handlers ──────────────────────────────────

    private void OnPlcConnected()
    {
        SendToJs(new { type = "connectionChanged", connected = true, text = "Connected", connecting = false });
    }

    private void OnPlcDisconnected(string msg)
    {
        SendToJs(new { type = "connectionChanged", connected = false, text = "Disconnected", connecting = false });
    }

    private void OnPlcError(string error)
    {
        // 单次尝试失败：提示一次，状态回到未连接，由用户手动重新点击"连接"
        SendToJs(new { type = "connectionChanged", connected = false, text = $"Connection failed: {error}", connecting = false });
        SendToJs(new { type = "error", text = $"Connection failed: {error}" });
    }

    private void OnPlcInfo(PlcInfo info)
    {
        SendToJs(new { type = "plcInfo", info });
    }

    private void OnDataUpdated(List<TagScanResult> results)
    {
        // 把扫描结果写回本地标签列表，这样后续 tagsChanged 重渲染
        // （切换扫描、增删改标签等）不会把已显示的值清成 "---"。
        foreach (var r in results)
        {
            if (r.Index < 0 || r.Index >= _tags.Count) continue;
            _tags[r.Index].Value = r.Value;
            _tags[r.Index].Quality = r.Quality;
            _tags[r.Index].Timestamp = r.Timestamp;
        }

        // Build a compact update array
        var updates = results.Select(r => new
        {
            index = r.Index,
            value = r.Value,
            quality = r.Quality.ToString(),
            timestamp = r.Timestamp
        }).ToList();

        SendToJs(new { type = "dataUpdated", results = updates });
    }

    private void OnScanTime(double ms)
    {
        SendToJs(new { type = "scanTime", ms });
    }

    // ── JS -> C# Message Handler ────────────────────────────

    private async void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        try
        {
            var json = e.WebMessageAsJson;
            // WebView2 wraps strings in quotes, unwrap if needed
            if (json.StartsWith('"') && json.EndsWith('"'))
                json = JsonSerializer.Deserialize<string>(json) ?? json;

            var msg = JsonSerializer.Deserialize<JsonElement>(json);

            if (!msg.TryGetProperty("action", out var actionProp))
                return;

            var action = actionProp.GetString();
            switch (action)
            {
                case "connect":
                    await HandleConnect(msg);
                    break;
                case "disconnect":
                    await HandleDisconnect();
                    break;
                case "addTag":
                    HandleAddTag(msg);
                    break;
                case "editTag":
                    HandleEditTag(msg);
                    break;
                case "deleteTag":
                    HandleDeleteTag(msg);
                    break;
                case "writeValue":
                    HandleWriteValue(msg);
                    break;
                case "saveConfig":
                    HandleSaveConfig();
                    break;
                case "loadConfig":
                    await HandleLoadConfig();
                    break;
                case "saveConfigAs":
                    HandleSaveConfigAs(msg);
                    break;
                case "toggleScan":
                    HandleToggleScan(msg);
                    break;
                case "refreshNow":
                    _plc.RefreshNow();
                    break;
                case "saveScreens":
                    HandleSaveScreens(msg);
                    break;
                case "theme":
                    HandleTheme(msg);
                    break;
            }
        }
        catch (Exception ex)
        {
            SendToJs(new { type = "error", text = ex.Message });
        }
    }

    // ── Command Handlers ────────────────────────────────────

    private async Task HandleConnect(JsonElement msg)
    {
        var ip = msg.GetProperty("ip").GetString() ?? "192.168.0.1";
        var rack = msg.GetProperty("rack").GetInt32();
        var slot = msg.GetProperty("slot").GetInt32();
        var scanInterval = msg.GetProperty("scanInterval").GetInt32();

        var cpuStr = msg.TryGetProperty("cpu", out var cpuProp) ? cpuProp.GetString() : "S71200";
        var cpu = Enum.TryParse<S7.Net.CpuType>(cpuStr, true, out var cpuType)
            ? cpuType
            : S7.Net.CpuType.S71200;

        _plc.SetConnection(ip, rack, slot, cpu);
        _plc.ScanInterval = scanInterval;
        _plc.SetTags([.. _tags]);
        SendToJs(new { type = "connectionChanged", connected = false, text = "Connecting...", connecting = true });
        await _plc.ConnectAsync();
    }

    private void HandleSaveScreens(JsonElement msg)
    {
        try
        {
            var raw = msg.GetProperty("screens").GetRawText();
            _screenConfig.Save(raw);
        }
        catch (Exception ex)
        {
            SendToJs(new { type = "error", text = $"保存画面失败: {ex.Message}" });
        }
    }

    private void HandleTheme(JsonElement msg)
    {
        var theme = msg.TryGetProperty("theme", out var t) ? t.GetString() : "light";
        bool dark = theme == "dark";
        Background = dark
            ? new SolidColorBrush(Color.FromRgb(0x0d, 0x11, 0x17))
            : new SolidColorBrush(Color.FromRgb(0xf8, 0xf9, 0xfb));
        SetTitlebarTheme(dark);
    }

    private async Task HandleDisconnect()
    {
        await _plc.DisconnectAsync();
    }

    private void HandleAddTag(JsonElement msg)
    {
        var tagProp = msg.GetProperty("tag");
        var tag = ParseTagFromJson(tagProp);
        if (tag == null) return;

        _tags.Add(tag);
        _plc.SetTags([.. _tags]);
        _ = PushTagsToJs();
    }

    private void HandleEditTag(JsonElement msg)
    {
        var index = msg.GetProperty("index").GetInt32();
        if (index < 0 || index >= _tags.Count) return;

        var tagProp = msg.GetProperty("tag");
        var tag = ParseTagFromJson(tagProp);
        if (tag == null) return;

        _tags[index] = tag;
        _plc.SetTags([.. _tags]);
        _ = PushTagsToJs();
    }

    private void HandleDeleteTag(JsonElement msg)
    {
        var index = msg.GetProperty("index").GetInt32();
        if (index < 0 || index >= _tags.Count) return;

        _tags.RemoveAt(index);
        _plc.SetTags([.. _tags]);
        _ = PushTagsToJs();
    }

    private void HandleWriteValue(JsonElement msg)
    {
        var index = msg.GetProperty("index").GetInt32();
        if (index < 0 || index >= _tags.Count) return;

        var tag = _tags[index];
        var valueProp = msg.GetProperty("value");

        object? value = tag.DataType switch
        {
            TagDataType.Bool => valueProp.GetBoolean(),
            TagDataType.Byte => (byte)valueProp.GetInt32(),
            TagDataType.Word => (ushort)valueProp.GetInt32(),
            TagDataType.DWord => (uint)valueProp.GetInt32(),
            TagDataType.Int => (short)valueProp.GetInt32(),
            TagDataType.DInt => valueProp.GetInt32(),
            TagDataType.Real => (float)valueProp.GetDouble(),
            _ => valueProp.GetInt32()
        };

        if (value == null) return;

        var (success, message) = _plc.WriteTag(tag, value);
        if (!success)
        {
            SendToJs(new { type = "error", text = $"{tag.Name}: {message}" });
        }
        else
        {
            SendToJs(new { type = "toast", text = $"{tag.Name}: write success", kind = "success" });
        }
    }

    private void HandleSaveConfig()
    {
        try
        {
            _configService.Save([.. _tags]);
            SendToJs(new { type = "toast", text = "Configuration saved", kind = "success" });
        }
        catch (Exception ex)
        {
            SendToJs(new { type = "error", text = $"Save failed: {ex.Message}" });
        }
    }

    private async Task HandleLoadConfig()
    {
        var dialog = new Microsoft.Win32.OpenFileDialog
        {
            Filter = "JSON files (*.json)|*.json|All files (*.*)|*.*"
        };

        if (dialog.ShowDialog() == true)
        {
            try
            {
                var tags = _configService.Load(dialog.FileName);
                _tags.Clear();
                _tags.AddRange(tags);
                _plc.SetTags([.. _tags]);
                await PushTagsToJs();
                SendToJs(new { type = "toast", text = $"Configuration loaded ({_tags.Count} tags)", kind = "success" });
            }
            catch (Exception ex)
            {
                SendToJs(new { type = "error", text = $"Load failed: {ex.Message}" });
            }
        }
    }

    private void HandleSaveConfigAs(JsonElement msg)
    {
        var path = msg.GetProperty("path").GetString();
        if (string.IsNullOrEmpty(path)) return;

        try
        {
            _configService.Save([.. _tags], path);
            SendToJs(new { type = "toast", text = $"Saved to: {path}", kind = "success" });
        }
        catch (Exception ex)
        {
            SendToJs(new { type = "error", text = $"Save failed: {ex.Message}" });
        }
    }

    private void HandleToggleScan(JsonElement msg)
    {
        var index = msg.GetProperty("index").GetInt32();
        if (index < 0 || index >= _tags.Count) return;

        _tags[index].ScanEnabled = !_tags[index].ScanEnabled;
        _plc.SetTags([.. _tags]);
        _ = PushTagsToJs();
    }

    // ── Helper: Parse TagConfig from JSON ───────────────────

    private static TagConfig? ParseTagFromJson(JsonElement prop)
    {
        var name = prop.GetProperty("name").GetString();
        var address = prop.GetProperty("address").GetString()?.ToUpper();
        if (string.IsNullOrWhiteSpace(name) || string.IsNullOrWhiteSpace(address))
            return null;

        var dataTypeStr = prop.GetProperty("dataType").GetString() ?? "Bool";
        var dataType = Enum.TryParse<TagDataType>(dataTypeStr, true, out var dt) ? dt : TagDataType.Bool;
        var group = prop.TryGetProperty("group", out var g) ? g.GetString() ?? "Default" : "Default";
        var comment = prop.TryGetProperty("comment", out var c) ? c.GetString() ?? "" : "";
        var scanEnabled = prop.TryGetProperty("scanEnabled", out var se) && se.GetBoolean();

        var tag = new TagConfig
        {
            Name = name,
            Address = address,
            DataType = dataType,
            Group = group,
            Comment = comment,
            ScanEnabled = scanEnabled
        };

        AddressParser.ParseToTag(address, tag);
        return tag;
    }

    // ── Helper: Push full tag list to JS ────────────────────

    private async Task PushTagsToJs()
    {
        var tagData = _tags.Select((t, i) => new
        {
            name = t.Name,
            address = t.Address,
            area = t.Area.ToString(),
            dataType = t.DataType.ToString(),
            dbNumber = t.DbNumber,
            byteOffset = t.ByteOffset,
            bitOffset = t.BitOffset,
            group = t.Group,
            comment = t.Comment,
            scanEnabled = t.ScanEnabled,
            value = t.Value,
            quality = t.Quality.ToString(),
            timestamp = t.Timestamp
        }).ToList();

        SendToJs(new { type = "tagsChanged", tags = tagData });
        await Task.CompletedTask;
    }

    // ── JS Interop Helpers ──────────────────────────────────

    /// <summary>
    /// Send a structured message to the JS frontend via PostWebMessageAsJson.
    /// This avoids string-eval'ing JS and eliminates all escaping issues.
    /// </summary>
    private void SendToJs(object payload)
    {
        try
        {
            if (WebView.CoreWebView2 != null)
                WebView.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(payload, JsonOpts));
        }
        catch { }
    }

    // ── Window Events ───────────────────────────────────────
    // 原生标题栏的 X 按钮 → 正常退出应用
}
