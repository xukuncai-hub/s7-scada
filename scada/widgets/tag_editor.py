"""
标签编辑器 - 添加/编辑 S7 标签配置
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QCheckBox, QPushButton,
    QLabel, QGroupBox, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt

from tag_config import (
    TagConfig, DataType, Area, parse_address, DATA_TYPE_SIZES
)
from theme import current, is_light


# S7-1200/1500 预置组名
PRESET_GROUPS = [
    "Default", "Digital Inputs", "Digital Outputs",
    "Analog Inputs", "Analog Outputs", "Alarms",
    "Parameters", "Production Data"
]


class TagEditorDialog(QDialog):
    """标签添加/编辑对话框"""

    def __init__(self, parent=None, tag: TagConfig = None):
        super().__init__(parent)
        self._edit_tag = tag
        self._result_tag = None
        self._setup_ui()

        if tag:
            self.setWindowTitle("编辑标签")
            self._fill_from_tag(tag)
        else:
            self.setWindowTitle("添加标签")

    def _setup_ui(self):
        self.setMinimumSize(480, 420)

        c = current()
        self.setStyleSheet(f"""
            QDialog {{ background: {c.bg_panel}; color: {c.text_primary}; }}
            QLabel {{ color: {c.text_primary}; background: transparent; font-size: 13px; }}
            QLabel#dlgTitle {{ font-size: 17px; font-weight: 700; color: {c.dlg_title}; }}
            QFormLayout QLabel {{ color: {c.text_secondary}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("标签配置")
        title.setObjectName("dlgTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("例如: Motor_Run_Status")
        form.addRow("名称:", self.name_input)

        self.addr_input = QLineEdit()
        self.addr_input.setPlaceholderText("例如: DB1.DBW0, M0.0, I0.0, Q0.0")
        self.addr_input.textChanged.connect(self._on_address_changed)
        form.addRow("地址:", self.addr_input)

        self.type_combo = QComboBox()
        for dt in DataType:
            size = DATA_TYPE_SIZES.get(dt, 0)
            self.type_combo.addItem(f"{dt.value} ({size}B)", dt)
        form.addRow("数据类型:", self.type_combo)

        self.group_combo = QComboBox()
        self.group_combo.setEditable(True)
        self.group_combo.addItems(PRESET_GROUPS)
        self.group_combo.setCurrentText("Default")
        form.addRow("分组:", self.group_combo)

        self.comment_input = QLineEdit()
        self.comment_input.setPlaceholderText("备注信息（可选）")
        form.addRow("备注:", self.comment_input)

        self.scan_check = QCheckBox("启用扫描")
        self.scan_check.setChecked(True)
        form.addRow("", self.scan_check)

        layout.addLayout(form)

        self.preview_group = QGroupBox("地址解析")
        self.preview_layout = QVBoxLayout(self.preview_group)
        self.preview_label = QLabel("输入地址后自动解析...")
        self.preview_label.setWordWrap(True)
        self.preview_layout.addWidget(self.preview_label)
        layout.addWidget(self.preview_group)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.ok_btn = QPushButton("确认")
        self.ok_btn.setObjectName("btnConnect")
        self.ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(self.ok_btn)
        layout.addLayout(btn_layout)

    def _on_address_changed(self, text: str):
        result = parse_address(text)
        c = current()
        GREEN, RED, DIM, BORDER = c.success, c.danger, c.text_secondary, c.border

        if result:
            lines = [
                f"区域: {result['area'].prefix}",
                f"类型: {result['data_type'].value}",
                f"DB: {result['db_number']}",
                f"偏移: {result['byte_offset']}",
            ]
            if result.get('bit_offset') and result['data_type'] == DataType.BOOL:
                lines.append(f"位: {result['bit_offset']}")
            self.preview_label.setText("  |  ".join(lines))
            self.preview_label.setStyleSheet(f"color:{GREEN}; font-size:12px;")
            self.preview_group.setStyleSheet(
                f"QGroupBox {{ border:1px solid {GREEN}; border-radius:6px; "
                f"margin-top:10px; padding:10px; background:transparent; "
                f"font-size:12px; color:{GREEN}; }} "
                f"QGroupBox::title {{ color:{GREEN}; }}")
            if result['data_type']:
                idx = self.type_combo.findData(result['data_type'])
                if idx >= 0:
                    self.type_combo.setCurrentIndex(idx)
        elif text.strip():
            self.preview_label.setText("无法解析地址，请检查格式")
            self.preview_label.setStyleSheet(f"color:{RED}; font-size:12px;")
            self.preview_group.setStyleSheet(
                f"QGroupBox {{ border:1px solid {RED}; border-radius:6px; "
                f"margin-top:10px; padding:10px; background:transparent; "
                f"font-size:12px; color:{RED}; }} "
                f"QGroupBox::title {{ color:{RED}; }}")
        else:
            self.preview_label.setText("输入地址后自动解析...")
            self.preview_label.setStyleSheet(f"color:{DIM}; font-size:12px;")
            self.preview_group.setStyleSheet(
                f"QGroupBox {{ border:1px solid {BORDER}; border-radius:6px; "
                f"margin-top:10px; padding:10px; background:transparent; "
                f"font-size:12px; color:{DIM}; }} "
                f"QGroupBox::title {{ color:{DIM}; }}")

    def _on_ok(self):
        """确认添加"""
        name = self.name_input.text().strip()
        address = self.addr_input.text().strip().upper()

        if not name:
            QMessageBox.warning(self, "警告", "请输入标签名称")
            return
        if not address:
            QMessageBox.warning(self, "警告", "请输入标签地址")
            return

        parsed = parse_address(address)
        if not parsed:
            QMessageBox.warning(
                self, "警告",
                f"无法解析地址: {address}\n\n"
                "支持的格式:\n"
                "  DB 区: DB1.DBX0.0, DB1.DBW2, DB1.DBD4\n"
                "  M 区:  M0.0, MW2, MD4, MB10\n"
                "  I 区:  I0.0, IW2, ID4\n"
                "  Q 区:  Q0.0, QW2, QD4"
            )
            return

        data_type = self.type_combo.currentData()
        group = self.group_combo.currentText().strip() or "Default"

        self._result_tag = TagConfig(
            name=name,
            address=address,
            area=parsed['area'],
            data_type=data_type,
            db_number=parsed['db_number'],
            byte_offset=parsed['byte_offset'],
            bit_offset=parsed.get('bit_offset', 0),
            group=group,
            scan_enabled=self.scan_check.isChecked(),
            comment=self.comment_input.text().strip()
        )
        self.accept()

    def get_tag(self) -> TagConfig:
        return self._result_tag

    def _fill_from_tag(self, tag: TagConfig):
        """编辑已有标签时填充表单"""
        self.name_input.setText(tag.name)
        self.addr_input.setText(tag.address)
        self.addr_input.setEnabled(False)  # 地址不可改
        idx = self.type_combo.findData(tag.data_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.group_combo.setCurrentText(tag.group)
        self.comment_input.setText(tag.comment)
        self.scan_check.setChecked(tag.scan_enabled)
