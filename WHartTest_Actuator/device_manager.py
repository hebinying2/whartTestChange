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

    def ensure_appium_server(self, port: int = 4723, timeout: int = 30) -> dict:
        """确保 Appium server 在运行；未运行则自动拉起并等待端口就绪。"""
        import socket
        import subprocess
        import time
        from pathlib import Path

        def _port_open() -> bool:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                return sock.connect_ex(('127.0.0.1', port)) == 0

        if _port_open():
            return {'running': True, 'started': False, 'port': port}

        from app_capabilities import detect_app_capability
        capability = detect_app_capability()
        appium_path = (capability.get('installed_tools') or {}).get('appium_path')
        if not appium_path:
            raise FileNotFoundError('未找到 Appium，请先安装（npm install -g appium）')

        log_dir = Path('./data/appium')
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = (log_dir / 'appium-server.log').open('a', encoding='utf-8', errors='replace')
        logger.info('启动 Appium server: %s (port=%s)', appium_path, port)
        self._appium_process = subprocess.Popen(
            [appium_path, '--port', str(port), '--relaxed-security'],
            stdout=log_file, stderr=subprocess.STDOUT,
        )

        deadline = time.time() + timeout
        while time.time() < deadline:
            if _port_open():
                logger.info('Appium server 已就绪: 127.0.0.1:%s', port)
                return {'running': True, 'started': True, 'port': port}
            time.sleep(1)
        raise TimeoutError(f'Appium server 未在 {timeout} 秒内就绪 (port={port})')
