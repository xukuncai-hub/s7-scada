"""
统一主题管理 — 深色 / 浅色 双模式颜色定义
所有硬编码颜色应从这里引用，通过 is_light() 检测当前主题
"""
from __future__ import annotations
from dataclasses import dataclass, field
from PyQt6.QtWidgets import QApplication


# ═══════════════════════════════════════════════════════════
#  颜色集
# ═══════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ThemeColors:
    """语义化颜色令牌 — 浅色 & 深色各一份"""

    # ── 基础色 ──
    bg_deep: str          # 最底层背景
    bg_panel: str         # 面板 / 卡片背景
    bg_card: str          # 次级卡片背景
    bg_input: str         # 输入框背景
    bg_input_focus: str   # 输入框聚焦微光
    border: str           # 默认边框
    border_hover: str     # 悬停边框
    text_primary: str     # 主文字
    text_secondary: str   # 次文字
    text_dim: str         # 弱文字
    accent: str           # 强调蓝
    accent_hover: str     # 悬停蓝
    accent_pressed: str   # 按压蓝
    success: str          # 良好绿
    danger: str           # 故障红
    warning: str          # 警告橙
    disabled: str         # 禁用态文字
    white: str            # 纯白

    # ── 区域色 (bg, accent) ──
    area_db: tuple[str, str]      # DB 区
    area_m: tuple[str, str]       # M 区
    area_i: tuple[str, str]       # I 区
    area_q: tuple[str, str]       # Q 区
    area_tc: tuple[str, str]      # T / C 区

    # ── 数据类型色 ──
    type_bool: str
    type_byte: str
    type_word: str
    type_dword: str
    type_int: str
    type_dint: str
    type_real: str

    # ── 表格 ──
    table_bg: str
    table_grid: str
    table_header_bg: str
    table_row_hover: str
    table_selection: str
    table_text_dim: str        # 占位文字

    # ── 微调框按钮 ──
    spin_btn_bg: str
    spin_arrow: str
    spin_btn_disabled_bg: str
    spin_arrow_disabled: str

    # ── LED 指示灯 ──
    led_green: str
    led_red: str

    # ── 卡片 / 提示区 ──
    card_empty_text: str
    card_empty_bg: str
    card_empty_border: str
    warn_card_bg: str
    warn_card_border: str
    warn_title: str
    warn_body: str
    info_card_bg: str
    info_card_border: str
    info_title: str
    info_body: str

    # ── 对话框 ──
    dlg_bg: str
    dlg_title: str
    dlg_subtitle: str
    dlg_info: str
    dlg_copy: str

    # ── 上下文菜单 ──
    menu_bg: str
    menu_border: str
    menu_text: str
    menu_selected_bg: str
    menu_selected_text: str
    menu_separator: str


# ═══════════════════════════════════════════════════════════
#  深色主题
# ═══════════════════════════════════════════════════════════

DARK = ThemeColors(
    bg_deep="#1a1d23",
    bg_panel="#21252d",
    bg_card="#282c35",
    bg_input="#181b21",
    bg_input_focus="rgba(64, 136, 232, 0.06)",
    border="#353a46",
    border_hover="#454a58",
    text_primary="#e0e3ea",
    text_secondary="#8b909e",
    text_dim="#5d6370",
    accent="#4088e8",
    accent_hover="#4088e8",
    accent_pressed="#3078d8",
    success="#40c868",
    danger="#e05050",
    warning="#e89840",
    disabled="#4d5460",
    white="#ffffff",

    area_db=("#1a3050", "#4088e8"),
    area_m=("#1a3820", "#40c868"),
    area_i=("#3a2810", "#e89840"),
    area_q=("#381818", "#e05050"),
    area_tc=("#281840", "#a858e8"),

    type_bool="#e89840",
    type_byte="#a858e8",
    type_word="#58b8e0",
    type_dword="#4088e8",
    type_int="#40c868",
    type_dint="#40c868",
    type_real="#e87080",

    table_bg="#1f2229",
    table_grid="#262a33",
    table_header_bg="#1c1f26",
    table_row_hover="#262a33",
    table_selection="#2858a8",
    table_text_dim="#4a5464",

    spin_btn_bg="#2d3240",
    spin_arrow="#8b909e",
    spin_btn_disabled_bg="#1f2229",
    spin_arrow_disabled="#4d5460",

    led_green="#40c868",
    led_red="#e05050",

    card_empty_text="#4a5464",
    card_empty_bg="#0b1019",
    card_empty_border="#1a2336",
    warn_card_bg="#2a2218",
    warn_card_border="#4a3820",
    warn_title="#d89830",
    warn_body="#b08028",
    info_card_bg="#21252d",
    info_card_border="#2e3340",
    info_title="#b0b6c2",
    info_body="#8b909e",

    dlg_bg="#21252d",
    dlg_title="#ffffff",
    dlg_subtitle="#8b909e",
    dlg_info="#b0b6c2",
    dlg_copy="#5d6370",

    menu_bg="#1a1f2e",
    menu_border="#2d3648",
    menu_text="#e2e8f0",
    menu_selected_bg="#2563eb",
    menu_selected_text="#ffffff",
    menu_separator="#2d3648",
)


# ═══════════════════════════════════════════════════════════
#  浅色主题
# ═══════════════════════════════════════════════════════════

LIGHT = ThemeColors(
    bg_deep="#f0f1f4",
    bg_panel="#fafbfd",
    bg_card="#ffffff",
    bg_input="#ffffff",
    bg_input_focus="rgba(48, 120, 216, 0.04)",
    border="#d8dbe2",
    border_hover="#a0a8b4",
    text_primary="#1c1e23",
    text_secondary="#5e6370",
    text_dim="#9095a0",
    accent="#3078d8",
    accent_hover="#4088e8",
    accent_pressed="#2868c0",
    success="#28a840",
    danger="#d03030",
    warning="#c87020",
    disabled="#b0b6c0",
    white="#ffffff",

    area_db=("#e0ecfa", "#3078d8"),
    area_m=("#e0f5e8", "#28a840"),
    area_i=("#fdf0e0", "#c87020"),
    area_q=("#fae0e0", "#d03030"),
    area_tc=("#ece0f8", "#8038c0"),

    type_bool="#c87020",
    type_byte="#8038c0",
    type_word="#3088c0",
    type_dword="#3078d8",
    type_int="#28a840",
    type_dint="#28a840",
    type_real="#d04060",

    table_bg="#ffffff",
    table_grid="#eceef2",
    table_header_bg="#f2f3f6",
    table_row_hover="#f5f6f8",
    table_selection="#3078d8",
    table_text_dim="#9095a0",

    spin_btn_bg="#eceef2",
    spin_arrow="#5e6370",
    spin_btn_disabled_bg="#f5f6f8",
    spin_arrow_disabled="#b0b6c0",

    led_green="#28a840",
    led_red="#d03030",

    card_empty_text="#9095a0",
    card_empty_bg="#f5f6f8",
    card_empty_border="#d8dbe2",
    warn_card_bg="#fdf5e6",
    warn_card_border="#e8d8b8",
    warn_title="#b06818",
    warn_body="#8a5010",
    info_card_bg="#ffffff",
    info_card_border="#e0e3e8",
    info_title="#4a4f5a",
    info_body="#5e6370",

    dlg_bg="#ffffff",
    dlg_title="#1c1e23",
    dlg_subtitle="#5e6370",
    dlg_info="#4a4f5a",
    dlg_copy="#9095a0",

    menu_bg="#ffffff",
    menu_border="#d8dbe2",
    menu_text="#1c1e23",
    menu_selected_bg="#3078d8",
    menu_selected_text="#ffffff",
    menu_separator="#e4e6ec",
)


# ═══════════════════════════════════════════════════════════
#  公共 API
# ═══════════════════════════════════════════════════════════

def is_light() -> bool:
    """检测当前是否为浅色主题"""
    qss = QApplication.instance().styleSheet()
    if not qss:
        return True  # 默认浅色
    return "#f0f1f4" in qss


def current() -> ThemeColors:
    """获取当前主题颜色集"""
    return LIGHT if is_light() else DARK


def area_colors() -> dict:
    """返回当前主题的区域色映射 {prefix: (bg, accent)}"""
    c = current()
    return {
        "DB": c.area_db,
        "M": c.area_m,
        "I": c.area_i,
        "Q": c.area_q,
        "T": c.area_tc,
        "C": c.area_tc,
    }


def type_colors() -> dict:
    """返回当前主题的数据类型色映射 {type_value: color}"""
    c = current()
    return {
        "Bool": c.type_bool,
        "Byte": c.type_byte,
        "Word": c.type_word,
        "DWord": c.type_dword,
        "Int": c.type_int,
        "DInt": c.type_dint,
        "Real": c.type_real,
    }
