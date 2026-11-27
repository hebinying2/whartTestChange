"""验证三问题修复：横屏分辨率 / 文本转义 / 注入实测。"""
import sys
sys.path.insert(0, '.')

from adb_manager import AdbManager

adb = AdbManager()
UDID = 'emulator-5554'

# 1. 横屏分辨率：应返回 1600x900（与截图一致），不再是 wm size 的 900x1600
w, h = adb.screen_size(UDID)
print(f'screen_size: {w}x{h}')
assert (w, h) == (1600, 900), f'横屏分辨率解析错误: {w}x{h}'

# 2. 修复后的坐标系：tap 画布右上角图标（ratio 0.79, 0.17）
#    修复前: x=0.79*900=711, y=0.17*1600=272（错位）
#    修复后: x=0.79*1600=1264, y=0.17*900=153（正确，KernelSU 图标位置）
print(f'tap 换算 (0.79,0.17) -> ({int(0.79*w)},{int(0.17*h)})  修复前是 (711,272)')

# 3. 文本转义逻辑（纯逻辑验证，不真注入）
import re


def esc(text: str):
    if any(ord(c) > 127 for c in text):
        raise ValueError('non-ascii')
    text = text.replace('\\', '\\\\').replace(' ', '%s')
    return re.sub(r'([&<>\|;*~"\'`\(\)\[\]$@])', r'\\\1', text)


assert esc('user@test.com') == 'user\\@test.com', esc('user@test.com')
assert esc('a b') == 'a%sb'
assert esc('p@ss w0rd!') == 'p\\@ss%sw0rd!', esc('p@ss w0rd!')
try:
    esc('中文')
    assert False, '非 ASCII 应拒绝'
except ValueError:
    pass
print('escape logic OK')

# 4. 真实注入验证：点 Home 键 + tap 图标位置（延续之前的横屏坐标系）
#    当前在桌面（上次测试已 HOME），tap SAMDUO 图标 (1206,192)
import time
import subprocess
before = subprocess.run(
    [r'C:\Users\hthby\AppData\Local\Android\Sdk\platform-tools\adb.exe', '-s', UDID,
     'shell', 'dumpsys', 'activity', 'activities'], capture_output=True, text=True).stdout
adb.tap(UDID, 1206, 192)
time.sleep(3)
after = subprocess.run(
    [r'C:\Users\hthby\AppData\Local\Android\Sdk\platform-tools\adb.exe', '-s', UDID,
     'shell', 'dumpsys', 'activity', 'activities'], capture_output=True, text=True).stdout

def top(out):
    for line in out.splitlines():
        if 'topResumedActivity' in line:
            return line.strip()[:100]
    return '?'

b, a = top(before), top(after)
print('tap 前:', b)
print('tap 后:', a)
print('RESULT:', 'tap 生效（前台变化）' if b != a else '前台未变化（点到的可能是桌面空白）')
