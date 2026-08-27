using System.Text.RegularExpressions;
using S7Scada.Models;

namespace S7Scada.Services;

/// <summary>
/// S7 地址解析器 - 支持 S7-1200/1500 全部地址格式
/// </summary>
public static partial class AddressParser
{
    // DB 区: DB1.DBX0.0, DB1.DBW2, DB1.DBD4, DB1.DBB0
    [GeneratedRegex(@"^DB(\d+)\.(DB[WXDB]\d+)(?:\.(\d+))?$", RegexOptions.IgnoreCase)]
    private static partial Regex DbAddressRegex();

    // DB 简化: DB1
    [GeneratedRegex(@"^DB(\d+)$", RegexOptions.IgnoreCase)]
    private static partial Regex DbSimpleRegex();

    // 非DB区: M0.0, MW2, MD4, MB10, I0.0, Q0.0, T0, C0
    [GeneratedRegex(@"^([MIQTC])([WXDB])?(\d+)(?:\.(\d+))?$", RegexOptions.IgnoreCase)]
    private static partial Regex NonDbAddressRegex();

    // DB 类型后缀: DBX, DBB, DBW, DBD
    [GeneratedRegex(@"^DB([WXDB])(\d+)$", RegexOptions.IgnoreCase)]
    private static partial Regex DbTypeSuffixRegex();

    /// <summary>解析 S7 地址字符串</summary>
    public static ParsedAddress? Parse(string? address)
    {
        if (string.IsNullOrWhiteSpace(address)) return null;
        address = address.Trim().ToUpper();

        // DB 区地址
        var dbMatch = DbAddressRegex().Match(address);
        if (dbMatch.Success)
        {
            int dbNum = int.Parse(dbMatch.Groups[1].Value);
            string suffix = dbMatch.Groups[2].Value;
            int? bitPart = dbMatch.Groups[3].Success ? int.Parse(dbMatch.Groups[3].Value) : null;

            var typeMatch = DbTypeSuffixRegex().Match(suffix);
            if (typeMatch.Success)
            {
                char typeChar = typeMatch.Groups[1].Value[0];
                int offset = int.Parse(typeMatch.Groups[2].Value);

                return typeChar switch
                {
                    'X' => new ParsedAddress(Area.DB, TagDataType.Bool, dbNum, offset, bitPart ?? 0, address),
                    'B' => new ParsedAddress(Area.DB, TagDataType.Byte, dbNum, offset, 0, address),
                    'W' => new ParsedAddress(Area.DB, TagDataType.Word, dbNum, offset, 0, address),
                    'D' => new ParsedAddress(Area.DB, TagDataType.DWord, dbNum, offset, 0, address),
                    _ => null
                };
            }
        }

        // DB 简化格式
        var dbSimple = DbSimpleRegex().Match(address);
        if (dbSimple.Success)
        {
            return new ParsedAddress(Area.DB, TagDataType.Byte, int.Parse(dbSimple.Groups[1].Value), 0, 0, address);
        }

        // 非 DB 区
        var nonDb = NonDbAddressRegex().Match(address);
        if (nonDb.Success)
        {
            string areaPrefix = nonDb.Groups[1].Value;
            string? typeCharStr = nonDb.Groups[2].Success ? nonDb.Groups[2].Value : null;
            int offset = int.Parse(nonDb.Groups[3].Value);
            int? bitPart = nonDb.Groups[4].Success ? int.Parse(nonDb.Groups[4].Value) : null;

            Area area = AreaInfo.FromPrefix(areaPrefix);
            char? typeChar = typeCharStr?.Length > 0 ? typeCharStr[0] : null;

            // 没有 typeChar 但有 bitPart → Bool 位地址 (如 M0.0)
            if (typeChar == null && bitPart.HasValue)
                return new ParsedAddress(area, TagDataType.Bool, 0, offset, bitPart.Value, address);

            // 没有 typeChar 也没有 bitPart → 默认 Word (如 T0, C0)
            if (typeChar == null && !bitPart.HasValue)
                return new ParsedAddress(area, TagDataType.Word, 0, offset, 0, address);

            // 有 typeChar
            if (typeChar.HasValue)
            {
                return typeChar.Value switch
                {
                    'X' => new ParsedAddress(area, TagDataType.Bool, 0, offset, bitPart ?? 0, address),
                    'B' => new ParsedAddress(area, TagDataType.Byte, 0, offset, 0, address),
                    'W' => new ParsedAddress(area, TagDataType.Word, 0, offset, 0, address),
                    'D' => new ParsedAddress(area, TagDataType.DWord, 0, offset, 0, address),
                    _ => null
                };
            }
        }

        return null;
    }

    /// <summary>解析地址并填充 TagConfig 字段</summary>
    public static bool ParseToTag(string address, TagConfig tag)
    {
        var parsed = Parse(address);
        if (parsed == null) return false;

        tag.Area = parsed.Area;
        tag.DataType = parsed.DataType;
        tag.DbNumber = parsed.DbNumber;
        tag.ByteOffset = parsed.ByteOffset;
        tag.BitOffset = parsed.BitOffset;
        return true;
    }
}

/// <summary>解析后的地址结构</summary>
public record ParsedAddress(
    Area Area,
    TagDataType DataType,
    int DbNumber,
    int ByteOffset,
    int BitOffset,
    string Raw
);
