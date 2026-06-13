"""
实时数据面板 - 数值仪表板卡片 + 数据表格
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QMenu, QPushButton, QLabel, QInputDialog, QMessageBox,
    QFrame, QScrollArea, QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QFont, QBrush, QAction, QPainter, QPen, QLinearGradient
from collections import defaultdict

from tag_config import TagConfig, DataType, TagQuality
from theme import current, area_colors, type_colors


# ── 数值仪表板卡片 ──────────────────────────────────────


class ValueCard(QFrame):
    """单个数值卡片 - 区域色标 + 大号数值"""

    def __init__(self, tag: TagConfig, parent=None):
        super().__init__(parent)
        self.tag = tag
        self._value = None
        self._quality = TagQuality.UNKNOWN
        self._flash_count = 0
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._flash_tick)
        self._flash_timer.setInterval(55)

        _areas = area_colors()
        self._area_color = _areas.get(tag.area.prefix, _areas.get("M", ("#1f2937", "#64748b")))

        self.setObjectName("valueCard")
        self.setMinimumSize(140, 96)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        content = QVBoxLayout()
        content.setContentsMargins(14, 10, 12, 10)
        content.setSpacing(3)

        # 标签名 - 带区域色标和类型图标
        header = QHBoxLayout()
        header.setSpacing(6)

        # 色标条
        self._dot = QLabel()
        self._dot.setFixedSize(7, 7)
        self._dot.setStyleSheet(
            f"background-color: {self._area_color[1]}; "
            "border-radius: 3px; min-width: 7px; min-height: 7px;"
        )
        header.addWidget(self._dot)

        self.name_lbl = QLabel(self.tag.name)
        self.name_lbl.setObjectName("cardLabel")
        self.name_lbl.setStyleSheet("")
        header.addWidget(self.name_lbl, stretch=1)

        # 禁用图标
        self._disabled_lbl = QLabel()
        self._disabled_lbl.setStyleSheet(f"color: {current().text_dim}; font-size: 11px;")
        header.addWidget(self._disabled_lbl)

        content.addLayout(header)

        # 数值 - 大字
        self.value_lbl = QLabel("---")
        self.value_lbl.setObjectName("cardValue")
        self.value_lbl.setWordWrap(False)
        content.addWidget(self.value_lbl)

        # 地址 + 时间
        self.addr_lbl = QLabel(self.tag.address)
        self.addr_lbl.setObjectName("cardAddr")
        content.addWidget(self.addr_lbl)

        layout.addLayout(content)

        # 不启用时的外观
        if not self.tag.scan_enabled:
            c = current()
            self._disabled_lbl.setText("⏸")
            self.name_lbl.setStyleSheet(f"color: {c.text_dim}; font-size: 11px; font-weight: 600;")
            self.value_lbl.setStyleSheet(
                f"color: {c.text_dim}; font-family: 'JetBrains Mono', 'Consolas', monospace; "
                "font-size: 24px; font-weight: 700;"
            )

    def update_value(self, value, quality: TagQuality, timestamp: str, error_msg: str = ""):
        """更新卡片数值"""
        old_val = self._value
        self._value = value
        self._quality = quality

        if quality == TagQuality.GOOD and value is not None:
            display = self._fmt(value)
            self.value_lbl.setText(display)

            if isinstance(value, bool):
                value_obj = "cardValueGood" if value else "cardValue"
                self.value_lbl.setObjectName(value_obj)
            elif isinstance(value, (int, float)):
                self.value_lbl.setObjectName("cardValue")
                self.value_lbl.setStyleSheet(self._number_style(current().accent))
            else:
                self.value_lbl.setObjectName("cardValue")

            self.setToolTip(
                f"<b>{self.tag.name}</b><br>"
                f"值: {display}<br>"
                f"地址: {self.tag.address}<br>"
                f"时间: {timestamp}"
            )

            if old_val is not None and old_val != value:
                self._flash_count = 6
                self._flash_timer.start()
        else:
            self.value_lbl.setText("???")
            self.value_lbl.setObjectName("cardValueBad")
            self.value_lbl.setStyleSheet("")
            tooltip = f"<b>⚠ {self.tag.name}</b><br>读取失败"
            if error_msg:
                tooltip += f"<br><br>{error_msg}"
            tooltip += (
                f"<br><br><span style='color:{current().text_dim};font-size:10px;'>"
                "可能原因:<br>"
                "• PLC 未启用 PUT/GET 通信<br>"
                "• DB 块未关闭优化访问<br>"
                "• 地址超出范围</span>"
            )
            self.setToolTip(tooltip)

    def _number_style(self, color: str) -> str:
        return (
            f"color: {color}; "
            "font-family: 'JetBrains Mono', 'Consolas', monospace; "
            "font-size: 24px; font-weight: 700;"
        )

    def _flash_tick(self):
        """值变化闪烁动画 - 使用区域色"""
        if self._flash_count <= 0:
            self._flash_timer.stop()
            self.setStyleSheet("")
            return
        self._flash_count -= 1
        if self._flash_count % 2 == 1:
            glow = self._area_color[0]
            accent = self._area_color[1]
            self.setStyleSheet(
                f"QFrame#valueCard {{ "
                f"background-color: {glow}; "
                f"border: 1px solid {accent}; "
                f"border-radius: 12px; }}"
            )
        else:
            self.setStyleSheet("")

    @staticmethod
    def _fmt(value) -> str:
        """格式化值"""
        if isinstance(value, bool):
            return "◉ ON" if value else "○ OFF"
        if isinstance(value, float):
            if abs(value) >= 1000:
                return f"{value:.1f}"
            return f"{value:.4f}"
        if isinstance(value, int):
            if abs(value) > 9999:
                return f"{value}"
            return str(value)
        return str(value)

    def mouseDoubleClickEvent(self, event):
        p = self.parent()
        while p and not isinstance(p, TagTableWidget):
            p = p.parent()
        if p:
            idx = p._tags.index(self.tag) if self.tag in p._tags else -1
            if idx >= 0:
                p._on_write_value(idx)


class ValueDashboard(QWidget):
    """数值仪表板 - 优化的网格卡片布局"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[ValueCard] = []
        self._setup_ui()

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 10)
        self.main_layout.setSpacing(10)

        # 标题行
        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 4, 0)

        icon_lbl = QLabel("◈")
        icon_lbl.setStyleSheet(f"color: {current().accent}; font-size: 15px; font-weight: 700;")
        header.addWidget(icon_lbl)

        title = QLabel("实时数值面板")
        title.setObjectName("sectionTitle")
        header.addWidget(title)

        header.addStretch()

        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("scanTime")
        header.addWidget(self.count_lbl)

        # 扫描指示灯
        self._pulse_dot = QLabel()
        self._pulse_dot.setFixedSize(8, 8)
        self._pulse_dot.setStyleSheet(
            f"background-color: {current().success}; border-radius: 4px;"
        )
        self._pulse_dot.setVisible(False)
        header.addWidget(self._pulse_dot)

        self.main_layout.addLayout(header)

        # 卡片滚动区
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(116)
        self.scroll.setStyleSheet(
            "QScrollArea { background-color: transparent; border: none; }"
            "QScrollBar:horizontal { height: 6px; background: transparent; }"
            "QScrollBar::handle:horizontal { background: rgba(128,128,128,0.3); border-radius: 3px; min-width: 30px; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }"
        )

        self.card_container = QWidget()
        self.card_container.setObjectName("dashboardCards")
        self.card_layout = QHBoxLayout(self.card_container)
        self.card_layout.setContentsMargins(4, 0, 4, 0)
        self.card_layout.setSpacing(12)
        self.card_layout.addStretch()

        self.scroll.setWidget(self.card_container)
        self.main_layout.addWidget(self.scroll)

        self.setVisible(False)

    def set_tags(self, tags: list[TagConfig]):
        """重建卡片"""
        for card in self._cards:
            self.card_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        if not tags:
            self.setVisible(False)
            self._pulse_dot.setVisible(False)
            return

        self.setVisible(True)
        self._pulse_dot.setVisible(True)

        for tag in tags:
            card = ValueCard(tag)
            self._cards.append(card)
            self.card_layout.insertWidget(self.card_layout.count() - 1, card)

        self.count_lbl.setText(f"{len(tags)} 个实时值")

    def update_values(self, results: list, tag_map: dict):
        """批量更新卡片值
        results: [(tag_index, value, quality, timestamp, error_msg?), ...]
        tag_map:  {card.tag → tag_index in self._cards's source list}
        """
        for card in self._cards:
            tag = card.tag
            for item in results:
                idx = item[0]
                value = item[1]
                quality = item[2]
                timestamp = item[3]
                error_msg = item[4] if len(item) > 4 else ""
                if tag is tag_map.get(idx):
                    card.update_value(value, quality, timestamp, error_msg)
                    break


# ── 主面板组件 ────────────────────────────────────────────

class TagTableWidget(QWidget):
    """实时数据面板 = 数值仪表板 + 数据表格"""

    tag_add_requested = pyqtSignal()
    tag_delete_requested = pyqtSignal(int)
    tag_edit_requested = pyqtSignal(int)
    write_requested = pyqtSignal(int, object)

    COL_NAME = 0
    COL_ADDRESS = 1
    COL_TYPE = 2
    COL_VALUE = 3
    COL_QUALITY = 4
    COL_TIME = 5

    HEADERS = ["名称", "地址", "类型", "当前值", "质量", "时间"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tags: list[TagConfig] = []
        self._tag_values: dict = {}   # index → (value, quality, timestamp)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ── 数值仪表板卡片 ──
        self.dashboard = ValueDashboard()
        layout.addWidget(self.dashboard)

        # ── 表格工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.setContentsMargins(4, 0, 4, 0)

        icon_lbl = QLabel("▦")
        icon_lbl.setStyleSheet(f"color: {current().accent}; font-size: 15px; font-weight: 700;")
        toolbar.addWidget(icon_lbl)

        title = QLabel("标签数据表")
        title.setObjectName("sectionTitle")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self.tag_count_label = QLabel("0 个标签")
        self.tag_count_label.setObjectName("scanTime")
        toolbar.addWidget(self.tag_count_label)

        btn_add = QPushButton("  添加标签")
        btn_add.setObjectName("btnAdd")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self.tag_add_requested.emit)
        toolbar.addWidget(btn_add)

        btn_scan_all = QPushButton("  全部扫描")
        btn_scan_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_scan_all.clicked.connect(self._toggle_all_scan)
        toolbar.addWidget(btn_scan_all)

        layout.addLayout(toolbar)

        # ── 表格 ──
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._on_double_click)

        # 交替行颜色
        self.table.setAlternatingRowColors(False)  # 我们自己控制

        # 表头
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_ADDRESS, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_TYPE, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(self.COL_TYPE, 80)
        header.setSectionResizeMode(self.COL_VALUE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_QUALITY, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(self.COL_QUALITY, 80)
        header.setSectionResizeMode(self.COL_TIME, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(self.COL_TIME, 90)

        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)

        layout.addWidget(self.table, stretch=1)

        # ── 空状态 ──
        self.empty_label = QLabel(
            "◈  暂无标签\n\n"
            "点击  「＋ 添加标签」  开始配置 PLC 监控信号\n"
            "DB · M · I · Q · T · C  区域全支持"
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c = current()
        self.empty_label.setStyleSheet(
            f"color: {c.card_empty_text}; font-size: 15px; padding: 80px; "
            f"background-color: {c.card_empty_bg}; border: 1px dashed {c.card_empty_border}; "
            "border-radius: 12px; line-height: 1.8;"
        )
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)
        self.empty_label.setVisible(True)

        # ── 底部状态 ──
        bottom = QHBoxLayout()
        bottom.setContentsMargins(4, 0, 4, 0)
        self.scan_info_label = QLabel("⏳ 等待连接...")
        self.scan_info_label.setObjectName("scanTime")
        bottom.addWidget(self.scan_info_label)
        bottom.addStretch()
        layout.addLayout(bottom)

    # ── 公共方法 ────────────────────────────────────────

    def set_tags(self, tags: list[TagConfig]):
        """设置标签列表并刷新"""
        self._tags = tags
        self._tag_values.clear()
        self._refresh_table()
        self.dashboard.set_tags(tags)

    def update_values(self, results: list):
        """
        批量更新标签值
        results: [(tag_index, value, quality, timestamp, error_msg?), ...]
        """
        tag_map = {i: t for i, t in enumerate(self._tags)}

        for item in results:
            idx = item[0]
            value = item[1]
            quality = item[2]
            timestamp = item[3]
            error_msg = item[4] if len(item) > 4 else ""

            self._tag_values[idx] = (value, quality, timestamp)

            if idx < self.table.rowCount():
                self._update_row(idx, value, quality, timestamp, error_msg)

        # 更新仪表板卡片
        self.dashboard.update_values(results, tag_map)

    def set_scan_info(self, scan_ms: float):
        """扫描耗时"""
        self.scan_info_label.setText(f"⚡ 扫描周期: {scan_ms:.1f} ms")
        self.scan_info_label.setObjectName("scanTime")
        self.scan_info_label.style().unpolish(self.scan_info_label)
        self.scan_info_label.style().polish(self.scan_info_label)

    def set_all_bad(self, error_summary: str = ""):
        if error_summary:
            self.scan_info_label.setText(f" 读取失败: {error_summary[:100]}")
            self.scan_info_label.setStyleSheet(f"color:{current().warning}; font-size:12px; font-weight:600;")
        else:
            self.scan_info_label.setStyleSheet("")

    def get_tags(self) -> list[TagConfig]:
        return self._tags

    # ── 表格刷新 ────────────────────────────────────────

    def _refresh_table(self):
        """完全重建表格"""
        self.table.setRowCount(0)

        if not self._tags:
            self.table.setVisible(False)
            self.empty_label.setVisible(True)
            self.tag_count_label.setText("0 个标签")
            return

        self.table.setVisible(True)
        self.empty_label.setVisible(False)
        self.table.setRowCount(len(self._tags))
        self.tag_count_label.setText(f"{len(self._tags)} 个标签")

        # ── 区域配色 ──
        area_icons = {"DB": "▣", "M": "▢", "I": "→", "Q": "←", "T": "◷", "C": "◎"}
        _areas = area_colors()
        area_accent = {k: v[1] for k, v in _areas.items()}
        c = current()

        for i, tag in enumerate(self._tags):
            accent = area_accent.get(tag.area.prefix, c.text_dim)

            # 名称 - 带区域色标 + 禁用指示
            icon = area_icons.get(tag.area.prefix, "·")
            name_text = f"{icon}  {tag.name}"
            if not tag.scan_enabled:
                name_text = f"⏸  {tag.name}"

            name_item = QTableWidgetItem(name_text)
            name_item.setToolTip(
                f"<b>{tag.name}</b><br>"
                f"地址: {tag.address}<br>"
                f"分组: {tag.group}<br>"
                f"{tag.comment if tag.comment else ''}"
            )
            name_color = QColor(c.text_dim) if not tag.scan_enabled else QColor(accent)
            name_item.setForeground(QBrush(name_color))
            self.table.setItem(i, self.COL_NAME, name_item)

            # 地址
            addr_item = QTableWidgetItem(f" {tag.address} ")
            addr_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            addr_item.setForeground(QBrush(QColor(c.text_secondary)))
            addr_font = QFont("Consolas", 10)
            addr_font.setBold(False)
            addr_item.setFont(addr_font)
            self.table.setItem(i, self.COL_ADDRESS, addr_item)

            # 类型 - 彩色标签
            type_item = QTableWidgetItem(tag.data_type.value)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            _tc_map = type_colors()
            tc = _tc_map.get(tag.data_type.value, c.text_secondary)
            type_item.setForeground(QBrush(QColor(tc)))
            type_font = QFont(self.font().family(), 10)
            type_font.setBold(True)
            type_item.setFont(type_font)
            self.table.setItem(i, self.COL_TYPE, type_item)

            # 值
            value_item = QTableWidgetItem("---")
            value_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            value_font = QFont("Consolas", 14)
            value_font.setBold(True)
            value_item.setFont(value_font)
            self.table.setItem(i, self.COL_VALUE, value_item)

            # 质量
            q_item = QTableWidgetItem("—")
            q_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            q_item.setForeground(QBrush(QColor(c.text_dim)))
            self.table.setItem(i, self.COL_QUALITY, q_item)

            # 时间
            t_item = QTableWidgetItem("--:--:--")
            t_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            t_item.setForeground(QBrush(QColor(c.text_dim)))
            t_font = QFont("Consolas", 9)
            t_item.setFont(t_font)
            self.table.setItem(i, self.COL_TIME, t_item)

    def _update_row(self, row: int, value, quality: TagQuality, timestamp: str, error_msg: str = ""):
        """更新单行"""
        value_item = self.table.item(row, self.COL_VALUE)
        if value_item is None:
            return

        c = current()
        display = self._format_value(value, quality)
        value_item.setText(display)

        if quality == TagQuality.GOOD:
            if isinstance(value, bool):
                if value:
                    value_item.setForeground(QBrush(QColor(c.success)))
                else:
                    value_item.setForeground(QBrush(QColor(c.text_dim)))
            elif isinstance(value, (int, float)):
                value_item.setForeground(QBrush(QColor(c.accent)))
            else:
                value_item.setForeground(QBrush(QColor(c.text_primary)))
            value_item.setToolTip(f"值: {display}")
        else:
            value_item.setForeground(QBrush(QColor(c.danger)))
            tooltip = "⚠ 读取失败\n"
            if error_msg:
                tooltip += f"\n{error_msg}"
            tooltip += "\n\n可能原因:\n• PLC 未启用 PUT/GET 通信\n• DB 块未关闭优化访问\n• 地址超出范围"
            value_item.setToolTip(tooltip)

        # 质量
        q_item = self.table.item(row, self.COL_QUALITY)
        if q_item:
            if quality == TagQuality.GOOD:
                q_item.setText("GOOD")
                q_item.setForeground(QBrush(QColor(c.success)))
                q_item.setToolTip("数据正常")
            else:
                q_item.setText("BAD")
                q_item.setForeground(QBrush(QColor(c.danger)))
                q_item.setToolTip(error_msg if error_msg else "读取失败")

        # 时间
        t_item = self.table.item(row, self.COL_TIME)
        if t_item:
            t_item.setText(timestamp)
            t_item.setForeground(QBrush(QColor(c.text_dim)))

    @staticmethod
    def _format_value(value, quality: TagQuality = TagQuality.UNKNOWN) -> str:
        """格式化显示值"""
        if quality != TagQuality.GOOD or value is None:
            return "  ???  "
        if isinstance(value, bool):
            return "◉ TRUE" if value else "○ FALSE"
        if isinstance(value, float):
            if abs(value) < 0.001 and value != 0:
                return f"{value:.6f}"
            return f"{value:.3f}"
        if isinstance(value, int):
            if abs(value) > 9999:
                return f"{value}  (0x{value & 0xFFFFFFFF:08X})"
            return str(value)
        return str(value)

    # ── 交互 ────────────────────────────────────────────

    def _show_context_menu(self, pos):
        """右键菜单"""
        row = self.table.currentRow()
        if row < 0 or row >= len(self._tags):
            return

        c = current()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {c.menu_bg};
                border: 1px solid {c.menu_border};
                border-radius: 8px;
                padding: 5px;
                color: {c.menu_text};
            }}
            QMenu::item {{
                padding: 8px 32px 8px 16px;
                border-radius: 5px;
                margin: 2px 4px;
            }}
            QMenu::item:selected {{
                background-color: {c.menu_selected_bg};
                color: {c.menu_selected_text};
            }}
            QMenu::separator {{
                height: 1px;
                background: {c.menu_separator};
                margin: 5px 10px;
            }}
        """)

        tag = self._tags[row]

        write_action = QAction("✏️  写入值...", menu)
        write_action.triggered.connect(lambda: self._on_write_value(row))
        menu.addAction(write_action)

        scan_text = "⏸  禁用扫描" if tag.scan_enabled else "▶️  启用扫描"
        scan_action = QAction(scan_text, menu)
        scan_action.triggered.connect(lambda: self._toggle_scan(row))
        menu.addAction(scan_action)

        menu.addSeparator()

        edit_action = QAction("⚙️  编辑标签...", menu)
        edit_action.triggered.connect(lambda: self.tag_edit_requested.emit(row))
        menu.addAction(edit_action)

        del_action = QAction("🗑️  删除标签", menu)
        del_action.triggered.connect(lambda: self.tag_delete_requested.emit(row))
        menu.addAction(del_action)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _on_double_click(self, index):
        self._on_write_value(index.row())

    def _on_write_value(self, row: int):
        """写入值"""
        tag = self._tags[row]
        current_val = self._tag_values.get(row, (None,))[0]

        if tag.data_type == DataType.BOOL:
            new_val = not current_val if isinstance(current_val, bool) else True
            self.write_requested.emit(row, new_val)
            return

        hint = f"当前值: {self._format_value(current_val)}"
        text, ok = QInputDialog.getText(
            self, "✏️ 写入值到 PLC",
            f"{tag.name}  ({tag.address})\n\n{hint}\n\n请输入新值:"
        )
        if ok and text.strip():
            try:
                t = text.strip()
                if tag.data_type in (DataType.INT, DataType.DINT):
                    new_val = int(t)
                elif tag.data_type == DataType.REAL:
                    new_val = float(t)
                elif tag.data_type in (DataType.BYTE, DataType.WORD, DataType.DWORD):
                    if t.startswith(('0x', '0X')):
                        new_val = int(t, 16)
                    else:
                        new_val = int(t)
                else:
                    new_val = int(t)
                self.write_requested.emit(row, new_val)
            except ValueError:
                QMessageBox.warning(self, "错误", f"无法解析输入值: {text}")

    def _toggle_scan(self, row: int):
        self._tags[row].scan_enabled = not self._tags[row].scan_enabled
        name_item = self.table.item(row, self.COL_NAME)
        if name_item:
            c = current()
            if self._tags[row].scan_enabled:
                name_item.setForeground(QBrush(QColor(c.text_primary)))
                name_item.setText(name_item.text().replace("💤", ""))
            else:
                name_item.setForeground(QBrush(QColor(c.text_dim)))
                if "💤" not in name_item.text():
                    name_item.setText(name_item.text().replace("  ", "  💤 "))

    def _toggle_all_scan(self):
        if not self._tags:
            return
        all_on = all(t.scan_enabled for t in self._tags)
        new_state = not all_on
        for tag in self._tags:
            tag.scan_enabled = new_state
        self._refresh_table()
