"""Android 模拟器生命周期管理（APP UI 自动化第一版）。

只封装 emulator 进程与 ADB 启动等待，不负责 Appium 会话。
"""

import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from adb_manager import AdbManager

logger = logging.getLogger('actuator.emulator')


def get_emulator_path() -> Optional[str]:
    """获取 emulator 可执行文件路径。"""
    android_home = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    if android_home:
        candidate = Path(android_home) / 'emulator' / ('emulator.exe' if os.name == 'nt' else 'emulator')
        if candidate.exists():
            return str(candidate)
    return shutil.which('emulator')


class EmulatorManager:
    """模拟器启动/停止/状态管理。"""

    def __init__(self, adb_manager: Optional[AdbManager] = None, boot_timeout: int = 120):
        self.adb = adb_manager or AdbManager()
        self.boot_timeout = boot_timeout
        self._processes: dict[str, subprocess.Popen] = {}

    def list_avds(self) -> list[str]:
        """列出本机可用 AVD。"""
        emulator = get_emulator_path()
        if not emulator:
            return []
        try:
            result = subprocess.run(
                [emulator, '-list-avds'],
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='replace',
            )
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except Exception as exc:
            logger.warning('列出 AVD 失败: %r', exc)
            return []

    def is_running(self, avd_name: str) -> Optional[str]:
        """按 AVD 名查找在线模拟器；返回 udid 或 None。"""
        return self._find_udid_by_avd(avd_name)

    def _avd_name_of(self, udid: str) -> Optional[str]:
        """通过 `adb emu avd name` 读取设备所属 AVD 名（仅 Google 模拟器支持）。"""
        try:
            result = self.adb._run(['emu', 'avd', 'name'], udid=udid, check=False)
        except Exception:
            return None
        for line in (result.stdout or '').splitlines():
            line = line.strip()
            if not line or line.upper() == 'OK':
                continue
            # 兼容两种输出："Pixel_6_API_34"（裸名）或
            # "Android Debug Bridge AvdName: Pixel_6_API_34"（带前缀）
            name = line.rsplit(':', 1)[1].strip() if ':' in line else line
            if name and name.upper() != 'OK':
                return name
        return None

    def _find_udid_by_avd(
        self, avd_name: str, exclude: Optional[set] = None
    ) -> Optional[str]:
        """遍历在线设备，按 AVD 名匹配模拟器 udid。

        不依赖固定端口：本机可能存在第三方模拟器占用 5554/5555，
        Google 模拟器端口漂移后呈现为任意 `emulator-N` / `127.0.0.1:N`。
        """
        for item in self.adb.devices():
            udid = item.get('udid', '')
            if item.get('status') != 'device':
                continue
            if exclude and udid in exclude:
                continue
            if not (udid.startswith('emulator-') or udid.startswith('127.0.0.1:')):
                continue
            if self._avd_name_of(udid) == avd_name:
                return udid
        return None

    def start(self, avd_name: str, *, headless: bool = True, snapshot_enabled: bool = True) -> str:
        """启动 AVD 并等待启动完成，返回 udid。"""
        emulator = get_emulator_path()
        if not emulator:
            raise FileNotFoundError('未找到 emulator，请配置 ANDROID_HOME/emulator')

        existing_udid = self._find_udid_by_avd(avd_name)
        if existing_udid:
            logger.info('模拟器已在运行: %s', existing_udid)
            return existing_udid

        port = self._pick_port()
        cmd = [emulator, '-avd', avd_name, '-port', str(port)]
        if headless:
            cmd.extend(['-no-window', '-no-audio', '-no-boot-anim', '-gpu', 'swiftshader_indirect'])
        if snapshot_enabled:
            cmd.append('-no-snapshot-save')

        # 记录启动前在线设备：端口漂移时靠"新增设备 + AVD 名匹配"定位 udid
        baseline = {d.get('udid') for d in self.adb.devices()}
        log_dir = Path('./data/emulators')
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f'{avd_name}-{uuid.uuid4().hex[:8]}.log'
        logger.info('启动模拟器: %s，日志: %s', ' '.join(cmd), log_path)
        log_file = log_path.open('w', encoding='utf-8', errors='replace')
        process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
        self._processes[avd_name] = process

        udid = self._wait_udid(avd_name, baseline, timeout=60)
        if not udid:
            raise TimeoutError(f'模拟器未在 60 秒内上线: {avd_name}')
        if not self.adb.wait_for_boot(udid, timeout=self.boot_timeout):
            raise TimeoutError(f'模拟器未在 {self.boot_timeout} 秒内完成 Android 启动')
        return udid

    def _pick_port(self) -> int:
        """选择一个未被占用的 console 端口。

        默认区间 5554/5555 常被第三方模拟器（MuMu/雷电等）抢占 adb 设备名
        与 console 端口，从 5556 起步并在已注册设备名中跳过冲突项。
        """
        used = {
            d.get('udid')
            for d in self.adb.devices()
            if str(d.get('udid', '')).startswith('emulator-')
        }
        for base in range(5556, 5586, 2):
            if f'emulator-{base}' not in used:
                return base
        return 5556

    def _wait_udid(
        self, avd_name: str, baseline: Optional[set] = None, timeout: int = 60
    ) -> Optional[str]:
        """等待目标 AVD 上线并返回其 udid（按 AVD 名匹配，容忍端口漂移）。"""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            udid = self._find_udid_by_avd(avd_name, exclude=baseline)
            if udid:
                return udid
            time.sleep(1)
        return None

    def stop(self, avd_name: Optional[str] = None, udid: Optional[str] = None):
        """停止模拟器。优先 adb emu kill，失败时终止本地进程。"""
        if not udid and avd_name:
            udid = self._find_udid_by_avd(avd_name)
        target_udid = udid
        if target_udid:
            try:
                self.adb.emu_kill(target_udid)
            except Exception as exc:
                logger.warning('adb emu kill 失败: %r', exc)

        if avd_name and avd_name in self._processes:
            process = self._processes.pop(avd_name)
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
            except Exception as exc:
                logger.warning('终止模拟器进程失败: %r', exc)
