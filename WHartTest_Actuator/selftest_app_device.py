#!/usr/bin/env python
"""APP 设备管理自测脚本。

覆盖链路：
  1. APP 能力检测（adb / emulator / appium）
  2. AVD 列表
  3. 设备状态查询（含未启动场景）
  4. 启动模拟器（已运行时应探测复用，不重复拉起）
  5. 启动后 adb devices 校验 udid 在线
  6. 停止模拟器并校验下线

用法：
    python selftest_app_device.py                # 全量（含启动/停止，约 1~3 分钟）
    python selftest_app_device.py --skip-boot    # 跳过启动/停止，只做只读检查

每次新增或修改 APP 设备相关功能后，运行本脚本做回归自测。
"""

import argparse
import json
import sys

from adb_manager import get_adb_path
from app_capabilities import detect_app_capability
from device_manager import DeviceManager
from emulator_manager import get_emulator_path

DEFAULT_AVD = 'Pixel_6_API_34'
PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = ''):
    mark = 'PASS' if ok else 'FAIL'
    line = f'[{mark}] {name}' + (f' - {detail}' if detail else '')
    print(line)
    (PASSED if ok else FAILED).append(name)


def main() -> int:
    parser = argparse.ArgumentParser(description='APP 设备管理自测')
    parser.add_argument('--skip-boot', action='store_true', help='跳过启动/停止')
    parser.add_argument('--avd', default=DEFAULT_AVD, help='AVD 名称')
    args = parser.parse_args()

    print('=== APP 设备管理自测 ===')

    # 1. 能力检测
    cap = detect_app_capability()
    check('能力检测 adb', cap['installed_tools'].get('adb') is True)
    check('能力检测 emulator', cap['installed_tools'].get('emulator') is True)
    print(f"    installed_tools: {json.dumps(cap['installed_tools'], ensure_ascii=False)}")

    # 2. 工具路径
    check('adb 路径', bool(get_adb_path()), str(get_adb_path()))
    check('emulator 路径', bool(get_emulator_path()), str(get_emulator_path()))

    manager = DeviceManager()

    # 3. AVD 列表
    avds = manager.emulator.list_avds()
    check('AVD 列表非空', bool(avds), f'avds={avds}')
    if args.avd not in avds:
        print(f'[WARN] 目标 AVD {args.avd} 不在本机列表中，后续启动用例将跳过')
        print(f'=== 结果: {len(PASSED)} passed, {len(FAILED)} failed ===')
        return 1 if FAILED else 0

    # 4. 状态查询（启动前）
    status = manager.status(args.avd)
    print(f"    启动前状态: {json.dumps(status, ensure_ascii=False)}")
    check('状态查询返回结构', isinstance(status, dict) and 'status' in status)

    if args.skip_boot:
        print(f'=== 结果: {len(PASSED)} passed, {len(FAILED)} failed ===')
        return 1 if FAILED else 0

    # 5. 启动（若已在运行，修复后的逻辑会探测复用）
    print(f'启动模拟器 {args.avd}（首次冷启动可能需要 1~3 分钟）...')
    try:
        result = manager.start_device(avd_name=args.avd, headless=True, snapshot_enabled=True)
        udid = result.get('udid', '')
        check('启动成功', bool(udid), f'udid={udid}')
    except Exception as exc:
        check('启动成功', False, repr(exc))
        print(f'=== 结果: {len(PASSED)} passed, {len(FAILED)} failed ===')
        return 1

    # 6. adb devices 校验 udid 在线
    online = [d['udid'] for d in manager.adb.devices() if d.get('status') == 'device']
    check('adb devices 可见该设备', udid in online, f'online={online}')

    # 7. 状态查询（启动后应为 running）
    status = manager.status(args.avd)
    check('启动后状态为 running', status.get('status') == 'running',
          f"status={status.get('status')}")

    # 8. 再次启动应复用（不重复拉起、立即返回）
    try:
        again = manager.start_device(avd_name=args.avd, headless=True, snapshot_enabled=True)
        check('重复启动复用同一 udid', again.get('udid') == udid,
              f"udid={again.get('udid')}")
    except Exception as exc:
        check('重复启动复用同一 udid', False, repr(exc))

    # 9. 停止
    try:
        stop_result = manager.stop_device(avd_name=args.avd)
        check('停止成功', stop_result.get('status') == 'stopped')
    except Exception as exc:
        check('停止成功', False, repr(exc))

    # 10. 停止后校验下线（轮询，模拟器退出需要几秒）
    import time
    offline = False
    deadline = time.time() + 15
    while time.time() < deadline:
        status = manager.status(args.avd)
        if status.get('status') == 'stopped':
            offline = True
            break
        time.sleep(2)
    check('停止后状态为 stopped', offline,
          f"status={status.get('status')}")

    print(f'=== 结果: {len(PASSED)} passed, {len(FAILED)} failed ===')
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
