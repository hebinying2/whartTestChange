"""APP 截图流（第一版使用截图轮询，不追求高帧率）。"""

import asyncio
import base64
from pathlib import Path

from adb_manager import AdbManager

logger = logging.getLogger('actuator.app_screen')


class AppScreenStreamer:
    """按固定频率采集模拟器画面帧。"""

    def __init__(self, adb_manager: AdbManager, udid: str,
                 on_frame, *, fps: float = 2.0):
        self.adb = adb_manager
        self.udid = udid
        self.on_frame = on_frame
        self.interval = max(0.2, 1 / max(fps, 0.1))
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self):
        """启动截图轮询。"""
        if self._task:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())
        logger.info('APP 截图流已启动 udid=%s fps=%.2f', self.udid, 1 / self.interval)

    async def stop(self):
        """停止截图轮询。"""
        if self._task:
            self._stop_event.set()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info('APP 截图流已停止 udid=%s', self.udid)

    async def _run(self):
        while not self._stop_event.is_set():
            try:
                path = Path('./data/app_frames') / f'{self.udid}.png'
                self.adb.screenshot(self.udid, str(path))
                data = path.read_bytes()
                frame = base64.b64encode(data).decode('ascii')
                await self.on_frame(frame)
            except Exception as exc:
                logger.warning('APP 截图失败: %r', exc)
            await asyncio.sleep(self.interval)
