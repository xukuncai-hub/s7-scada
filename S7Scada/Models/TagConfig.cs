using System.Text.Json.Serialization;

namespace S7Scada.Models;

/// <summary>S7 数据类型</summary>
public enum TagDataType
{
    Bool, Byte, Word, DWord, Int, DInt, Real
}

/// <summary>标签数据质量</summary>
public enum TagQuality
{
    Good, Bad, Unknown
}

/// <summary>S7 内存区域</summary>
public enum Area
{
    DB, M, I, Q, T, C
}

/// <summary>区域信息扩展</summary>
public static class AreaInfo
{
    public static string Prefix(this Area area) => area switch
    {
        Area.DB => "DB",
        Area.M => "M",
        Area.I => "I",
        Area.Q => "Q",
        Area.T => "T",
        Area.C => "C",
        _ => "?"
    };

    /// <summary>S7.Net Area 映射</summary>
    public static S7.Net.DataType ToS7NetArea(this Area area) => area switch
    {
        Area.DB => S7.Net.DataType.DataBlock,
        Area.M => S7.Net.DataType.Memory,
        Area.I => S7.Net.DataType.Input,
        Area.Q => S7.Net.DataType.Output,
        Area.T => S7.Net.DataType.Timer,
        Area.C => S7.Net.DataType.Counter,
        _ => S7.Net.DataType.Memory
    };

    public static int ByteSize(this TagDataType dt) => dt switch
    {
        TagDataType.Bool => 1,
        TagDataType.Byte => 1,
        TagDataType.Word => 2,
        TagDataType.Int => 2,
        TagDataType.DWord => 4,
        TagDataType.DInt => 4,
        TagDataType.Real => 4,
        _ => 1
    };

    public static Area FromPrefix(string prefix) => prefix?.ToUpper() switch
    {
        "DB" => Area.DB,
        "M" => Area.M,
        "I" => Area.I,
        "Q" => Area.Q,
        "T" => Area.T,
        "C" => Area.C,
        _ => Area.M
    };
}

/// <summary>单个标签的完整配置</summary>
public class TagConfig
{
    public string Name { get; set; } = "";
    public string Address { get; set; } = "";
    public Area Area { get; set; } = Area.M;
    public TagDataType DataType { get; set; } = TagDataType.Bool;
    public int DbNumber { get; set; }
    public int ByteOffset { get; set; }
    public int BitOffset { get; set; }
    public string Group { get; set; } = "Default";
    public bool ScanEnabled { get; set; } = true;
    public string Comment { get; set; } = "";

    // 运行时数据（不序列化）
    [JsonIgnore] public object? Value { get; set; }
    [JsonIgnore] public TagQuality Quality { get; set; } = TagQuality.Unknown;
    [JsonIgnore] public string Timestamp { get; set; } = "";

    [JsonIgnore] public int ByteLength => DataType.ByteSize();

    [JsonIgnore] public string DisplayName => $"{Name} ({Address})";
}

/// <summary>标签扫描结果</summary>
public record TagScanResult(
    int Index,
    object? Value,
    TagQuality Quality,
    string Timestamp,
    string ErrorMessage = ""
);

/// <summary>标签配置 JSON 序列化模型</summary>
public class TagConfigJson
{
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("address")] public string Address { get; set; } = "";
    [JsonPropertyName("area")] public string Area { get; set; } = "M";
    [JsonPropertyName("data_type")] public string DataType { get; set; } = "Bool";
    [JsonPropertyName("db_number")] public int DbNumber { get; set; }
    [JsonPropertyName("byte_offset")] public int ByteOffset { get; set; }
    [JsonPropertyName("bit_offset")] public int BitOffset { get; set; }
    [JsonPropertyName("group")] public string Group { get; set; } = "Default";
    [JsonPropertyName("scan_enabled")] public bool ScanEnabled { get; set; } = true;
    [JsonPropertyName("comment")] public string Comment { get; set; } = "";
}
