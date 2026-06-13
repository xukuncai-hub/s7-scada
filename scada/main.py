
"""
S7 SCADA - S7-1200/1500 PLC 上位机
入口文件
"""
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from s7_app import S7App


def load_stylesheet(app: QApplication) -> str:
    """加载 QSS 样式表 — 默认浅色"""
    style_path = Path(__file__).parent / "style_light.qss"
    if not style_path.exists():
        return ""

    with open(style_path, 'r', encoding='utf-8') as f:
        qss = f.read()
    return qss


def main():
    # 高 DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("S7 SCADA")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("SCADA")

    # 加载样式
    qss = load_stylesheet(app)
    if qss:
        app.setStyleSheet(qss)

    # 创建并显示主窗口
    window = S7App()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
