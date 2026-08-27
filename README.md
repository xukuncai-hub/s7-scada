# S7 SCADA 上位机

基于 **C# WPF + WebView2** 的西门子 S7 上位机监控软件，用于 PLC 标签的实时监控、数据查看与画面组态。

前端使用 HTML/CSS/JS 构建界面，通过 WebView2 承载，通信层使用 **S7netplus** 与西门子 S7-1200/1500/300/400 通信。

## ✨ 功能特性

- **S7 通信**
  - 支持 S7-1200 / 1500 / 300 / 400（可切换 CPU 型号）
  - 地址区：DB、M、I、Q、T、C
  - 地址解析：`DB1.DBW2`、`M0.0`、`DB1.DBD4` 等格式
  - 批量按区读取、断线检测、读写超时保护（5s）
- **标签管理**
  - 增删改、启停单个标签扫描、分组
  - 配置保存/加载（`s7_tags.json`），含预置示例标签
  - 搜索 + 分组筛选
- **实时数据**
  - 数值表格 + 仪表卡片双视图，双击/右键写入值
  - 扫描间隔可调（默认 100ms），支持手动立即刷新
  - 连接状态反馈（连接中/失败原因/超时）
- **画面编辑器（HMI 组态）**
  - 多画面自由添加/切换/重命名/删除
  - 组件：数值显示、指示灯、文本
  - 画布上自由拖拽摆放、缩放
  - 组件绑定标签后实时刷新，布局自动保存（`screens.json`）
- **界面**
  - 明/暗主题切换，标题栏随主题配色
  - 原生窗口动画（最小化/最大化/还原）
  - 响应式布局，侧边栏可折叠

## 📦 运行要求

| 平台 | Windows 10 / 11（x64） |
|------|------------------------|
| 运行时 | 无需 .NET（分发包自包含）；源码运行需要 .NET SDK 10 |
| WebView2 | 需要 WebView2 运行时（Win11 自带，Win10 一般已预装） |

## 🚀 快速开始

### 方式一：直接下载（推荐）
从 [Releases](https://github.com/xukuncai-hub/s7-scada/releases) 下载 `S7Scada-win-x64.zip`，解压后双击 `S7Scada.exe` 即可运行。

### 方式二：源码构建
```bash
# 需要 .NET SDK 10 + Windows
dotnet build S7Scada/S7Scada.csproj -c Release
# 运行
./S7Scada/bin/Release/net10.0-windows/S7Scada.exe
```

### 发布单文件 exe（分发包）
```bash
dotnet publish S7Scada/S7Scada.csproj -c Release -r win-x64 --self-contained true \
  -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true \
  -p:DebugType=None -p:DebugSymbols=false -o publish
```
产物：`publish/S7Scada.exe`（自包含）+ `publish/wwwroot/`（前端资源，必须与 exe 同目录）。

## 🖥️ 使用说明

### 1. 连接 PLC
1. 左侧填 **IP 地址**（如 `192.168.0.1`），选择 **CPU 型号**
2. Rack 0 / Slot 1（S7-1200/1500 默认），扫描间隔默认 100ms
3. 点击 **Connect**。连接失败会提示原因，手动重试即可

> **TIA 工程要求**：DB 需关闭"优化的块访问"；PLC 需开启 PUT/GET 通信。

### 2. 添加标签
- 工具栏 **Add Tag**，填写名称 + 地址（如 `DB1.DBW2`），地址自动解析
- 支持类型：Bool / Byte / Word / DWord / Int / DInt / Real
- **Ctrl+S** 保存配置，**Ctrl+N** 添加标签，**Ctrl+B** 折叠侧边栏

### 3. 画面编辑器
1. 工具栏切到 **「画面」**
2. 点 **+ 画面** 添加画面，顶部 tab 切换（双击重命名）
3. 点 **数值 / 指示灯 / 文本** 添加组件
4. 拖拽组件摆放，拖右下角缩放；选中后在上方属性栏绑定标签、改文字/字号
5. 布局自动保存，重启后保留

### 4. PLCSIM 仿真
- **S7-PLCSIM（基础）**：IP 填 `127.0.0.1`
- **S7-PLCSIM Advanced**：启用 `PLCSIM Virtual Eth. Adapter`，填实例 IP；需先把实例设为 RUN 并下载程序

## 📁 项目结构

```
S7Scada/
├── App.xaml(.cs)               # 入口
├── Views/MainWindow.xaml(.cs)  # 主窗口 + JS/C# 消息桥
├── Services/
│   ├── PlcService.cs           # PLC 通信（连接/扫描/读写）
│   ├── AddressParser.cs        # S7 地址解析
│   ├── TagConfigService.cs     # 标签配置持久化
│   └── ScreenConfigService.cs  # 画面配置持久化
├── Models/                     # PlcInfo / TagConfig
└── wwwroot/                    # 前端（index.html / app.js / style.css）
```

## ⚙️ 配置文件

| 文件 | 说明 | 位置 |
|------|------|------|
| `s7_tags.json` | 标签配置（含预置示例） | 程序目录，首次运行生成 |
| `screens.json` | 画面布局 | 程序目录，首次保存生成 |

## 🔧 常见问题

- **连接超时**：检查 IP / 网段 / PLC 是否可 ping 通；仿真环境检查虚拟网卡配置
- **连上但看不到数值**：确认标签 `scan_enabled` 为开（右键菜单可恢复）；确认地址在 PLC 中存在
- **读不到 DB 数据**：TIA 里把 DB 的"优化的块访问"关闭并重新编译
- **WebView2 报错**：安装微软 WebView2 Runtime

## 📄 许可

仅限学习与内部使用。
