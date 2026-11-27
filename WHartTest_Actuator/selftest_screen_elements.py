"""阶段 3/4a 执行器侧逻辑自测：画面推流 + 控件树解析。"""
import sys
sys.path.insert(0, '.')

import consumer, app_elements, app_screen_streamer, adb_manager  # noqa: F401 语法检查
from models import UiSocketEnum

assert UiSocketEnum.APP_SCREEN_START == 'u_app_screen_start'
assert UiSocketEnum.APP_SCREEN_FRAME == 'u_app_screen_frame'
assert UiSocketEnum.APP_SCREEN_INPUT == 'u_app_screen_input'
assert UiSocketEnum.APP_SCREEN_STATUS == 'u_app_screen_status'
assert UiSocketEnum.APP_SCREEN_STOP == 'u_app_screen_stop'
assert UiSocketEnum.APP_ELEMENTS_DUMP == 'u_app_elements_dump'
assert UiSocketEnum.APP_ELEMENTS_RESULT == 'u_app_elements_result'

XML = (
    '<?xml version="1.0"?>'
    '<hierarchy>'
    '<node class="android.widget.Button" package="com.test" '
    'resource-id="com.test:id/login" text="登录" content-desc="" '
    'clickable="true" bounds="[100,200][400,300]"/>'
    '<node class="android.widget.EditText" package="com.test" '
    'resource-id="com.test:id/username" text="" content-desc="用户名" '
    'clickable="true" editable="true" bounds="[100,50][500,120]"/>'
    '<node class="android.widget.TextView" package="com.test" '
    'resource-id="" text="静态文本不可点" clickable="false" '
    'bounds="[0,900][1080,940]"/>'
    '</hierarchy>'
)

nodes = app_elements.parse_ui_xml(XML)
assert len(nodes) == 3, f'应为 3 个节点（2 交互 + 1 静态文本可断言），实际 {len(nodes)}'
static = [n for n in nodes if not n['clickable'] and not n['editable']]
print('static nodes:', [(n['class'], n['locator_type'], n['locator_value']) for n in static])
assert static and static[0]['locator_type'] == 'uiautomator', static[0]

# 定位优先级：content-desc 优先于 resource-id
print('all nodes:', [(n['class'], n['content_desc'], n['locator_type'], n['locator_value']) for n in nodes])
by_desc = [n for n in nodes if n['content_desc']]
assert by_desc and by_desc[0]['locator_type'] == 'accessibility_id'
assert by_desc[0]['locator_value'] == '用户名'

by_id = [n for n in nodes if n['resource_id'] == 'com.test:id/login']
assert by_id and by_id[0]['locator_type'] == 'resource_id'

# 坐标命中
hit = app_elements.find_node_at(nodes, 250, 250)
assert hit and hit['resource_id'] == 'com.test:id/login'
assert app_elements.find_node_at(nodes, 999, 999) is None

# 边界解析
r = nodes[0]['rect']
assert r == {'x1': 100, 'y1': 200, 'x2': 400, 'y2': 300, 'w': 300, 'h': 100, 'cx': 250, 'cy': 250}, r

# AppScreenStreamer 幂等与降频
class FakeAdb:
    def __init__(self):
        self.calls = 0
    def screenshot_bytes(self, udid):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError('第一次失败')
        return b'\x89PNG fake'

import asyncio

async def smoke():
    adb = FakeAdb()
    frames = []
    s = app_screen_streamer.AppScreenStreamer(
        adb, 'emulator-5554', lambda f, raw: frames.append((f, raw)), fps=8)
    await s.start()
    await asyncio.sleep(0.8)
    await s.stop()
    await s.stop()  # 幂等
    assert len(frames) >= 1, f'应至少收到 1 帧，实际 {len(frames)}'
    s.set_fps(0.5)
    assert s.fps == 0.5

asyncio.run(smoke())
print('STAGE3A-4A ALL OK')
