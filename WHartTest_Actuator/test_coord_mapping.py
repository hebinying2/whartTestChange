"""坐标系映射实验：确定 Appium page_source 坐标 → 物理显示(tap)坐标的映射。

步骤：
1. attach EMS app（portrait app 在横屏模拟器上）
2. page_source 找一个可点击节点，记录 dump 系中心 (cx, cy)
3. Appium clickGesture 点击（Appium 系内自洽，一定生效）
4. 对比点击前后截图 diff 质心 → 得到该节点在物理显示系的位置 (x_s, y_s)
5. 输出 (cx, cy) → (x_s, y_s) 推映射
"""
import io
import struct
import subprocess
import sys
import time
import zlib

sys.path.insert(0, '.')

ADB = r'C:\Users\hthby\AppData\Local\Android\Sdk\platform-tools\adb.exe'
UDID = 'emulator-5554'


def adb(*args, binary=False):
    r = subprocess.run([ADB, '-s', UDID, *args], capture_output=True)
    return r.stdout if binary else r.stdout.decode('utf-8', errors='replace')


def png_pixels(data: bytes):
    """极简 PNG 解码（RGB/RGBA 非隔行）→ (w, h, 像素字节)"""
    import zlib as _z
    w, h = struct.unpack('>II', data[16:24])
    pos = 8
    idat = b''
    while pos < len(data):
        ln = struct.unpack('>I', data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        if typ == b'IDAT':
            idat += data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
    raw = _z.decompress(idat)
    # 假设 color type 6 (RGBA) 或 2 (RGB), 8bit
    ct = data[25]
    bpp = 4 if ct == 6 else 3
    stride = w * bpp + 1
    out = bytearray(w * h * bpp)
    prev = bytearray(w * bpp)
    for y in range(h):
        row = raw[y * stride:(y + 1) * stride]
        f = row[0]
        cur = bytearray(row[1:])
        if f == 1:
            for i in range(bpp, len(cur)):
                cur[i] = (cur[i] + cur[i - bpp]) & 0xFF
        elif f == 2:
            for i in range(len(cur)):
                cur[i] = (cur[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(len(cur)):
                left = cur[i - bpp] if i >= bpp else 0
                cur[i] = (cur[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(len(cur)):
                a = cur[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                cur[i] = (cur[i] + pr) & 0xFF
        out[y * w * bpp:(y + 1) * w * bpp] = cur
        prev = cur
    return w, h, bytes(out)


def diff_centroid(d1, d2):
    w, h, p1 = png_pixels(d1)
    _, _, p2 = png_pixels(d2)
    bpp = len(p1) // (w * h)
    sx = sy = n = 0
    step = 8  # 采样加速
    for y in range(0, h, step):
        for x in range(0, w, step):
            i = (y * w + x) * bpp
            d = abs(p1[i] - p2[i]) + abs(p1[i + 1] - p2[i + 1]) + abs(p1[i + 2] - p2[i + 2])
            if d > 60:
                sx += x
                sy += y
                n += 1
    return (sx // n, sy // n, n) if n else None


from appium_executor import AppiumExecutor
import app_elements

ex = AppiumExecutor()
caps = ex.build_capabilities(udid=UDID, device_name=UDID, app_package='com.samduo.ems')
caps.update({'forceAppLaunch': False, 'appWaitForLaunch': False,
             'appWaitActivity': '*', 'skipDeviceInitialization': True})
ex.start_session(caps)
target = None
try:
    ex._driver.update_settings({'waitForIdleTimeout': 0})
    time.sleep(2)
    xml = ex._driver.page_source
    nodes = app_elements.parse_ui_xml(xml)
    # 选一个非全屏、明显可点的节点
    cands = [n for n in nodes if n['rect']['w'] < 900 and n['rect']['h'] < 400]
    print('候选节点:')
    for n in cands[:6]:
        r = n['rect']
        print(f"  {n['locator_value'][:50]} bounds={n['bounds']} center=({r['cx']},{r['cy']})")
    target = cands[0] if cands else None
    if not target:
        print('无可点击候选')
        sys.exit(0)

    before = adb('exec-out', 'screencap', '-p', binary=True)
    cx, cy = target['rect']['cx'], target['rect']['cy']
    ex._driver.execute_script('mobile: clickGesture', {'x': cx, 'y': cy})
    time.sleep(2.5)
    after = adb('exec-out', 'screencap', '-p', binary=True)
finally:
    ex.close_session()

c = diff_centroid(before, after)
if not c:
    print('点击后画面无变化（节点可能是静态按钮）——换一个界面元素重试')
    sys.exit(0)
x_s, y_s, n = c
print(f'dump 中心=({cx},{cy})  物理显示 diff 质心=({x_s},{y_s}) 变化点数={n}')
H_p, W_p = 1600, 900  # 面板 portrait 尺寸
print('候选映射:')
print(f'  A 直用        : ({cx},{cy})')
print(f'  B (cy,cx)     : ({cy},{cx})')
print(f'  C (H-y, x)    : ({H_p - cy},{cx})')
print(f'  D (y, W-x)    : ({cy},{W_p - cx})')
