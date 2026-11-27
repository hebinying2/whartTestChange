"""复现问题 1：Home 页 tap 图标是否启动应用（模拟执行器坐标换算链路）。"""
import io
import subprocess
import sys
import time

ADB = r'C:\Users\hthby\AppData\Local\Android\Sdk\platform-tools\adb.exe'
UDID = 'emulator-5554'


def adb(*args, binary=False):
    r = subprocess.run([ADB, '-s', UDID, *args], capture_output=True)
    if binary:
        return r.stdout
    return r.stdout.decode('utf-8', errors='replace')


def focus():
    out = adb('shell', 'dumpsys', 'activity', 'activities')
    for line in out.splitlines():
        line = line.strip()
        if line.startswith('topResumedActivity'):
            return line.split(' ', 1)[1].split(' ')[0].rstrip('}')
    return '?'


def png_size(data: bytes):
    import struct
    w, h = struct.unpack('>II', data[16:24])
    return w, h


def find_icon(data: bytes):
    """找桌面上一个应用图标中心：取截图中非黑像素聚类的简单试探。
    这里不用 CV，改用 uiautomator dump 找图标节点。"""
    return None


print('1. 当前前台:', focus())
print('2. wm size:', adb('shell', 'wm', 'size').strip())
frame = adb('exec-out', 'screencap', '-p', binary=True)
w, h = png_size(frame)
print('3. 截图 PNG 尺寸:', f'{w}x{h}', '（前端 viewport 与 tap 换算基数）')

# 用 uiautomator dump 找一个图标节点（clickable/text/content-desc）
xml = adb('shell', 'uiautomator', 'dump', '/sdcard/uidump_x.xml')
xml = adb('shell', 'cat', '/sdcard/uidump_x.xml')
import re
import xml.etree.ElementTree as ET

try:
    root = ET.fromstring(xml)
except ET.ParseError as exc:
    print('XML 解析失败:', exc, xml[:200])
    sys.exit(1)

icons = []
for el in root.iter('node'):
    a = dict(el.attrib)
    m = re.match(r'\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]', a.get('bounds', ''))
    if not m:
        continue
    x1, y1, x2, y2 = map(int, m.groups())
    if (x2 - x1) < 40 or (y2 - y1) < 40 or (x2 - x1) > (w * 0.5):
        continue
    if a.get('clickable') == 'true' or a.get('text') or a.get('content-desc'):
        icons.append({
            'desc': a.get('content-desc') or a.get('text') or a.get('resource-id'),
            'class': a.get('class'),
            'cx': (x1 + x2) // 2, 'cy': (y1 + y2) // 2,
            'bounds': a.get('bounds'),
        })

print(f'4. 桌面可点击候选节点 {len(icons)} 个（前 10）:')
for ic in icons[:10]:
    print('   ', ic)

if not icons:
    print('没有找到图标节点，退出')
    sys.exit(0)

# 选一个 desc 非空的图标 tap（模拟前端：ratio = cx/w, cy/h）
target = next((i for i in icons if i['desc'] and i['desc'] not in ('workspace',)), icons[0])
ratio_x, ratio_y = target['cx'] / w, target['cy'] / h
print(f"5. 模拟前端点击: ratio=({ratio_x:.4f},{ratio_y:.4f}) -> 像素({int(ratio_x*w)},{int(ratio_y*h)}) 目标={target['desc']}")

before = focus()
r = adb('shell', 'input', 'tap', str(int(ratio_x * w)), str(int(ratio_y * h)))
print('6. input tap 返回码输出:', repr(r)[:80])
time.sleep(3)
after = focus()
print('7. tap 前前台:', before)
print('8. tap 后前台:', after)
print('9. 结论:', 'APP 已启动（tap 链路 OK）' if after != before else '前台未变化（tap 未生效或点在空白处）')
