"""
连接设置面板 - 现代工业风, 大LED指示灯, 卡片式布局
"""
from PyQt6.QtWidgets import (
    QWidget, QGroupBox, QHBoxLayout, QVBoxLayout,
    QLineEdit, QSpinBox, QPushButton, QLabel, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPointF
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QBrush, QPen,
    QRadialGradient, QIntValidator, QPainterPath, QMouseEvent
)
import math
from theme import current, is_light


# ── 手绘箭头按钮 ───────────────────────────────────────

class _SpinArrowButton(QWidget):
    """用 QPainter 绘制的 ▶ 箭头按钮，非文字字符"""
    clicked = pyqtSignal()

    def __init__(self, upward: bool, parent=None):
        super().__init__(parent)
        self._upward = upward
        self._hover = False
        self._pressed = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoFillBackground(False)

    def enterEvent(self, ev):
        self._hover = True
        self.update()

    def leaveEvent(self, ev):
        self._hover = False
        self.update()

    def mousePressEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
            self.clicked.emit()

    def mouseReleaseEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._pressed = False
            self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        c = current()

        # ── 背景（圆角：上按钮圆右上，下按钮圆右下） ──
        if not self.isEnabled():
            bg = QColor(c.spin_btn_disabled_bg)
        elif self._pressed:
            bg = QColor(c.accent_pressed)
        elif self._hover:
            bg = QColor(c.accent_hover)
        else:
            bg = QColor(c.spin_btn_bg)

        p.setBrush(QBrush(bg))
        p.setPen(QPen(QColor(c.border), 1))

        rr = 5  # 圆角半径
        path = QPainterPath()
        if self._upward:
            # 顶部圆角在右上
            path.moveTo(0, h)
            path.lineTo(0, rr)
            path.arcTo(0, 0, rr * 2, rr * 2, 90, 90)
            path.lineTo(w, 0)
            path.lineTo(w, h)
        else:
            # 底部圆角在右下
            path.moveTo(0, 0)
            path.lineTo(0, h)
            path.lineTo(w, h)
            path.lineTo(w, rr)
            path.arcTo(w - rr * 2, h - rr * 2, rr * 2, rr * 2, 0, -90)
        path.closeSubpath()
        p.drawPath(path)

        # ── 箭头 ──
        if not self.isEnabled():
            ac = QColor(c.spin_arrow_disabled)
        elif self._hover or self._pressed:
            ac = QColor(c.white)
        else:
            ac = QColor(c.spin_arrow)

        p.setBrush(QBrush(ac))
        p.setPen(Qt.PenStyle.NoPen)
        cx, cy = w / 2.0, h / 2.0
        arrow = QPainterPath()
        if self._upward:
            arrow.moveTo(cx, cy - 2.5)
            arrow.lineTo(cx + 3.5, cy + 1.8)
            arrow.lineTo(cx - 3.5, cy + 1.8)
        else:
            arrow.moveTo(cx, cy + 2.5)
            arrow.lineTo(cx + 3.5, cy - 1.8)
            arrow.lineTo(cx - 3.5, cy - 1.8)
        arrow.closeSubpath()
        p.drawPath(arrow)
        p.end()


# ── 微调框 ──────────────────────────────────────────

class Spinner(QWidget):
    """自定义微调框：输入框 + 手绘箭头步进按钮"""
    valueChanged = pyqtSignal(int)

    def __init__(self, min_val=0, max_val=9999, default=0, parent=None):
        super().__init__(parent)
        self._min = min_val
        self._max = max_val

        self.setObjectName("spinner")
        self.setFixedHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        c = current()
        self.edit = QLineEdit(str(default))
        self.edit.setObjectName("spinEdit")
        self.edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit.setValidator(QIntValidator(min_val, max_val))
        self.edit.editingFinished.connect(self._on_edit)
        self.edit.setStyleSheet(
            f"QLineEdit {{ font-size: 13px; font-weight: 600; padding: 0 6px; "
            f"background: {c.bg_input}; border: 1px solid {c.border}; "
            f"border-right: none; border-radius: 6px 0 0 6px; "
            f"color: {c.text_primary}; font-family: 'Consolas', monospace; }}"
        )
        layout.addWidget(self.edit, stretch=1)

        btn_area = QVBoxLayout()
        btn_area.setContentsMargins(0, 0, 0, 0)
        btn_area.setSpacing(0)

        self.btn_up = _SpinArrowButton(upward=True)
        self.btn_up.setFixedSize(28, 17)
        self.btn_up.setToolTip("增加")
        self.btn_up.clicked.connect(self._step_up)
        btn_area.addWidget(self.btn_up)

        self.btn_down = _SpinArrowButton(upward=False)
        self.btn_down.setFixedSize(28, 17)
        self.btn_down.setToolTip("减少")
        self.btn_down.clicked.connect(self._step_down)
        btn_area.addWidget(self.btn_down)

        layout.addLayout(btn_area)

    def value(self):
        try:
            return int(self.edit.text())
        except ValueError:
            return self._min

    def setValue(self, v):
        self.edit.setText(str(max(self._min, min(self._max, v))))

    def setRange(self, lo, hi):
        self._min = lo
        self._max = hi

    def setEnabled(self, en):
        self.edit.setEnabled(en)
        self.btn_up.setEnabled(en)
        self.btn_down.setEnabled(en)

    def _step_up(self):
        v = min(self._max, self.value() + 1)
        self.edit.setText(str(v))
        self.valueChanged.emit(v)

    def _step_down(self):
        v = max(self._min, self.value() - 1)
        self.edit.setText(str(v))
        self.valueChanged.emit(v)

    def _on_edit(self):
        v = self.value()
        self.valueChanged.emit(v)


class LedIndicator(QWidget):
    """大号 LED 状态指示灯 - 带光晕效果"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor(current().led_red)  # 红 = 断开
        self._pulse = False
        self._pulse_phase = 0.0
        self.setFixedSize(22, 22)

        # 脉冲动画
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse_tick)
        self._timer.setInterval(50)

    def set_color(self, color: str, pulse: bool = False):
        self._color = QColor(color)
        self._pulse = pulse
        if pulse:
            self._timer.start()
        else:
            self._timer.stop()
            self._pulse_phase = 0.0
        self.update()

    def _pulse_tick(self):
        self._pulse_phase += 0.12
        if self._pulse_phase > 2 * math.pi:
            self._pulse_phase = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = 11, 11  # 中心
        r = 8  # 主体半径

        # ── 外光晕 ──
        if self._pulse:
            alpha = int(50 + 30 * math.sin(self._pulse_phase))
            glow = QRadialGradient(cx, cy, 11)
            glow_color = QColor(self._color)
            glow_color.setAlpha(alpha)
            glow.setColorAt(0, glow_color)
            glow_color.setAlpha(0)
            glow.setColorAt(1, glow_color)
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(cx - 11, cy - 11, 22, 22)

        # ── 主体 ──
        body = QRadialGradient(cx - 2, cy - 3, r)
        body.setColorAt(0, QColor(255, 255, 255, 80))
        body.setColorAt(0.4, self._color.lighter(150))
        body.setColorAt(0.8, self._color)
        body.setColorAt(1, self._color.darker(130))
        painter.setBrush(QBrush(body))
        painter.setPen(QPen(self._color.darker(150), 1))
        painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        # ── 高光点 ──
        highlight = QRadialGradient(cx - 2, cy - 5, 3)
        highlight.setColorAt(0, QColor(255, 255, 255, 160))
        highlight.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(highlight))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(cx - 3, cy - 5, 6, 4)

        painter.end()


class ConnectionPanel(QGroupBox):
    """PLC 连接设置面板 - 精工设计"""

    connect_requested = pyqtSignal(str, int, int)   # ip, rack, slot
    disconnect_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("PLC 连接", parent)
        self._connected = False
        self._setup_ui()

    def _setup_ui(self):
        c = current()
        LBL = f"color: {c.text_secondary}; font-size: 11px; font-weight: 600;"

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(14, 20, 14, 12)

        # ═══════════════════════════════════════════
        #  LED + 状态 + IP
        # ═══════════════════════════════════════════
        status_card = QFrame()
        status_card.setObjectName("panelCard")
        sc = QHBoxLayout(status_card)
        sc.setContentsMargins(14, 12, 14, 12)
        sc.setSpacing(12)

        self.led = LedIndicator()
        sc.addWidget(self.led)

        v = QVBoxLayout()
        v.setSpacing(2)
        self.ip_display = QLabel("192.168.0.1")
        self.ip_display.setObjectName("ipDisplay")
        v.addWidget(self.ip_display)
        self.status_label = QLabel("未连接")
        self.status_label.setObjectName("statusDisconnected")
        v.addWidget(self.status_label)
        sc.addLayout(v, stretch=1)

        self.plc_type_label = QLabel("")
        self.plc_type_label.setStyleSheet(
            f"color:{c.text_dim}; font-size:10px; font-weight:500;")
        sc.addWidget(self.plc_type_label)
        layout.addWidget(status_card)

        # ═══════════════════════════════════════════
        #  IP 地址
        # ═══════════════════════════════════════════
        self.ip_input = QLineEdit("192.168.0.1")
        self.ip_input.setPlaceholderText("PLC IP 地址...")
        self.ip_input.setMinimumHeight(38)
        layout.addWidget(self.ip_input)

        # ═══════════════════════════════════════════
        #  Rack / Slot / 扫描间隔
        # ═══════════════════════════════════════════
        grid = QHBoxLayout()
        grid.setSpacing(12)

        self.rack_spin = Spinner(0, 31, 0)
        self.rack_spin.setToolTip("S7-1200 → 0\nS7-1500 → 0")
        grid.addWidget(self._labeled("Rack", self.rack_spin, LBL), stretch=1)

        self.slot_spin = Spinner(0, 31, 1)
        self.slot_spin.setToolTip("S7-1200 → 1\nS7-1500 → 1")
        grid.addWidget(self._labeled("Slot", self.slot_spin, LBL), stretch=1)

        self.scan_spin = Spinner(50, 10000, 500)
        self.scan_spin.setToolTip("数据刷新间隔 (ms)")
        grid.addWidget(self._labeled("扫描间隔", self.scan_spin, LBL), stretch=2)
        layout.addLayout(grid)

        # ═══════════════════════════════════════════
        #  按钮
        # ═══════════════════════════════════════════
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_connect = QPushButton("🔌  连接 PLC")
        self.btn_connect.setObjectName("btnConnect")
        self.btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_connect.setMinimumHeight(40)
        self.btn_connect.clicked.connect(self._on_connect_clicked)

        self.btn_disconnect = QPushButton("⏻  断开连接")
        self.btn_disconnect.setObjectName("btnDisconnect")
        self.btn_disconnect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_disconnect.setMinimumHeight(40)
        self.btn_disconnect.clicked.connect(self._on_disconnect_clicked)
        self.btn_disconnect.setVisible(False)

        btn_row.addWidget(self.btn_connect)
        btn_row.addWidget(self.btn_disconnect)
        layout.addLayout(btn_row)

        # ═══════════════════════════════════════════
        #  PLC 信息
        # ═══════════════════════════════════════════
        self.info_label = QLabel("")
        self.info_label.setStyleSheet(
            f"color: {c.text_dim}; font-size: 10.5px; padding: 2px 4px;")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        layout.addStretch()

    @staticmethod
    def _labeled(title: str, widget: QWidget, lbl_style: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lb = QLabel(title)
        lb.setStyleSheet(lbl_style)
        lay.addWidget(lb)
        lay.addWidget(widget)
        return w

    def _on_connect_clicked(self):
        ip = self.ip_input.text().strip()
        if not ip:
            return
        self.btn_connect.setEnabled(False)
        self.btn_connect.setText("⏳  连接中...")
        self.connect_requested.emit(
            ip, self.rack_spin.value(), self.slot_spin.value()
        )

    def _on_disconnect_clicked(self):
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.setText("⏳  断开中...")
        self.disconnect_requested.emit()

    def set_status(self, connected: bool, ip_or_msg: str = ""):
        self._connected = connected
        if connected:
            self.led.set_color(current().led_green, True)
            self.status_label.setText(" 已连接")
            self.status_label.setObjectName("statusConnected")
            self.ip_display.setText(ip_or_msg or self.ip_input.text().strip())
            self.ip_display.setObjectName("ipConnected")
            self.ip_input.setText(self.ip_display.text())
            self.btn_connect.setVisible(False)
            self.btn_disconnect.setVisible(True)
            self.btn_disconnect.setEnabled(True)
            self.btn_disconnect.setText(" 断开连接")
            self.ip_input.setEnabled(False)
            self.rack_spin.setEnabled(False)
            self.slot_spin.setEnabled(False)
        else:
            self.led.set_color(current().led_red, False)
            self.status_label.setText(ip_or_msg or " 未连接")
            self.status_label.setObjectName("statusDisconnected")
            self.ip_display.setObjectName("ipDisconnected")
            self.btn_connect.setVisible(True)
            self.btn_connect.setEnabled(True)
            self.btn_connect.setText(" 连接 PLC")
            self.btn_disconnect.setVisible(False)
            self.ip_input.setEnabled(True)
            self.rack_spin.setEnabled(True)
            self.slot_spin.setEnabled(True)

        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def set_plc_info(self, module: str, version: str, serial: str):
        """显示 PLC 信息"""
        parts = [f"型号: {module}"]
        if version:
            parts.append(f"固件: {version}")
        self.plc_type_label.setText(" | ".join(parts))
        if serial:
            self.info_label.setText(f"S/N: {serial}")

    def set_connection_error(self, error: str):
        self.set_status(False, " 连接失败")
        self.info_label.setText(f"错误: {error[:80]}")

    def get_scan_interval(self) -> int:
        return self.scan_spin.value()
