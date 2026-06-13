"""
PLC 后台通信线程 - 基于 python-snap7
负责连接管理、批量读取、数据解析、断线重连
"""
from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition
from datetime import datetime
from typing import Any, Optional
import logging
import re

from snap7 import Client as Snap7Client
from snap7.error import (
    S7Error, S7ConnectionError, S7TimeoutError,
    S7ProtocolError, S7StalePacketError
)

from tag_config import (
    TagConfig, DataType, TagQuality, Area,
    parse_bytes, value_to_bytes, DATA_TYPE_SIZES
)

logger = logging.getLogger(__name__)


class PlcWorker(QThread):
    """PLC 通信后台线程"""

    # 连接状态信号
    connected = pyqtSignal()
    disconnected = pyqtSignal(str)          # 断开原因
    connection_error = pyqtSignal(str)      # 连接错误消息
    plc_info = pyqtSignal(str, str, str)    # 模块名, 版本, 序列号

    # 数据信号
    data_updated = pyqtSignal(list)         # [(tag_index, value, quality, timestamp)]
    write_result = pyqtSignal(int, bool, str)  # tag_index, success, message

    # 状态信号
    scan_time = pyqtSignal(float)           # 本次扫描耗时(ms)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._client = Snap7Client()
        self._tags: list[TagConfig] = []
        self._ip = "192.168.0.1"
        self._rack = 0
        self._slot = 1
        self._scan_interval = 500           # ms
        self._running = False
        self._paused = False
        self._mutex = QMutex()
        self._condition = QWaitCondition()

        # 连接重试参数
        self._auto_reconnect = True
        self._reconnect_interval = 3000     # ms

    # ── 属性 ────────────────────────────────────────────

    @property
    def is_plc_connected(self) -> bool:
        return self._client.get_connected()

    @property
    def ip(self) -> str:
        return self._ip

    @property
    def rack(self) -> int:
        return self._rack

    @property
    def slot(self) -> int:
        return self._slot

    @property
    def scan_interval(self) -> int:
        return self._scan_interval

    # ── 公共接口（主线程调用，线程安全） ────────────────

    def set_connection(self, ip: str, rack: int = 0, slot: int = 1):
        """设置连接参数（需在连接前调用）"""
        self._ip = ip
        self._rack = rack
        self._slot = slot

    def set_tags(self, tags: list[TagConfig]):
        """设置要扫描的标签列表"""
        self._mutex.lock()
        self._tags = tags.copy()
        self._mutex.unlock()

    def set_scan_interval(self, interval_ms: int):
        """设置扫描间隔 (ms)"""
        self._scan_interval = max(50, interval_ms)

    def connect_plc(self):
        """
        连接到 PLC。
        由于 snap7 连接是阻塞操作，这里发出信号让 run() 执行。
        """
        if not self.isRunning():
            self._running = True
            self._paused = False
            self.start()
        else:
            # 已经在运行，触发重连
            self._paused = False
            self._condition.wakeAll()

    def disconnect_plc(self):
        """断开 PLC 连接并停止扫描"""
        self._paused = True
        self._running = False
        self._condition.wakeAll()
        if self.isRunning():
            self.wait(3000)  # 等待线程退出

    def request_write(self, tag_index: int, value: Any):
        """请求写入值到 PLC（在线程中执行）"""
        # 写入操作在主循环的下一个周期处理
        # 通过队列方式：这里简化实现，直接在内部处理
        pass

    def stop(self):
        """停止线程"""
        self._running = False
        self._condition.wakeAll()
        if self.isRunning():
            self.wait(5000)

    # ── PLC 信息识别 ────────────────────────────────────

    def _fetch_plc_info(self):
        """三级抓取 PLC 信息，合并最优结果"""
        module, version, serial = "", "", ""
        order_code_raw = ""

        # ── 1) 订货号 ──
        try:
            oc = self._client.get_order_code()
            logger.debug(f"get_order_code raw: OrderCode={oc.OrderCode!r} V1={oc.V1} V2={oc.V2} V3={oc.V3}")
            if oc.OrderCode:
                raw = oc.OrderCode
                if isinstance(raw, bytes):
                    raw = raw.decode('ascii', errors='replace').strip().rstrip('\x00')
                else:
                    raw = str(raw).strip()
                if raw:
                    order_code_raw = raw
            # V1/V2/V3 不是固件版本，跳过
        except Exception as e:
            logger.debug(f"get_order_code error: {e}")

        # ── 2) CPU Info ──
        try:
            cpu = self._client.get_cpu_info()
            # dump all keys for debug
            clean = {}
            for k, v in cpu.items():
                if isinstance(v, bytes):
                    clean[k] = v.decode('utf-8', errors='replace').rstrip('\x00').strip()
                else:
                    clean[k] = str(v) if v else ''
            logger.debug(f"get_cpu_info: {clean}")

            for key in ('ModuleTypeName', 'ModuleName'):
                val = clean.get(key, '')
                if val and val.lower() != 'unknown' and len(val) > 1:
                    module = val
                    break
            serial = clean.get('SerialNumber', '') or serial
            version = clean.get('ASName', '') or version
            version = clean.get('FirmwareVersion', '') or version
        except Exception as e:
            logger.debug(f"get_cpu_info error: {e}")

        # ── 3) 多个 SZL 尝试 ──
        szl_attempts = [
            (0x0011, 0, "cpu_basic"),
            (0x0011, 1, "module_id"),
            (0x0011, 6, "serial"),
            (0x0011, 7, "fw_version"),
            (0x0131, 1, "fw_detail"),
            (0x001C, 1, "component_id"),
            (0x0111, 1, "hw_id"),
        ]
        for ssl_id, index, label in szl_attempts:
            try:
                szl = self._client.read_szl(ssl_id, index)
                if not szl or not szl.Data:
                    continue

                data = bytes(szl.Data)

                # 方式A: 按 null 切段
                segments = [s.decode('ascii', errors='replace').strip()
                            for s in data.split(b'\x00')
                            if len(s.strip(b'\x00')) > 1]
                logger.debug(f"SZL 0x{ssl_id:04X}[{index}] segments: {segments[:8]!r}")

                # 方式B: 整段原文（去掉不可打印字符）
                raw_text = data.decode('ascii', errors='replace')
                clean_text = re.sub(r'[^\x20-\x7E]', '', raw_text)
                logger.debug(f"SZL 0x{ssl_id:04X}[{index}] clean: {clean_text[:120]!r}")

                # ── 从整段原文中提取 MLFB ──
                for match_text in [clean_text] + segments:
                    # 找 6ES7 开头
                    idx = match_text.upper().find('6ES7')
                    if idx < 0:
                        continue
                    tail = match_text[idx:]
                    # 取 6ES7 + 最多 25 字符 (MLFB 典型长度 ~19)
                    raw = tail[:25].replace(' ', '').replace('-', '')
                    # 如果内含第二个 6ES7，在它前面截断
                    second = raw[4:].upper().find('6ES7')
                    if second > 0:
                        raw = raw[:second + 4]
                    # 验证：必须以 6ES7 + digit + 2 digits 开头
                    if re.match(r'6ES7\d{3}', raw):
                        order_code_raw = raw
                        if not module:
                            module = self._mlfb_to_name(order_code_raw)
                        break

                for seg in segments:
                    idx = seg.upper().find('6ES7')
                    if idx < 0:
                        continue
                    tail = seg[idx:]
                    raw = tail[:25].replace(' ', '').replace('-', '')
                    second = raw[4:].upper().find('6ES7')
                    if second > 0:
                        raw = raw[:second + 4]
                    if re.match(r'6ES7\d{3}', raw) and not order_code_raw:
                        order_code_raw = raw
                        if not module:
                            module = self._mlfb_to_name(order_code_raw)
                        break

                    # 固件版本
                    if not version:
                        vm = re.search(r'V(\d+)\.(\d+)', seg)
                        if vm:
                            version = vm.group(0)

                    # 序列号
                    if not serial and re.match(r'^[A-Z0-9]{6,24}$', seg) and '6ES7' not in seg.upper():
                        serial = seg

            except Exception as e:
                logger.debug(f"SZL 0x{ssl_id:04X}[{index}] error: {e}")

        # ── 合成 ──
        if order_code_raw and not module:
            module = self._mlfb_to_name(order_code_raw)

        if not module:
            module = "未知型号"

        # 格式化显示：S7-1516 (6ES7516-3AN01-0AB0)
        if order_code_raw and module != "未知型号":
            display_code = order_code_raw
            # 尝试加回 Siemens 标准连字符: 6ES75163AN010AB0 → 6ES7 516-3AN01-0AB0
            m = re.match(r'(6ES7)(\d)(\d{2})(.{5})(.{4})', order_code_raw)
            if m:
                display_code = f"{m.group(1)} {m.group(2)}{m.group(3)}-{m.group(4)}-{m.group(5)}"
            module = f"{module} ({display_code})"

        logger.info(f"PLC: {module}  FW: {version or '?'}  S/N: {serial or '?'}")
        self.plc_info.emit(module, version or "", serial or "")

    @staticmethod
    def _classify_order_code(code: str) -> str:
        """6ES7 214-... → S7-1200"""
        m = re.search(r'6ES7[-\s]*(\d)', code.upper())
        if m:
            prefix = m.group(1)
            return {'2': 'S7-1200', '5': 'S7-1500',
                    '3': 'S7-300', '4': 'S7-400'}.get(prefix, '')
        return ""

    @staticmethod
    def _mlfb_to_name(mlfb: str) -> str:
        """6ES7516-3AN01-0AB0 → S7-1516"""
        m = re.search(r'6ES7\s*(\d)(\d{2})', mlfb.upper().replace('-', '').replace(' ', ''))
        if m:
            family_num = m.group(1)
            model = m.group(2)
            return f"S7-{family_num}{model}"
        return mlfb

    # ── 线程主循环 ──────────────────────────────────────

    def run(self):
        """后台线程主循环"""
        reconnect_timer = 0

        while self._running:
            try:
                # 连接 PLC
                if not self._client.get_connected():
                    try:
                        logger.info(f"Connecting to {self._ip} "
                                     f"rack={self._rack} slot={self._slot}")
                        self._client.connect(self._ip, self._rack, self._slot)

                        # 获取 PLC 型号 / 固件 / 序列号
                        self._fetch_plc_info()

                        self.connected.emit()
                        reconnect_timer = 0
                        logger.info("PLC connected successfully")

                    except S7Error as e:
                        err_msg = str(e)
                        logger.warning(f"Connection failed: {err_msg}")
                        self.connection_error.emit(err_msg)

                        # 等待后重试
                        if self._auto_reconnect and self._running:
                            self._client.disconnect()
                            sleep_time = min(reconnect_timer, 10000)
                            self._msleep(sleep_time)
                            reconnect_timer = max(3000, reconnect_timer + 1000)
                            continue
                        else:
                            break

                # 主扫描循环
                while self._running and not self._paused:
                    if not self._client.get_connected():
                        self.disconnected.emit("连接断开")
                        break

                    self._mutex.lock()
                    tags_snapshot = self._tags.copy()
                    self._mutex.unlock()

                    if tags_snapshot:
                        scan_start = datetime.now()
                        results = self._scan_tags(tags_snapshot)
                        scan_ms = (datetime.now() - scan_start).total_seconds() * 1000
                        self.scan_time.emit(scan_ms)

                        if results:
                            self.data_updated.emit(results)

                    # 等待扫描间隔
                    self._mutex.lock()
                    if self._running and not self._paused:
                        self._condition.wait(self._mutex, self._scan_interval)
                    self._mutex.unlock()

                # 处理暂停
                while self._paused and self._running:
                    self._mutex.lock()
                    self._condition.wait(self._mutex, 500)
                    self._mutex.unlock()

            except S7Error as e:
                logger.error(f"PLC error: {e}")
                self.disconnected.emit("")
                try:
                    self._client.disconnect()
                except Exception:
                    pass

                if self._auto_reconnect and self._running:
                    self._msleep(self._reconnect_interval)
                else:
                    break
            except Exception as e:
                logger.error(f"Unexpected error in PLC worker: {e}")
                self._msleep(1000)

        # 清理
        try:
            if self._client.get_connected():
                self._client.disconnect()
        except Exception:
            pass
        self.disconnected.emit("")

    # ── 标签扫描 ─────────────────────────────────────────

    def _scan_tags(self, tags: list[TagConfig]) -> list:
        """
        批量扫描标签，优化为按区域分组读取。
        返回: [(tag_index, value, quality, timestamp, error_msg), ...]
              error_msg 仅在 quality == BAD 时有意义
        """
        # 按 (area, db_number) 分组
        groups: dict[tuple, list] = {}
        for idx, tag in enumerate(tags):
            if not tag.scan_enabled:
                continue
            key = (tag.area, tag.db_number)
            groups.setdefault(key, []).append((idx, tag))

        results = []
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        for (area, db_num), tag_list in groups.items():
            try:
                self._read_group(area, db_num, tag_list, results, timestamp)
            except S7Error as e:
                # 标记该组所有标签为 BAD，附带错误信息
                err_msg = str(e)
                area_name = area.prefix
                if area == Area.DB:
                    group_desc = f"DB{db_num}"
                else:
                    group_desc = f"{area_name} area"
                full_err = f"[{group_desc}] {err_msg}"
                for idx, tag in tag_list:
                    results.append((idx, None, TagQuality.BAD, timestamp, full_err))

        return results

    def _read_group(self, area: Area, db_num: int,
                    tag_list: list, results: list, timestamp: str):
        """
        读取一组标签（同一区域）。采用范围读取优化：
        找到该组的最小/最大字节偏移，一次性读取整个范围。
        """
        enabled = [(idx, t) for idx, t in tag_list if t.scan_enabled]
        if not enabled:
            return

        # 计算覆盖范围
        min_offset = min(t.byte_offset for _, t in enabled)
        max_offset = max(t.byte_offset + t.byte_length for _, t in enabled)
        total_size = max_offset - min_offset

        if total_size <= 0:
            total_size = 4  # 至少读 4 字节

        # 读取数据
        raw_data = self._read_area(area, db_num, min_offset, total_size)

        if raw_data is None:
            raise S7Error("返回数据为空")

        # 解析每个标签的值
        for idx, tag in enabled:
            local_offset = tag.byte_offset - min_offset
            end_offset = local_offset + tag.byte_length

            if end_offset > len(raw_data):
                results.append((idx, None, TagQuality.BAD, timestamp,
                              f"偏移超出数据范围 (need {end_offset}, got {len(raw_data)})"))
                continue

            tag_data = raw_data[local_offset:end_offset]
            value = parse_bytes(tag_data, tag.data_type, tag.bit_offset) \
                if tag.data_type == DataType.BOOL \
                else parse_bytes(tag_data, tag.data_type)

            quality = TagQuality.GOOD if value is not None else TagQuality.BAD
            err = "" if value is not None else "数据解析失败"
            results.append((idx, value, quality, timestamp, err))

    def _read_area(self, area: Area, db_num: int,
                   start: int, size: int) -> Optional[bytes]:
        """读取指定区域的数据"""
        try:
            if area == Area.DB:
                return self._client.db_read(db_num, start, size)
            else:
                return self._client.read_area(area.code, db_num, start, size)
        except S7Error:
            raise

    def _msleep(self, ms: int):
        """毫秒级休眠（线程安全）"""
        self._mutex.lock()
        self._condition.wait(self._mutex, ms)
        self._mutex.unlock()

    # ── 写入操作 ─────────────────────────────────────────

    def write_tag(self, tag_index: int,
                  tag: TagConfig, value: Any) -> tuple[bool, str]:
        """
        向 PLC 写入值。
        返回 (success, message)。
        注意：此方法在调用线程中执行，需要确保 PLC 已连接。
        """
        if not self._client.get_connected():
            return False, "PLC not connected"

        try:
            if tag.data_type == DataType.BOOL:
                # 读-改-写：BOOL 类型必须先读出当前字节，
                # 只修改目标位后写回，避免覆盖同一字节的其他位
                return self._write_bool(tag, value)
            else:
                data = value_to_bytes(value, tag.data_type, tag.bit_offset)
                if data is None:
                    return False, "Value conversion failed"

                if tag.area == Area.DB:
                    self._client.db_write(tag.db_number, tag.byte_offset, data)
                else:
                    self._client.write_area(
                        tag.area.code, tag.db_number, tag.byte_offset, data
                    )
                return True, "Write successful"
        except S7Error as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)

    def _write_bool(self, tag: TagConfig, value: Any) -> tuple[bool, str]:
        """读-改-写 BOOL 值，避免覆盖同一字节的其他位"""
        # 1. 读取当前字节
        if tag.area == Area.DB:
            raw = self._client.db_read(tag.db_number, tag.byte_offset, 1)
        else:
            raw = self._client.read_area(tag.area.code, tag.db_number,
                                         tag.byte_offset, 1)

        if not raw or len(raw) == 0:
            return False, "Read current byte failed"

        # 2. 修改目标位
        current_byte = raw[0]
        if value:
            new_byte = current_byte | (1 << tag.bit_offset)
        else:
            new_byte = current_byte & ~(1 << tag.bit_offset)

        # 3. 写回
        data = bytes([new_byte])
        if tag.area == Area.DB:
            self._client.db_write(tag.db_number, tag.byte_offset, data)
        else:
            self._client.write_area(tag.area.code, tag.db_number,
                                    tag.byte_offset, data)
        return True, "Write successful"
