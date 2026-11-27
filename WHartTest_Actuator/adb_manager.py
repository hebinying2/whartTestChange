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

    def screenshot_bytes(self, udid: str) -> bytes:
        """截图并返回原始 PNG 字节（画面推流用，避免落盘）。"""
        raw = subprocess.run(
            [get_adb_path(), '-s', udid, 'exec-out', 'screencap', '-p'],
            capture_output=True,
            timeout=self.timeout,
        )
        if raw.returncode != 0 or not raw.stdout:
            raise RuntimeError(f"ADB 截图失败: {raw.stderr.decode('utf-8', errors='replace')}")
        return raw.stdout

    def screen_size(self, udid: str) -> tuple[int, int]:
        """读取设备当前实际分辨率 (宽, 高)。

        注意：不能用 `wm size`——横屏模拟器返回未旋转的声明尺寸
        （实测 900x1600），而 screencap/注入坐标系是 1600x900，
        会导致画面点击换算完全错位。改从截图 PNG IHDR 头解析
        （PNG 16-24 字节为宽高，与实际屏幕方向一致）。
        """
        import struct
        data = self.screenshot_bytes(udid)
        if len(data) < 24:
            raise RuntimeError('截图数据异常，无法解析分辨率')
        w, h = struct.unpack('>II', data[16:24])
        return int(w), int(h)

    def tap(self, udid: str, x: int, y: int):
        """注入点击。"""
        return self._run(['shell', 'input', 'tap', str(int(x)), str(int(y))], udid=udid)

    def swipe(self, udid: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        """注入滑动。"""
        return self._run(
            ['shell', 'input', 'swipe', str(int(x1)), str(int(y1)),
             str(int(x2)), str(int(y2)), str(int(duration_ms))], udid=udid)

    def input_text(self, udid: str, text: str):
        """注入文本（不支持中文，复杂文本走 uiautomator/Appium）。"""
        return self._run(['shell', 'input', 'text', text], udid=udid)

    def key_event(self, udid: str, keycode: str):
        """注入按键（BACK=4, HOME=3, ENTER=66 等）。"""
        return self._run(['shell', 'input', 'keyevent', str(keycode)], udid=udid)

    def dump_ui(self, udid: str, timeout_s: float = 10) -> str:
        """uiautomator dump 控件树 XML（无需 Appium session 的元素采集来源）。

        屏幕存在动画（图表刷新/加载中/输入法弹出）或残留 dump 进程时，
        会报 "ERROR: could not get idle state"——先 pkill 清理残留，
        再递增间隔重试（重试期间动画往往恰好处于间歇静止）。
        """
        import time
        last_err = ''
        dumped = False
        for attempt in range(3):
            self._run(['shell', 'pkill', '-f', 'uiautomator'], udid=udid, check=False)
            time.sleep(0.5)
            result = self._run(
                ['shell', 'uiautomator', 'dump', '/sdcard/uidump.xml'],
                udid=udid, check=False)
            out = (result.stdout or '')
            if 'dumped' in out.lower() or 'uidump' in out.lower():
                dumped = True
                break
            last_err = (out or result.stderr or '').strip()[:140]
            time.sleep(1.0 + attempt)
        if not dumped:
            raise RuntimeError(
                f'uiautomator dump 失败: {last_err or "未知错误"}'
                '（屏幕可能存在持续动画/输入法，请稍候重试）')
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            cat = self._run(['shell', 'cat', '/sdcard/uidump.xml'], udid=udid, check=False)
            content = cat.stdout or ''
            if content.strip().startswith('<?xml') or '<hierarchy' in content:
                return content
            time.sleep(0.5)
        raise RuntimeError('uiautomator dump 读取超时')

    def current_focus(self, udid: str) -> str:
        """当前前台窗口（Activity），形如 pkg/.MainActivity。"""
        result = self._run(['shell', 'dumpsys', 'window', 'displaysize'], udid=udid, check=False)
        _ = result
        focus = self._run(
            ['shell', 'dumpsys', 'activity', 'activities'], udid=udid, check=False)
        for line in (focus.stdout or '').splitlines():
            line = line.strip()
            if line.startswith('topResumedActivity') or line.startswith('mResumedActivity'):
                # 形如 topResumedActivity=ActivityRecord{... u0 com.pkg/.Activity t123}
                part = line.split(' ', 1)[1] if ' ' in line else ''
                for token in part.split():
                    if '/' in token and '.' in token.split('/')[0]:
                        return token.rstrip('}')
        return ''
