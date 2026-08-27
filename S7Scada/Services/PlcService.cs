using System.Diagnostics;
using System.Text.RegularExpressions;
using S7.Net;
using S7Scada.Models;

namespace S7Scada.Services;

/// <summary>
/// PLC 通信服务 - 基于 S7.Net
/// 负责连接管理、批量读取、数据解析、断线重连
/// </summary>
public partial class PlcService : IDisposable
{
    private Plc? _plc;
    private readonly object _lock = new();
    private readonly object _commLock = new(); // 串行化 PLC 通信（扫描循环与手动刷新）
    private CancellationTokenSource? _cts;
    private Task? _scanTask;
    private bool _connected;

    // 事件
    public event Action? Connected;
    public event Action<string>? Disconnected;
    public event Action<string>? ConnectionError;
    public event Action<PlcInfo>? PlcInfoReceived;
    public event Action<List<TagScanResult>>? DataUpdated;
    public event Action<double>? ScanTime;

    // 属性
    public bool IsConnected => _connected;
    public string Ip { get; private set; } = "192.168.0.1";
    public CpuType Cpu { get; private set; } = CpuType.S71200;
    public int Rack { get; private set; }
    public int Slot { get; private set; } = 1;
    public int ScanInterval { get; set; } = 100;

    private List<TagConfig> _tags = [];

    // MLFB 解析
    [GeneratedRegex(@"6ES7\s*(\d)(\d{2})", RegexOptions.IgnoreCase)]
    private static partial Regex MlfbRegex();

    [GeneratedRegex(@"6ES7\d{3}")]
    private static partial Regex MlfbPrefixRegex();

    [GeneratedRegex(@"V(\d+)\.(\d+)")]
    private static partial Regex FirmwareRegex();

    [GeneratedRegex(@"(6ES7)(\d)(\d{2})(.{5})(.{4})")]
    private static partial Regex MlfbFormatRegex();

    /// <summary>设置连接参数</summary>
    public void SetConnection(string ip, int rack = 0, int slot = 1, CpuType cpu = CpuType.S71200)
    {
        Ip = ip;
        Rack = rack;
        Slot = slot;
        Cpu = cpu;
    }

    /// <summary>设置要扫描的标签列表</summary>
    public void SetTags(List<TagConfig> tags)
    {
        lock (_lock)
        {
            _tags = [.. tags];
        }
    }

    /// <summary>连接 PLC 并启动扫描</summary>
    public async Task ConnectAsync()
    {
        if (_connected) return;

        _cts?.Dispose();
        _cts = new CancellationTokenSource();
        _scanTask = Task.Run(() => ScanLoopAsync(_cts.Token));
        await Task.CompletedTask;
    }

    /// <summary>断开 PLC</summary>
    public async Task DisconnectAsync()
    {
        _cts?.Cancel();
        if (_scanTask != null)
        {
            try { await _scanTask; } catch { }
        }
        DisconnectInternal();
    }

    /// <summary>立即手动刷新一次全部标签（不改变持续扫描的状态）</summary>
    public void RefreshNow()
    {
        if (!_connected || _plc == null) return;

        _ = Task.Run(() =>
        {
            List<TagConfig> snapshot;
            lock (_lock) { snapshot = [.. _tags]; }
            if (snapshot.Count == 0) return;

            var results = ScanTags(snapshot);
            if (results.Count > 0)
                DataUpdated?.Invoke(results);
        });
    }

    /// <summary>写入标签值到 PLC</summary>
    public (bool Success, string Message) WriteTag(TagConfig tag, object value)
    {
        if (!_connected || _plc == null)
            return (false, "PLC 未连接");

        try
        {
            if (tag.DataType == TagDataType.Bool)
                return WriteBool(tag, value);

            byte[]? data = ValueToBytes(value, tag.DataType);
            if (data == null) return (false, "值转换失败");

            if (tag.Area == Area.DB)
                _plc.WriteBytes(S7.Net.DataType.DataBlock, (ushort)tag.DbNumber, tag.ByteOffset, data);
            else
                _plc.WriteBytes(tag.Area.ToS7NetArea(), (ushort)tag.DbNumber, tag.ByteOffset, data);

            return (true, "写入成功");
        }
        catch (Exception ex)
        {
            return (false, ex.Message);
        }
    }

    public void Dispose()
    {
        _cts?.Cancel();
        DisconnectInternal();
        GC.SuppressFinalize(this);
    }

    // ── 私有方法 ────────────────────────────────────────

    private async Task ScanLoopAsync(CancellationToken ct)
    {
        try
        {
            // 单次连接尝试：失败即停止，由用户手动重新点击"连接"
            if (!await TryConnectOnceAsync(ct))
            {
                DisconnectInternal();
                return;
            }

            // 连接成功后持续扫描；连接断开时停止，不做自动重连
            while (!ct.IsCancellationRequested && _connected)
            {
                List<TagConfig> snapshot;
                lock (_lock) { snapshot = [.. _tags]; }

                if (snapshot.Count > 0)
                {
                    var sw = Stopwatch.StartNew();
                    var results = ScanTags(snapshot);
                    sw.Stop();
                    ScanTime?.Invoke(sw.Elapsed.TotalMilliseconds);

                    if (results.Count > 0)
                        DataUpdated?.Invoke(results);
                }

                // 连接已断开则停止扫描（不自动重连）
                if (_plc == null || !_plc.IsConnected)
                {
                    Disconnected?.Invoke("连接已断开");
                    break;
                }

                await Task.Delay(ScanInterval, ct);
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception ex)
        {
            Debug.WriteLine($"PLC error: {ex.Message}");
        }

        DisconnectInternal();
    }

    private void DisconnectInternal()
    {
        _connected = false;
        try { _plc?.Close(); } catch { }
        _plc = null;
        Disconnected?.Invoke("");
    }

    /// <summary>
    /// 尝试连接一次。Open() 是阻塞调用，这里给它包一层 5 秒超时，
    /// 避免 IP 不可达时界面一直卡在 "Connecting..." 等操作系统级的 TCP 超时（可达 20 秒+）。
    /// 返回 true 表示连接成功。
    /// </summary>
    private async Task<bool> TryConnectOnceAsync(CancellationToken ct)
    {
        const int connectTimeoutMs = 5000;

        try
        {
            _plc = new Plc(Cpu, Ip, (short)Rack, (short)Slot)
            {
                ReadTimeout = 5000,
                WriteTimeout = 5000
            };

            var openTask = Task.Run(() => _plc.Open(), ct);
            var done = await Task.WhenAny(openTask, Task.Delay(connectTimeoutMs, ct));

            if (done == openTask)
            {
                await openTask; // rethrow if Open() failed
                _connected = true;
                Connected?.Invoke();

                // 异步获取 PLC 信息
                _ = Task.Run(() => FetchPlcInfo(), ct);
                return true;
            }

            // 连接超时或用户已取消（取消时不上报错误）
            try { _plc.Close(); } catch { }
            _plc = null;
            if (!ct.IsCancellationRequested)
                ConnectionError?.Invoke($"连接超时（{connectTimeoutMs / 1000}s 内无响应）");
            return false;
        }
        catch (Exception ex)
        {
            try { _plc?.Close(); } catch { }
            _plc = null;
            if (!ct.IsCancellationRequested)
                ConnectionError?.Invoke(ex.Message);
            return false;
        }
    }

    // ── 批量扫描 ────────────────────────────────────────

    private List<TagScanResult> ScanTags(List<TagConfig> tags)
    {
        // 按 (area, db_number) 分组
        var groups = tags
            .Select((tag, idx) => (idx, tag))
            .Where(t => t.tag.ScanEnabled)
            .GroupBy(t => (t.tag.Area, t.tag.DbNumber));

        var results = new List<TagScanResult>();
        string timestamp = DateTime.Now.ToString("HH:mm:ss.fff");

        // 与手动刷新共用串行锁，避免并发读写 S7.Net 的连接
        lock (_commLock)
        {
            foreach (var group in groups)
            {
                try
                {
                    ReadGroup(group.Key.Area, group.Key.DbNumber, group.ToList(), results, timestamp);
                }
                catch (Exception ex)
                {
                    string errDesc = group.Key.Area == Area.DB
                        ? $"DB{group.Key.DbNumber}"
                        : $"{group.Key.Area.Prefix()} area";
                    string fullErr = $"[{errDesc}] {ex.Message}";
                    foreach (var (idx, tag) in group)
                        results.Add(new TagScanResult(idx, null, TagQuality.Bad, timestamp, fullErr));
                }
            }
        }

        return results;
    }

    private void ReadGroup(Area area, int dbNum,
        List<(int idx, TagConfig tag)> tagList,
        List<TagScanResult> results, string timestamp)
    {
        var enabled = tagList.Where(t => t.tag.ScanEnabled).ToList();
        if (enabled.Count == 0 || _plc == null) return;

        int minOffset = enabled.Min(t => t.tag.ByteOffset);
        int maxOffset = enabled.Max(t => t.tag.ByteOffset + t.tag.ByteLength);
        int totalSize = Math.Max(maxOffset - minOffset, 4);

        byte[]? rawData = ReadArea(area, dbNum, minOffset, totalSize);
        if (rawData == null || rawData.Length == 0)
            throw new Exception("返回数据为空");

        foreach (var (idx, tag) in enabled)
        {
            int localOffset = tag.ByteOffset - minOffset;
            int endOffset = localOffset + tag.ByteLength;

            if (endOffset > rawData.Length)
            {
                results.Add(new TagScanResult(idx, null, TagQuality.Bad, timestamp,
                    $"偏移超出数据范围 (need {endOffset}, got {rawData.Length})"));
                continue;
            }

            var tagData = rawData[localOffset..endOffset];
            object? value = ParseBytes(tagData, tag.DataType, tag.BitOffset);
            var quality = value != null ? TagQuality.Good : TagQuality.Bad;
            string err = value != null ? "" : "数据解析失败";
            results.Add(new TagScanResult(idx, value, quality, timestamp, err));
        }
    }

    private byte[]? ReadArea(Area area, int dbNum, int start, int size)
    {
        if (_plc == null) return null;

        return area switch
        {
            Area.DB => _plc.ReadBytes(S7.Net.DataType.DataBlock, (ushort)dbNum, start, size),
            _ => _plc.ReadBytes(area.ToS7NetArea(), (ushort)dbNum, start, size)
        };
    }

    // ── 写入操作 ────────────────────────────────────────

    private (bool, string) WriteBool(TagConfig tag, object value)
    {
        try
        {
            if (_plc == null) return (false, "PLC 未连接");

            // 读-改-写
            byte[] raw = tag.Area == Area.DB
                ? _plc.ReadBytes(S7.Net.DataType.DataBlock, (ushort)tag.DbNumber, tag.ByteOffset, 1)
                : _plc.ReadBytes(tag.Area.ToS7NetArea(), (ushort)tag.DbNumber, tag.ByteOffset, 1);

            if (raw == null || raw.Length == 0)
                return (false, "读取当前字节失败");

            byte currentByte = raw[0];
            bool boolVal = Convert.ToBoolean(value);
            byte newByte = boolVal
                ? (byte)(currentByte | (1 << tag.BitOffset))
                : (byte)(currentByte & ~(1 << tag.BitOffset));

            byte[] writeData = [newByte];
            if (tag.Area == Area.DB)
                _plc.WriteBytes(S7.Net.DataType.DataBlock, (ushort)tag.DbNumber, tag.ByteOffset, writeData);
            else
                _plc.WriteBytes(tag.Area.ToS7NetArea(), (ushort)tag.DbNumber, tag.ByteOffset, writeData);

            return (true, "写入成功");
        }
        catch (Exception ex)
        {
            return (false, ex.Message);
        }
    }

    // ── PLC 信息识别 ────────────────────────────────────

    private void FetchPlcInfo()
    {
        var info = new PlcInfo();
        try
        {
            if (_plc == null) return;

            // S7netplus 0.20 does not expose ReadSZL; fall back to a default name
            info.Module = Cpu switch
            {
                CpuType.S71200 => "S7-1200",
                CpuType.S71500 => "S7-1500",
                CpuType.S7300 => "S7-300",
                CpuType.S7400 => "S7-400",
                _ => "S7 PLC"
            };

            PlcInfoReceived?.Invoke(info);
        }
        catch
        {
            info.Module = "S7 PLC";
            PlcInfoReceived?.Invoke(info);
        }
    }

    private void ParseSzlData(byte[] data, PlcInfo info)
    {
        try
        {
            // 尝试从数据中提取 ASCII 字符串
            string text = System.Text.Encoding.ASCII.GetString(data);
            string clean = Regex.Replace(text, @"[^\x20-\x7E]", "");

            // 查找 MLFB 订货号 (6ES7...)
            var mlfbMatch = Regex.Match(clean, @"6ES7[\d\w\-]{10,20}");
            if (mlfbMatch.Success)
            {
                info.OrderCode = mlfbMatch.Value;
                info.Module = MlfbToName(mlfbMatch.Value);
            }

            // 查找固件版本
            var fwMatch = FirmwareRegex().Match(clean);
            if (fwMatch.Success)
                info.FirmwareVersion = fwMatch.Value;

            // 查找序列号
            var segments = text.Split('\0', StringSplitOptions.RemoveEmptyEntries);
            foreach (var seg in segments)
            {
                string s = seg.Trim();
                if (Regex.IsMatch(s, @"^[A-Z0-9]{6,24}$") && !s.Contains("6ES7"))
                {
                    info.SerialNumber = s;
                    break;
                }
            }
        }
        catch { }
    }

    private static string MlfbToName(string mlfb)
    {
        var m = MlfbRegex().Match(mlfb.Replace("-", "").Replace(" ", ""));
        if (m.Success)
        {
            string familyNum = m.Groups[1].Value;
            string model = m.Groups[2].Value;
            return familyNum is "2" or "5"
                ? $"S7-1{familyNum}{model}"
                : $"S7-{familyNum}{model}";
        }
        return mlfb;
    }

    // ── 字节解析 ────────────────────────────────────────

    private static object? ParseBytes(byte[] data, TagDataType dataType, int bitOffset = 0)
    {
        try
        {
            return dataType switch
            {
                TagDataType.Bool when data.Length > 0 => (data[0] & (1 << bitOffset)) != 0,
                TagDataType.Byte when data.Length > 0 => data[0],
                TagDataType.Word when data.Length >= 2 => BitConverter.ToUInt16(data[..2].Reverse().ToArray()),
                TagDataType.Int when data.Length >= 2 => BitConverter.ToInt16(data[..2].Reverse().ToArray()),
                TagDataType.DWord when data.Length >= 4 => BitConverter.ToUInt32(data[..4].Reverse().ToArray()),
                TagDataType.DInt when data.Length >= 4 => BitConverter.ToInt32(data[..4].Reverse().ToArray()),
                TagDataType.Real when data.Length >= 4 => Math.Round(
                    BitConverter.ToSingle(data[..4].Reverse().ToArray()), 6),
                _ => null
            };
        }
        catch { return null; }
    }

    private static byte[]? ValueToBytes(object value, TagDataType dataType)
    {
        try
        {
            return dataType switch
            {
                TagDataType.Byte => [(byte)(Convert.ToByte(value) & 0xFF)],
                TagDataType.Word => BitConverter.GetBytes((ushort)(Convert.ToUInt16(value) & 0xFFFF)).Reverse().ToArray(),
                TagDataType.Int => BitConverter.GetBytes(Convert.ToInt16(value)).Reverse().ToArray(),
                TagDataType.DWord => BitConverter.GetBytes((uint)(Convert.ToUInt32(value) & 0xFFFFFFFF)).Reverse().ToArray(),
                TagDataType.DInt => BitConverter.GetBytes(Convert.ToInt32(value)).Reverse().ToArray(),
                TagDataType.Real => BitConverter.GetBytes(Convert.ToSingle(value)).Reverse().ToArray(),
                _ => null
            };
        }
        catch { return null; }
    }
}
