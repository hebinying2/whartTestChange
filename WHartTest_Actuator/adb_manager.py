"""ADB 命令封装（APP UI 自动化第一版）。

只负责与 ADB 交互，不做设备生命周期管理；生命周期由 emulator_manager / device_manager 维护。
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger('actuator.adb')


def _resolve_tool(name: str, sub_dir: str) -> Optional[str]:
    """优先从 ANDROID_HOME 解析工具路径，其次回退 PATH。"""
    android_home = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    if android_home:
        candidate = Path(android_home) / sub_dir / name
        if candidate.exists():
            return str(candidate)
    return shutil.which(name)


def get_adb_path() -> Optional[str]:
    """获取 adb 可执行文件路径。"""
    return _resolve_tool('adb.exe' if os.name == 'nt' else 'adb', 'platform-tools')


class AdbManager:
    """ADB 命令封装。"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def _run(self, args: list[str], udid: Optional[str] = None, check: bool = True) -> subprocess.CompletedProcess:
        adb = get_adb_path()
        if not adb:
            raise FileNotFoundError('未找到 adb，请配置 ANDROID_HOME 或加入 PATH')
        cmd = [adb]
        if udid:
            cmd.extend(['-s', udid])
        cmd.extend(args)
        logger.info('执行 ADB 命令: %s', ' '.join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, encoding='utf-8', errors='replace')
        if check and result.returncode != 0:
            raise RuntimeError(f"ADB 命令失败({result.returncode}): {' '.join(cmd)} -> {result.stderr or result.stdout}")
        return result

    def devices(self) -> list[dict]:
        """返回当前在线设备列表。"""
        try:
            result = self._run(['devices', '-l'], check=False)
        except FileNotFoundError:
            return []
        devices = []
        for line in result.stdout.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            devices.append({'udid': parts[0], 'status': parts[1], 'extra': ' '.join(parts[2:])})
        return devices

    def connect(self, address: str) -> bool:
        """主动连接 TCP 设备（如模拟器 127.0.0.1:5555）。"""
        try:
            result = self._run(['connect', address], check=False)
        except FileNotFoundError:
            return False
        return 'connected' in (result.stdout or '').lower()

    def is_online(self, udid: str) -> bool:
        """判断指定设备是否在线。"""
        return any(d.get('udid') == udid and d.get('status') == 'device' for d in self.devices())

    def wait_for_device(self, udid: str, timeout: int = 60) -> bool:
        """等待设备上线。"""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_online(udid):
                return True
            time.sleep(1)
        return False

    def boot_completed(self, udid: str) -> bool:
        """判断 Android 是否完成启动。"""
        try:
            result = self._run(['shell', 'getprop', 'sys.boot_completed'], udid=udid, check=False)
            return result.stdout.strip() == '1'
        except Exception:
            return False

    def wait_for_boot(self, udid: str, timeout: int = 120) -> bool:
        """等待设备完成 Android 启动。"""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.boot_completed(udid):
                return True
            time.sleep(2)
        return False

    def device_info(self, udid: str) -> dict:
        """读取设备基础信息。"""
        props = ['ro.product.model', 'ro.build.version.release', 'ro.product.cpu.abi']
        info = {}
        for prop in props:
            try:
                result = self._run(['shell', 'getprop', prop], udid=udid, check=False)
                info[prop] = result.stdout.strip()
            except Exception:
                info[prop] = ''
        return info

    def install_app(self, udid: str, apk_path: str) -> subprocess.CompletedProcess:
        """安装 APK。"""
        return self._run(['install', '-r', str(apk_path)], udid=udid)

    def uninstall_app(self, udid: str, package: str) -> subprocess.CompletedProcess:
        """卸载 APP。"""
        return self._run(['uninstall', package], udid=udid, check=False)

    def start_app(self, udid: str, package: str, activity: Optional[str] = None):
        """启动 APP。activity 为空时使用 monkey 拉起默认入口。"""
        if activity:
            component = activity if '.' in activity else f"{package}/{activity}"
            return self._run(['shell', 'am', 'start', '-n', component], udid=udid)
        return self._run(['shell', 'monkey', '-p', package, '-c', 'android.intent.category.LAUNCHER', '1'], udid=udid)

    def stop_app(self, udid: str, package: str):
        """强制停止 APP。"""
        return self._run(['shell', 'am', 'force-stop', package], udid=udid)

    def emu_kill(self, udid: str) -> subprocess.CompletedProcess:
        """向模拟器控制台发送 kill 指令。"""
        return self._run(['emu', 'kill'], udid=udid, check=False)

    def screenshot(self, udid: str, output_path: str) -> str:
        """截图保存到本地文件。"""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        result = self._run(['exec-out', 'screencap', '-p'], udid=udid)
        # exec-out 返回二进制，text=True 下已按 utf-8 replace 解码；改用 bytes 稳定保存。
        raw = subprocess.run(
            [get_adb_path(), '-s', udid, 'exec-out', 'screencap', '-p'],
            capture_output=True,
            timeout=self.timeout,
        )
        if raw.returncode != 0:
            raise RuntimeError(f"ADB 截图失败: {raw.stderr.decode('utf-8', errors='replace')}")
        output.write_bytes(raw.stdout)
        return str(output)
