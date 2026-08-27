using System.Windows;
using S7Scada.Services;
using S7Scada.Views;

namespace S7Scada;

public partial class App : Application
{
    private PlcService? _plcService;

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        _plcService = new PlcService();
        var configService = new TagConfigService();

        var mainWindow = new MainWindow(_plcService, configService);
        mainWindow.Show();

        await mainWindow.InitializeAsync();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _plcService?.Dispose();
        base.OnExit(e);
    }
}
