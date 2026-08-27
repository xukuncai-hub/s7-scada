using System.IO;
using System.Text.Json;
using S7Scada.Models;

namespace S7Scada.Services;

/// <summary>标签配置持久化服务</summary>
public class TagConfigService
{
    private static readonly string DefaultConfigPath =
        Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "s7_tags.json");

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
    };

    /// <summary>加载标签配置</summary>
    public List<TagConfig> Load(string? path = null)
    {
        path ??= DefaultConfigPath;
        if (!File.Exists(path))
            return CreatePresetTags();

        try
        {
            var json = File.ReadAllText(path);
            var items = JsonSerializer.Deserialize<List<TagConfigJson>>(json);
            if (items == null) return CreatePresetTags();

            return items.Select(ConvertFromJson).ToList();
        }
        catch
        {
            return CreatePresetTags();
        }
    }

    /// <summary>保存标签配置</summary>
    public void Save(List<TagConfig> tags, string? path = null)
    {
        path ??= DefaultConfigPath;
        var items = tags.Select(ConvertToJson).ToList();
        var json = JsonSerializer.Serialize(items, JsonOptions);
        File.WriteAllText(path, json);
    }

    /// <summary>创建预置示例标签</summary>
    public static List<TagConfig> CreatePresetTags()
    {
        var presets = new (string Name, string Addr, TagDataType Type, string Group)[]
        {
            ("急停信号",   "DB1.DBX0.0", TagDataType.Bool, "Alarms"),
            ("运行状态",   "M0.0",       TagDataType.Bool, "Digital Inputs"),
            ("温度值",     "DB1.DBW2",   TagDataType.Int,  "Analog Inputs"),
            ("压力值",     "DB1.DBD4",   TagDataType.Real, "Analog Inputs"),
            ("传感器输入", "I0.0",       TagDataType.Bool, "Digital Inputs"),
            ("产量计数",   "DB1.DBD8",   TagDataType.DInt, "Production Data"),
            ("电机速度",   "DB1.DBW12",  TagDataType.Word, "Parameters"),
            ("输出状态",   "Q0.0",       TagDataType.Bool, "Digital Outputs"),
        };

        return presets.Select(p =>
        {
            var tag = new TagConfig
            {
                Name = p.Name,
                Address = p.Addr,
                DataType = p.Type,
                Group = p.Group,
                ScanEnabled = true
            };
            AddressParser.ParseToTag(p.Addr, tag);
            return tag;
        }).ToList();
    }

    private static TagConfig ConvertFromJson(TagConfigJson json)
    {
        var tag = new TagConfig
        {
            Name = json.Name,
            Address = json.Address,
            DbNumber = json.DbNumber,
            ByteOffset = json.ByteOffset,
            BitOffset = json.BitOffset,
            Group = json.Group,
            ScanEnabled = json.ScanEnabled,
            Comment = json.Comment
        };
        tag.Area = AreaInfo.FromPrefix(json.Area);
        tag.DataType = Enum.TryParse<TagDataType>(json.DataType, true, out var dt) ? dt : TagDataType.Bool;
        return tag;
    }

    private static TagConfigJson ConvertToJson(TagConfig tag) => new()
    {
        Name = tag.Name,
        Address = tag.Address,
        Area = tag.Area.Prefix(),
        DataType = tag.DataType.ToString(),
        DbNumber = tag.DbNumber,
        ByteOffset = tag.ByteOffset,
        BitOffset = tag.BitOffset,
        Group = tag.Group,
        ScanEnabled = tag.ScanEnabled,
        Comment = tag.Comment
    };
}
