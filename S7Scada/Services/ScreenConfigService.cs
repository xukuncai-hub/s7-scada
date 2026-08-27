using System.IO;

namespace S7Scada.Services;

/// <summary>
/// 画面配置持久化。画面/组件结构完全由前端定义，
/// 这里只做 screens.json 的原始 JSON 读写（透传，不强类型建模）。
/// </summary>
public class ScreenConfigService
{
    private static readonly string DefaultConfigPath =
        Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "screens.json");

    public string Load(string? path = null)
    {
        path ??= DefaultConfigPath;
        return File.Exists(path) ? File.ReadAllText(path) : "[]";
    }

    public void Save(string json, string? path = null)
    {
        path ??= DefaultConfigPath;
        File.WriteAllText(path, json);
    }
}
