namespace S7Scada.Models;

/// <summary>PLC 设备信息</summary>
public class PlcInfo
{
    public string Module { get; set; } = "";
    public string FirmwareVersion { get; set; } = "";
    public string SerialNumber { get; set; } = "";
    public string OrderCode { get; set; } = "";

    public string DisplayText
    {
        get
        {
            var parts = new List<string>();
            if (!string.IsNullOrEmpty(Module)) parts.Add(Module);
            if (!string.IsNullOrEmpty(FirmwareVersion)) parts.Add($"FW:{FirmwareVersion}");
            return string.Join(" | ", parts);
        }
    }
}
