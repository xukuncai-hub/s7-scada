"""
S7 标签配置数据模型 - 地址解析、数据类型定义
支持 S7-1200/1500 地址格式
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import re
import struct


class DataType(Enum):
    """S7 数据类型"""
    BOOL = "Bool"
    BYTE = "Byte"
    WORD = "Word"
    DWORD = "DWord"
    INT = "Int"
    DINT = "DInt"
    REAL = "Real"


class TagQuality(Enum):
    """标签数据质量"""
    GOOD = "Good"
    BAD = "Bad"
    UNKNOWN = "Unknown"


class Area(Enum):
    """S7 内存区域"""
    DB = ("DB", 0x84)
    M = ("M", 0x83)
    I = ("I", 0x81)
    Q = ("Q", 0x82)
    T = ("T", 0x1D)
    C = ("C", 0x1C)

    def __init__(self, prefix: str, code: int):
        self.prefix = prefix
        self.code = code


@dataclass
class TagConfig:
    """单个标签的完整配置"""
    name: str
    address: str           # 完整地址，如 DB1.DBW0, M0.0, I0.0
    area: Area
    data_type: DataType
    db_number: int = 0
    byte_offset: int = 0
    bit_offset: int = 0    # 仅 BOOL 类型使用
    group: str = "Default"
    scan_enabled: bool = True
    comment: str = ""

    # 运行时数据
    value: Any = None
    quality: TagQuality = TagQuality.UNKNOWN
    timestamp: str = ""

    @property
    def byte_length(self) -> int:
        """返回该类型占用的字节数"""
        return DATA_TYPE_SIZES[self.data_type]

    @property
    def display_name(self) -> str:
        """树形列表中的显示名"""
        return f"{self.name} ({self.address})"


# 数据类型 → 字节数
DATA_TYPE_SIZES = {
    DataType.BOOL: 1,
    DataType.BYTE: 1,
    DataType.WORD: 2,
    DataType.INT: 2,
    DataType.DWORD: 4,
    DataType.DINT: 4,
    DataType.REAL: 4,
}


def parse_address(address: str) -> Optional[dict]:
    """
    解析 S7 地址字符串，返回各组成部分。

    支持格式:
        DB 区: DB1.DBX0.0, DB1.DBW2, DB1.DBD4, DB1.DBB0
        M 区:  M0.0, MW2, MD4, MB10
        I 区:  I0.0, IW2, ID4, IB10
        Q 区:  Q0.0, QW2, QD4, QB10
        T 区:  T0, TW2
        C 区:  C0, CW2

    返回 None 表示解析失败。
    """
    if not address or not isinstance(address, str):
        return None

    address = address.strip().upper()

    # DB 区地址: DB<num>.DB<type><offset>[.<bit>]
    db_match = re.match(
        r'^DB(\d+)\.(DB[WXDB]\d+)(?:\.(\d+))?$', address
    )
    if db_match:
        db_num = int(db_match.group(1))
        suffix = db_match.group(2)  # e.g., "DBW0", "DBX2.0"
        bit_part = db_match.group(3)  # e.g., "0" for DBX2.0

        # 解析 DBW/DBD/DBB/DBX
        type_match = re.match(r'^DB([WXDB])(\d+)$', suffix)
        if type_match:
            type_char = type_match.group(1)
            offset = int(type_match.group(2))
            area = Area.DB
            db_num = db_num
            byte_offset = offset

            if type_char == 'X':
                data_type = DataType.BOOL
                bit_offset = int(bit_part) if bit_part else 0
                return {
                    'area': area,
                    'data_type': data_type,
                    'db_number': db_num,
                    'byte_offset': byte_offset,
                    'bit_offset': bit_offset,
                    'raw': address
                }
            elif type_char == 'B':
                return {
                    'area': area, 'data_type': DataType.BYTE,
                    'db_number': db_num, 'byte_offset': offset,
                    'bit_offset': 0, 'raw': address
                }
            elif type_char == 'W':
                return {
                    'area': area, 'data_type': DataType.WORD,
                    'db_number': db_num, 'byte_offset': offset,
                    'bit_offset': 0, 'raw': address
                }
            elif type_char == 'D':
                return {
                    'area': area, 'data_type': DataType.DWORD,
                    'db_number': db_num, 'byte_offset': offset,
                    'bit_offset': 0, 'raw': address
                }

    # DB 简化格式: DB<num> (仅 DB 编号，不带数据类型)
    db_simple = re.match(r'^DB(\d+)$', address)
    if db_simple:
        return {
            'area': Area.DB, 'data_type': DataType.BYTE,
            'db_number': int(db_simple.group(1)),
            'byte_offset': 0, 'bit_offset': 0, 'raw': address
        }

    # 非 DB 区: <area_prefix><type_char><offset>[.<bit>]
    # 如: M0.0, MW2, MD4, MB10, I0.0, Q0.0
    non_db = re.match(
        r'^([MIQTC])([WXDB])?(\d+)(?:\.(\d+))?$', address
    )
    if non_db:
        area_prefix = non_db.group(1)
        type_char = non_db.group(2)  # None for bit addresses like M0.0
        offset = int(non_db.group(3))
        bit_part = non_db.group(4)  # e.g., "0" for M0.0

        # Map area prefix
        area_map = {a.prefix: a for a in Area}
        area = area_map.get(area_prefix)
        if area is None:
            return None

        # 没有 type_char 但有 bit_part → Bool 位地址 (如 M0.0)
        if type_char is None and bit_part is not None:
            return {
                'area': area, 'data_type': DataType.BOOL,
                'db_number': 0, 'byte_offset': offset,
                'bit_offset': int(bit_part), 'raw': address
            }
        # 没有 type_char 也没有 bit_part → 默认 Word (如 T0, C0, MW10?? no MW has W)
        elif type_char is None and bit_part is None:
            # 可能是 T0, C0 等
            return {
                'area': area, 'data_type': DataType.WORD,
                'db_number': 0, 'byte_offset': offset,
                'bit_offset': 0, 'raw': address
            }
        # 有 type_char
        elif type_char is not None:
            byte_offset = offset
            if type_char == 'X':
                return {
                    'area': area, 'data_type': DataType.BOOL,
                    'db_number': 0, 'byte_offset': offset,
                    'bit_offset': int(bit_part) if bit_part else 0,
                    'raw': address
                }
            elif type_char == 'B':
                return {
                    'area': area, 'data_type': DataType.BYTE,
                    'db_number': 0, 'byte_offset': offset,
                    'bit_offset': 0, 'raw': address
                }
            elif type_char == 'W':
                return {
                    'area': area, 'data_type': DataType.WORD,
                    'db_number': 0, 'byte_offset': offset,
                    'bit_offset': 0, 'raw': address
                }
            elif type_char == 'D':
                return {
                    'area': area, 'data_type': DataType.DWORD,
                    'db_number': 0, 'byte_offset': offset,
                    'bit_offset': 0, 'raw': address
                }

    return None


def parse_bytes(data: bytes, data_type: DataType, bit_offset: int = 0) -> Any:
    """将 S7 原始字节数据解析为 Python 值"""
    try:
        if data_type == DataType.BOOL:
            if len(data) == 0:
                return None
            return bool(data[0] & (1 << bit_offset))
        elif data_type == DataType.BYTE:
            return data[0] if len(data) > 0 else None
        elif data_type == DataType.WORD:
            return struct.unpack('>H', data[:2])[0] if len(data) >= 2 else None
        elif data_type == DataType.INT:
            return struct.unpack('>h', data[:2])[0] if len(data) >= 2 else None
        elif data_type == DataType.DWORD:
            return struct.unpack('>I', data[:4])[0] if len(data) >= 4 else None
        elif data_type == DataType.DINT:
            return struct.unpack('>i', data[:4])[0] if len(data) >= 4 else None
        elif data_type == DataType.REAL:
            return round(struct.unpack('>f', data[:4])[0], 6) if len(data) >= 4 else None
    except (struct.error, IndexError):
        return None
    return None


def value_to_bytes(value: Any, data_type: DataType, bit_offset: int = 0) -> Optional[bytes]:
    """将 Python 值转换为 S7 可写的字节数据"""
    try:
        if data_type == DataType.BOOL:
            val = 1 if value else 0
            return bytes([val << bit_offset])
        elif data_type == DataType.BYTE:
            return bytes([int(value) & 0xFF])
        elif data_type == DataType.WORD:
            return struct.pack('>H', int(value) & 0xFFFF)
        elif data_type == DataType.INT:
            return struct.pack('>h', int(value))
        elif data_type == DataType.DWORD:
            return struct.pack('>I', int(value) & 0xFFFFFFFF)
        elif data_type == DataType.DINT:
            return struct.pack('>i', int(value))
        elif data_type == DataType.REAL:
            return struct.pack('>f', float(value))
    except (struct.error, ValueError, TypeError):
        return None
    return None
