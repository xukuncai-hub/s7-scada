"""
S7 SCADA 主窗口 - S7-1200/1500 PLC 上位机
整合连接面板、标签表格、PLC 通信线程
"""
import json
import os
import sys
import ctypes
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QStatusBar, QMenuBar, QMenu, QToolBar,
    QMessageBox, QFileDialog, QLabel, QFrame, QApplication,
    QScrollArea
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtGui import QAction, QIcon, QFont

from tag_config import TagConfig, DataType, Area, TagQuality, parse_address
from plc_worker import PlcWorker
from widgets.connection_panel import ConnectionPanel
from widgets.tag_table import TagTableWidget
from widgets.tag_editor import TagEditorDialog
from theme import current, is_light


# 应用配置常量
APP_NAME = "S7 SCADA"
APP_VERSION = "1.0.0"
CONFIG_FILE = "s7_tags.json"


def create_preset_tags() -> list[TagConfig]:
    """创建预置示例标签"""
    presets = [
        ("急停信号", "DB1.DBX0.0", DataType.BOOL, "Alarms"),
        ("运行状态", "M0.0", DataType.BOOL, "Digital Inputs"),
        ("温度值", "DB1.DBW2", DataType.INT, "Analog Inputs"),
        ("压力值", "DB1.DBD4", DataType.REAL, "Analog Inputs"),
        ("传感器输入", "I0.0", DataType.BOOL, "Digital Inputs"),
        ("产量计数", "DB1.DBD8", DataType.DINT, "Production Data"),
        ("电机速度", "DB1.DBW12", DataType.WORD, "Parameters"),
        ("输出状态", "Q0.0", DataType.BOOL, "Digital Outputs"),
    ]

    tags = []
    for name, addr, dtype, group in presets:
        parsed = parse_address(addr)
        if parsed:
            tags.append(TagConfig(
                name=name,
                address=addr,
                area=parsed['area'],
                data_type=dtype,
                db_number=parsed['db_number'],
                byte_offset=parsed['byte_offset'],
                bit_offset=parsed.get('bit_offset', 0),
                group=group,
                scan_enabled=True,
            ))
    return tags


class S7App(QMainWindow):
    """S7 SCADA 主窗口"""

    def __init__(self):
        super().__init__()
        self._tags: list[TagConfig] = []

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} - PLC 上位机")
        self.setMinimumSize(1100, 720)
        self.resize(1280, 840)

        # ── 初始化 PLC 工作线程 ──
        self.plc_worker = PlcWorker()
        self._connect_signals()

        # ── 构建 UI ──
        self._setup_menubar()
        self._setup_toolbar()
        self._setup_central()
        self._setup_statusbar()

        # ── 全局快捷键 ──
        self._shortcut_f11 = QShortcut(QKeySequence(Qt.Key.Key_F11), self)
        self._shortcut_f11.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._shortcut_f11.activated.connect(self._toggle_fullscreen)

        # ── 加载配置 ──
        self._load_config()

        # 启动时设置 Windows 标题栏为浅色（默认浅色主题）
        self._set_titlebar_dark(int(self.winId()), False)

    # ═══════════════════════════════════════════════════
    #  信号连接
    # ═══════════════════════════════════════════════════

    def _connect_signals(self):
        """连接 PLC Worker 信号到 UI 更新"""
        w = self.plc_worker

        # 连接状态
        w.connected.connect(self._on_connected)
        w.disconnected.connect(self._on_disconnected)
        w.connection_error.connect(self._on_connection_error)
        w.plc_info.connect(self._on_plc_info)

        # 数据
        w.data_updated.connect(self._on_data_updated)
        w.scan_time.connect(self._on_scan_time)

    # ═══════════════════════════════════════════════════
    #  菜单栏
    # ═══════════════════════════════════════════════════

    def _setup_menubar(self):
        menubar = self.menuBar()

        # ── 文件 ──
        file_menu = menubar.addMenu("文件(&F)")

        load_action = QAction("打开配置...", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self._load_tags_from_file)
        file_menu.addAction(load_action)

        save_action = QAction("保存配置", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_tags_to_file)
        file_menu.addAction(save_action)

        save_as_action = QAction("另存为...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._save_tags_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        clear_action = QAction("清空标签", self)
        clear_action.triggered.connect(self._clear_tags)
        file_menu.addAction(clear_action)

        reset_action = QAction("恢复预置标签", self)
        reset_action.triggered.connect(self._reset_presets)
        file_menu.addAction(reset_action)

        file_menu.addSeparator()

        fullscreen_action = QAction("全屏模式  (F11)", self)
        fullscreen_action.triggered.connect(self._toggle_fullscreen)
        file_menu.addAction(fullscreen_action)

        file_menu.addSeparator()

        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Alt+F4")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # ── 视图 ──
        view_menu = menubar.addMenu("视图(&V)")

        self.theme_action = QAction("深色模式", self)
        self.theme_action.setShortcut("Ctrl+T")
        self.theme_action.triggered.connect(self._toggle_theme)
        view_menu.addAction(self.theme_action)

        view_menu.addSeparator()

        fullscreen_v_action = QAction("全屏模式  (F11)", self)
        fullscreen_v_action.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(fullscreen_v_action)

        # ── PLC ──
        plc_menu = menubar.addMenu("PLC(&P)")

        connect_action = QAction("连接 PLC", self)
        connect_action.setShortcut("F5")
        connect_action.triggered.connect(self._connect_plc)
        plc_menu.addAction(connect_action)

        disconnect_action = QAction("断开 PLC", self)
        disconnect_action.setShortcut("F6")
        disconnect_action.triggered.connect(self._disconnect_plc)
        plc_menu.addAction(disconnect_action)

        plc_menu.addSeparator()

        add_action = QAction("添加标签...", self)
        add_action.setShortcut("Ctrl+N")
        add_action.triggered.connect(self._add_tag)
        plc_menu.addAction(add_action)

        # ── 帮助 ──
        help_menu = menubar.addMenu("帮助(&H)")

        about_action = QAction("关于...", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ═══════════════════════════════════════════════════
    #  工具栏
    # ═══════════════════════════════════════════════════

    def _setup_toolbar(self):
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # 连接按钮
        # 连接按钮
        self.tb_connect = QAction("  连接 PLC", self)
        self.tb_connect.triggered.connect(self._connect_plc)
        toolbar.addAction(self.tb_connect)

        self.tb_disconnect = QAction("  断开 PLC", self)
        self.tb_disconnect.triggered.connect(self._disconnect_plc)
        self.tb_disconnect.setVisible(False)
        toolbar.addAction(self.tb_disconnect)

        toolbar.addSeparator()

        # 标签
        tb_add = QAction("  添加标签", self)
        tb_add.triggered.connect(self._add_tag)
        toolbar.addAction(tb_add)

        toolbar.addSeparator()

        # 保存
        tb_save = QAction("  保存配置", self)
        tb_save.triggered.connect(self._save_tags_to_file)
        toolbar.addAction(tb_save)

        toolbar.addSeparator()

        # 连接状态指示
        self.tb_status = QLabel("  未连接  ")
        self.tb_status.setObjectName("tbStatus")
        toolbar.addWidget(self.tb_status)

    # ═══════════════════════════════════════════════════
    #  中央区域
    # ═══════════════════════════════════════════════════

    def _setup_central(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(3)

        # ── 左面板 ──
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(10)

        self.connection_panel = ConnectionPanel()
        self.connection_panel.connect_requested.connect(self._on_connect_requested)
        self.connection_panel.disconnect_requested.connect(self._disconnect_plc)
        left_layout.addWidget(self.connection_panel)

        # ── 可滚动的提示卡片区 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")

        tips_widget = QWidget()
        tips_layout = QVBoxLayout(tips_widget)
        tips_layout.setContentsMargins(0, 0, 0, 0)
        tips_layout.setSpacing(8)

        # TIA Portal 配置
        warn = QFrame()
        warn.setObjectName("warnCard")
        wl = QVBoxLayout(warn)
        wl.setContentsMargins(12, 10, 12, 10)
        wl.setSpacing(4)
        wt = QLabel("TIA Portal 设置检查")
        wt.setObjectName("warnTitle")
        wl.addWidget(wt)
        wb = QLabel(
            "1. CPU 属性 → 防护与安全 → 允许 PUT/GET 通信\n"
            "2. DB 块属性 → 取消「优化的块访问」\n"
            "3. 确认 CPU 处于 RUN 模式"
        )
        wb.setObjectName("warnBody")
        wb.setWordWrap(True)
        wl.addWidget(wb)
        self.plc_warning = warn
        tips_layout.addWidget(warn)

        tips_layout.addWidget(self._make_info_card("地址格式",
            "DB1.DBX0.0    布尔位 (Bit)\n"
            "DB1.DBW2      字     (Word, 2B)\n"
            "DB1.DBD4      双字   (DWord, 4B)\n"
            "M0.0   M区布尔  I0.0   输入\n"
            "Q0.0   输出      MW2    M区字"))
        tips_layout.addWidget(self._make_info_card("数据类型",
            "Bool → 位      Byte → 8b\n"
            "Word → 16b     DWord → 32b\n"
            "Int → 有符号16  DInt → 有符号32\n"
            "Real → IEEE754浮点"))
        tips_layout.addWidget(self._make_info_card("快捷键",
            "F5 连接  F6 断开  F11 全屏\n"
            "Ctrl+N 添加  Ctrl+S 保存\n"
            "Ctrl+T 浅色/深色切换\n"
            "双击单元格 写入  右键 菜单"))
        tips_layout.addWidget(self._make_info_card("写入数值",
            "双击表格 → 输入新值 → 确认\n"
            "Bool 双击自动翻转 ON/OFF\n"
            "支持十进制 或 十六进制(0x前缀)\n"
            "示例: 42 / 0x1A2B / 3.14159"))
        tips_layout.addWidget(self._make_info_card("故障排查",
            "读取失败 → 检查 PUT/GET 权限\n"
            "DB失败 → 关闭优化块访问\n"
            "写入失败 → 确认区域可写\n"
            "连不上 → 确认 IP/Rack/Slot"))

        tips_layout.addStretch()
        scroll.setWidget(tips_widget)
        left_layout.addWidget(scroll)

        splitter.addWidget(left_panel)

        # ── 右面板（数据表格） ──
        self.tag_table = TagTableWidget()
        self.tag_table.tag_add_requested.connect(self._add_tag)
        self.tag_table.tag_delete_requested.connect(self._delete_tag)
        self.tag_table.tag_edit_requested.connect(self._edit_tag)
        self.tag_table.write_requested.connect(self._write_tag)
        splitter.addWidget(self.tag_table)

        splitter.setSizes([340, 1020])
        main_layout.addWidget(splitter)

    @staticmethod
    def _make_info_card(title: str, body: str) -> "QFrame":
        card = QFrame()
        card.setObjectName("infoCard")
        l = QVBoxLayout(card)
        l.setContentsMargins(14, 12, 14, 12)
        l.setSpacing(6)
        t = QLabel(title)
        t.setObjectName("infoTitle")
        l.addWidget(t)
        b = QLabel(body)
        b.setObjectName("infoBody")
        b.setWordWrap(True)
        l.addWidget(b)
        return card

    # ═══════════════════════════════════════════════════
    #  状态栏
    # ═══════════════════════════════════════════════════

    def _setup_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.sb_connection = QLabel(" 未连接")
        self.sb_connection.setObjectName("sbDisconnected")
        self.status_bar.addWidget(self.sb_connection)

        self.sb_plc_info = QLabel("")
        self.sb_plc_info.setObjectName("sbInfo")
        self.status_bar.addWidget(self.sb_plc_info)

        self.sb_scan = QLabel("")
        self.sb_scan.setObjectName("sbScan")
        self.status_bar.addPermanentWidget(self.sb_scan)

        self.sb_tags = QLabel("标签: 0")
        self.sb_tags.setObjectName("sbTags")
        self.status_bar.addPermanentWidget(self.sb_tags)

    # ═══════════════════════════════════════════════════
    #  事件处理
    # ═══════════════════════════════════════════════════

    def changeEvent(self, event):
        """最大化→无边框全屏"""
        if event.type() == event.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMaximized:
                self.setWindowState(
                    self.windowState() & ~Qt.WindowState.WindowMaximized)
                self.showFullScreen()
        super().changeEvent(event)

    def closeEvent(self, event):
        self._save_config()
        if self.plc_worker.isRunning():
            self.plc_worker.stop()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            self._toggle_fullscreen()
        elif event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
        else:
            super().keyPressEvent(event)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ── 主题切换 ────────────────────────────────────────
    _light = True  # 默认浅色模式

    @staticmethod
    def _set_titlebar_dark(hwnd: int, dark: bool):
        """Windows 标题栏深色/浅色 (DWM)"""
        if sys.platform != "win32":
            return
        try:
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1 if dark else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

    def _toggle_theme(self):
        self._light = not self._light
        if self._light:
            path = Path(__file__).parent / "style_light.qss"
            self.theme_action.setText("深色模式")
        else:
            path = Path(__file__).parent / "style.qss"
            self.theme_action.setText("浅色模式")

        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                QApplication.instance().setStyleSheet(f.read())

        # Windows 标题栏跟随主题
        self._set_titlebar_dark(int(self.winId()), not self._light)

        if self.plc_worker.is_plc_connected:
            self._on_connected()
        else:
            self._on_disconnected()

    # ═══════════════════════════════════════════════════
    #  PLC 连接
    # ═══════════════════════════════════════════════════

    def _on_connect_requested(self, ip: str, rack: int, slot: int):
        """连接面板触发连接"""
        self.plc_worker.set_connection(ip, rack, slot)
        self.plc_worker.set_scan_interval(
            self.connection_panel.get_scan_interval()
        )
        self.plc_worker.set_tags(self._tags)
        self.plc_worker.connect_plc()

    def _connect_plc(self):
        """通过工具栏/菜单触发连接"""
        cp = self.connection_panel
        ip = cp.ip_input.text().strip()
        if not ip:
            QMessageBox.warning(self, "警告", "请输入 PLC IP 地址")
            return
        self.plc_worker.set_connection(
            ip, cp.rack_spin.value(), cp.slot_spin.value()
        )
        self.plc_worker.set_scan_interval(cp.get_scan_interval())
        self.plc_worker.set_tags(self._tags)
        self.plc_worker.connect_plc()

    def _disconnect_plc(self):
        """断开 PLC"""
        self.plc_worker.disconnect_plc()

    def _on_connected(self):
        self.connection_panel.set_status(True, self.plc_worker.ip)
        self.sb_connection.setText(" 已连接")
        self.sb_connection.setObjectName("sbConnected")
        self.tb_status.setText("  已连接  ")
        self.tb_status.setObjectName("tbConnected")
        self.tb_connect.setVisible(False)
        self.tb_disconnect.setVisible(True)
        self.plc_warning.setVisible(False)
        # refresh style
        self.sb_connection.style().unpolish(self.sb_connection)
        self.sb_connection.style().polish(self.sb_connection)
        self.tb_status.style().unpolish(self.tb_status)
        self.tb_status.style().polish(self.tb_status)

    def _on_disconnected(self, reason: str = ""):
        self.connection_panel.set_status(False, reason)
        self.sb_connection.setText(" 未连接")
        self.sb_connection.setObjectName("sbDisconnected")
        self.tb_status.setText("  未连接  ")
        self.tb_status.setObjectName("tbDisconnected")
        self.tb_connect.setVisible(True)
        self.tb_disconnect.setVisible(False)
        self.plc_warning.setVisible(True)
        self.sb_connection.style().unpolish(self.sb_connection)
        self.sb_connection.style().polish(self.sb_connection)
        self.tb_status.style().unpolish(self.tb_status)
        self.tb_status.style().polish(self.tb_status)

    def _on_connection_error(self, error: str):
        self.connection_panel.set_connection_error(error)
        self.sb_connection.setText(f" 错误: {error[:50]}")
        self.sb_connection.setObjectName("sbError")
        self.sb_connection.style().unpolish(self.sb_connection)
        self.sb_connection.style().polish(self.sb_connection)

    def _on_plc_info(self, module: str, version: str, serial: str):
        """PLC 信息更新"""
        self.connection_panel.set_plc_info(module, version, serial)
        self.sb_plc_info.setText(f"PLC: {module} | S/N: {serial[:20]}")
        self.setWindowTitle(
            f"{APP_NAME} v{APP_VERSION} - {module} @ "
            f"{self.plc_worker.ip}"
        )

    # ═══════════════════════════════════════════════════
    #  数据更新
    # ═══════════════════════════════════════════════════

    def _on_data_updated(self, results: list):
        """PLC 数据更新"""
        self.tag_table.update_values(results)

        # 统计好/坏数据，显示诊断
        good_count = sum(1 for r in results if r[2] == TagQuality.GOOD)
        bad_count = len(results) - good_count
        if bad_count > 0:
            errors = set()
            for r in results:
                if r[2] != TagQuality.GOOD and len(r) > 4 and r[4]:
                    errors.add(r[4])
            err_summary = " | ".join(list(errors)[:3])
            self.sb_tags.setText(f"标签: {len(self._tags)} | OK:{good_count} BAD:{bad_count}")
            if err_summary:
                self.sb_plc_info.setText(f" {err_summary[:120]}")
                self.sb_plc_info.setObjectName("sbWarn")
            if good_count == 0:
                self.tag_table.set_all_bad(err_summary)
        else:
            self.sb_tags.setText(f"标签: {len(self._tags)} | OK:{good_count}")
            self.sb_plc_info.setObjectName("sbInfo")
            self.tag_table.set_all_bad("")
        self.sb_plc_info.style().unpolish(self.sb_plc_info)
        self.sb_plc_info.style().polish(self.sb_plc_info)

    def _on_scan_time(self, scan_ms: float):
        """扫描耗时更新"""
        self.tag_table.set_scan_info(scan_ms)
        self.sb_scan.setText(f"扫描: {scan_ms:.1f} ms")

    # ═══════════════════════════════════════════════════
    #  标签管理
    # ═══════════════════════════════════════════════════

    def _add_tag(self):
        """打开添加标签对话框"""
        dialog = TagEditorDialog(self)
        if dialog.exec() == TagEditorDialog.DialogCode.Accepted:
            tag = dialog.get_tag()
            if tag:
                self._tags.append(tag)
                self._refresh_ui()

    def _edit_tag(self, index: int):
        """编辑标签"""
        if 0 <= index < len(self._tags):
            dialog = TagEditorDialog(self, self._tags[index])
            if dialog.exec() == TagEditorDialog.DialogCode.Accepted:
                new_tag = dialog.get_tag()
                if new_tag:
                    self._tags[index] = new_tag
                    self._refresh_ui()

    def _delete_tag(self, index: int):
        """删除标签"""
        if 0 <= index < len(self._tags):
            tag = self._tags[index]
            reply = QMessageBox.question(
                self, "确认删除",
                f"确定要删除标签 「{tag.name}」({tag.address}) 吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                del self._tags[index]
                self._refresh_ui()

    def _clear_tags(self):
        """清空所有标签"""
        if not self._tags:
            return
        reply = QMessageBox.question(
            self, "确认清空",
            f"确定要删除全部 {len(self._tags)} 个标签吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._tags.clear()
            self._refresh_ui()

    def _reset_presets(self):
        """恢复预置标签"""
        reply = QMessageBox.question(
            self, "恢复预置",
            "将用预置示例标签替换当前配置，确定吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._tags = create_preset_tags()
            self._refresh_ui()

    def _write_tag(self, index: int, value):
        """写入标签值到 PLC"""
        if index < 0 or index >= len(self._tags):
            return
        tag = self._tags[index]

        if not self.plc_worker.is_plc_connected:
            QMessageBox.warning(
                self, "无法写入", "PLC 未连接，请先连接 PLC"
            )
            return

        success, msg = self.plc_worker.write_tag(index, tag, value)
        if success:
            self.statusBar().showMessage(
                f"✓ 写入成功: {tag.name} = {value}", 3000
            )
        else:
            QMessageBox.critical(
                self, "写入失败", f"{tag.name}: {msg}"
            )

    def _refresh_ui(self):
        """刷新 UI 显示"""
        self.plc_worker.set_tags(self._tags)
        self.tag_table.set_tags(self._tags)
        self.sb_tags.setText(f"标签: {len(self._tags)}")

    # ═══════════════════════════════════════════════════
    #  配置持久化
    # ═══════════════════════════════════════════════════

    def _config_path(self) -> Path:
        return Path(CONFIG_FILE)

    def _save_config(self):
        """自动保存到默认配置文件"""
        try:
            data = []
            for tag in self._tags:
                data.append({
                    'name': tag.name,
                    'address': tag.address,
                    'area': tag.area.prefix,
                    'data_type': tag.data_type.value,
                    'db_number': tag.db_number,
                    'byte_offset': tag.byte_offset,
                    'bit_offset': tag.bit_offset,
                    'group': tag.group,
                    'scan_enabled': tag.scan_enabled,
                    'comment': tag.comment,
                })
            with open(self._config_path(), 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Save config failed: {e}")

    def _load_config(self):
        """加载配置，失败则用预置标签"""
        try:
            path = self._config_path()
            if not path.exists():
                self._tags = create_preset_tags()
                self._refresh_ui()
                return

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._tags = []
            for item in data:
                area_map = {a.prefix: a for a in Area}
                dt_map = {dt.value: dt for dt in DataType}

                area = area_map.get(item.get('area', 'M'), Area.M)
                dtype = dt_map.get(item.get('data_type', 'Bool'), DataType.BOOL)

                self._tags.append(TagConfig(
                    name=item.get('name', 'Tag'),
                    address=item.get('address', ''),
                    area=area,
                    data_type=dtype,
                    db_number=item.get('db_number', 0),
                    byte_offset=item.get('byte_offset', 0),
                    bit_offset=item.get('bit_offset', 0),
                    group=item.get('group', 'Default'),
                    scan_enabled=item.get('scan_enabled', True),
                    comment=item.get('comment', ''),
                ))
            self._refresh_ui()
        except Exception as e:
            print(f"Load config failed: {e}")
            self._tags = create_preset_tags()
            self._refresh_ui()

    def _save_tags_to_file(self):
        """保存到当前配置文件"""
        self._save_config()
        self.statusBar().showMessage(
            f"✓ 配置已保存: {self._config_path()}", 3000
        )

    def _save_tags_as(self):
        """另存为 JSON 文件"""
        path, _ = QFileDialog.getSaveFileName(
            self, "保存标签配置", "tags.json",
            "JSON 文件 (*.json);;All Files (*)"
        )
        if path:
            try:
                data = []
                for tag in self._tags:
                    data.append({
                        'name': tag.name,
                        'address': tag.address,
                        'area': tag.area.prefix,
                        'data_type': tag.data_type.value,
                        'db_number': tag.db_number,
                        'byte_offset': tag.byte_offset,
                        'bit_offset': tag.bit_offset,
                        'group': tag.group,
                        'scan_enabled': tag.scan_enabled,
                        'comment': tag.comment,
                    })
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                self.statusBar().showMessage(
                    f"✓ 配置已保存: {path}", 3000
                )
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存失败: {e}")

    def _load_tags_from_file(self):
        """从 JSON 文件加载配置"""
        path, _ = QFileDialog.getOpenFileName(
            self, "打开标签配置", "",
            "JSON 文件 (*.json);;All Files (*)"
        )
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                self._tags = []
                area_map = {a.prefix: a for a in Area}
                dt_map = {dt.value: dt for dt in DataType}

                for item in data:
                    area = area_map.get(item.get('area', 'M'), Area.M)
                    dtype = dt_map.get(item.get('data_type', 'Bool'), DataType.BOOL)

                    self._tags.append(TagConfig(
                        name=item.get('name', 'Tag'),
                        address=item.get('address', ''),
                        area=area,
                        data_type=dtype,
                        db_number=item.get('db_number', 0),
                        byte_offset=item.get('byte_offset', 0),
                        bit_offset=item.get('bit_offset', 0),
                        group=item.get('group', 'Default'),
                        scan_enabled=item.get('scan_enabled', True),
                        comment=item.get('comment', ''),
                    ))

                self._refresh_ui()
                self.statusBar().showMessage(
                    f"✓ 已加载 {len(self._tags)} 个标签: {path}", 5000
                )
            except Exception as e:
                QMessageBox.critical(self, "错误", f"加载失败: {e}")

    def _show_about(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton

        c = current()

        dlg = QDialog(self)
        dlg.setWindowTitle(f"关于 {APP_NAME}")
        dlg.setFixedSize(420, 380)
        dlg.setStyleSheet(f"""
            QDialog {{ background: {c.bg_panel}; }}
            QLabel {{ color: {c.text_primary}; background: transparent; }}
            QLabel#title {{ font-size: 22px; font-weight: 700; color: {c.dlg_title}; }}
            QLabel#sub {{ font-size: 13px; color: {c.dlg_subtitle}; }}
            QLabel#info {{ font-size: 13px; color: {c.dlg_info}; }}
            QLabel#copy {{ font-size: 11px; color: {c.dlg_copy}; }}
            QPushButton {{ background: {c.accent}; border: none; color: {c.white};
                font-weight: 600; font-size: 13px; padding: 10px 28px; border-radius: 7px; }}
            QPushButton:hover {{ background: {c.accent_hover}; }}
        """)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(10)

        title = QLabel(f"{APP_NAME} v{APP_VERSION}")
        title.setObjectName("title")
        layout.addWidget(title)

        sub = QLabel("S7-1200/1500 PLC 上位机监控软件")
        sub.setObjectName("sub")
        layout.addWidget(sub)

        layout.addSpacing(8)

        info = QLabel(
            "协议: S7 (ISO-on-TCP)<br>"
            "设备: S7-1200 / S7-1500<br>"
            "默认: Rack=0, Slot=1<br>"
            "框架: Python 3 + PyQt6 + python-snap7"
        )
        info.setObjectName("info")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addSpacing(8)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: {c.border}; max-height: 1px;")
        layout.addWidget(sep)

        author = QLabel("作者: song")
        author.setObjectName("info")
        layout.addWidget(author)

        email = QLabel("邮箱: 2023234259@qq.com")
        email.setObjectName("info")
        email.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(email)

        layout.addSpacing(6)

        copy = QLabel("S7 SCADA  © 2025")
        copy.setObjectName("copy")
        layout.addWidget(copy)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("确定")
        btn_close.clicked.connect(dlg.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        dlg.exec()
