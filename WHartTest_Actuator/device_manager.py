"""APP 自动化设备池（第一版仅支持 Android 模拟器）。

单进程内维护可用的设备槽位，避免同一模拟器被并发任务重复占用。
"""

import logging
import threading
from typing import Optional

from adb_manager import AdbManager
from emulator_manager import EmulatorManager

logger = logging.getLogger('actuator.device_manager')


class DeviceManager:
    """管理模拟器槽位与状态。"""

    def __init__(self, adb_manager: Optional[AdbManager] = None, boot_timeout: int = 120):
        self.adb = adb_manager or AdbManager()
        self.emulator = EmulatorManager(self.adb, boot_timeout=boot_timeout)
        self._lock = threading.Lock()
        self._busy_udids: set[str] = set()

    def has_toolchain(self) -> dict:
        """检查 ADB / emulator 是否可用。"""
        from adb_manager import get_adb_path
        from emulator_manager import get_emulator_path

        return {
            'adb': bool(get_adb_path()),
            'emulator': bool(get_emulator_path()),
            'online_devices': len([d for d in self.adb.devices() if d.get('status') == 'device']),
        }

    def start_device(self, *, avd_name: str, headless: bool = True, snapshot_enabled: bool = True) -> dict:
        """启动模拟器并返回 udid。"""
        with self._lock:
            udid = self.emulator.start(avd_name, headless=headless, snapshot_enabled=snapshot_enabled)
            self._busy_udids.add(udid)
        return {'udid': udid, 'status': 'running'}

    def stop_device(self, *, avd_name: Optional[str] = None, udid: Optional[str] = None):
        """停止模拟器并释放槽位。"""
        target_udid = udid
        if not target_udid and avd_name:
            target_udid = self.emulator.is_running(avd_name)
        self.emulator.stop(avd_name=avd_name, udid=target_udid)
        with self._lock:
            if target_udid:
                self._busy_udids.discard(target_udid)
        return {'udid': target_udid, 'status': 'stopped'}

    def status(self, avd_name: str) -> dict:
        """查询模拟器状态。"""
        udid = self.emulator.is_running(avd_name)
        info = self.adb.device_info(udid) if udid else {}
        return {
            'udid': udid,
            'status': 'running' if udid else 'stopped',
            'info': info,
        }
