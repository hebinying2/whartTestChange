"""APP 截图流（第一版使用截图轮询，不追求高帧率）。"""

import asyncio
import base64
import logging

from adb_manager import AdbManager

logger = logging.getLogger('actuator.app_screen')


class AppScreenStreamer:
    """按固定频率采集模拟器画面帧（字节截图 → base64 回调）。

    支持：
    - 动态降频 set_fps：APP 用例执行期间降低帧率，避免 screencap
      与 UiAutomator2 抢资源（方案 19.3 实现要点 3）
    - 幂等 stop：任务取消安全清理（实现要点 4）
    """

    def __init__(self, adb_manager: AdbManager, udid: str,
                 on_frame, *, fps: float = 2.0):
        self.adb = adb_manager
        self.udid = udid
        self.on_frame = on_frame
        self.fps = max(0.2, float(fps or 2.0))
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def set_fps(self, fps: float):
        """运行中动态调整帧率（执行互斥降频用）。"""
        self.fps = max(0.2, float(fps or 2.0))

    async def start(self):
        """启动截图轮询。"""
        if self.running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())
        logger.info('APP 截图流已启动 udid=%s fps=%.2f', self.udid, self.fps)

    async def stop(self):
        """停止截图轮询（幂等）。"""
        if self._task:
            self._stop_event.set()
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._task = None
            logger.info('APP 截图流已停止 udid=%s', self.udid)

    async def _run(self):
        while not self._stop_event.is_set():
            try:
                data = await asyncio.to_thread(self.adb.screenshot_bytes, self.udid)
                frame = base64.b64encode(data).decode('ascii')
                # 回调携带原始字节：consumer 从 PNG 头解析当前分辨率
                # （模拟器横竖屏会随前台 APP 切换，坐标系必须跟帧走）
                await self.on_frame(frame, data)
            except Exception as exc:
                logger.warning('APP 截图失败: %r', exc)
            # 每轮循环重新计算间隔，支持运行中动态降频
            await asyncio.sleep(max(0.2, 1 / self.fps))
