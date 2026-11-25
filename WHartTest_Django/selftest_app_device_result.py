#!/usr/bin/env python
"""APP 设备结果回传落库自测（端到端，模拟执行器）。

流程：
  1. 在数据库创建临时 UiDeviceProfile（status=stopped）
  2. 以执行器身份通过真实 WebSocket 连接后端
  3. 发送 APP_DEVICE_RESULT（action=start, status=running）
  4. 断言数据库状态已变为 running
  5. 发送 APP_DEVICE_RESULT（action=stop, status=stopped）
  6. 断言数据库状态回到 stopped
  7. 清理临时记录

用法（需先启动后端）：
    .venv/Scripts/python.exe selftest_app_device_result.py
"""

import asyncio
import os
import sys

BASE = 'd:/platform_test/WHartTest/WHartTest_Django'
sys.path.insert(0, BASE)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wharttest_django.settings')
# 本地 WS 直连，绕过系统代理（websockets 库会读取 http_proxy）
os.environ['NO_PROXY'] = '127.0.0.1,localhost'
os.environ['no_proxy'] = '127.0.0.1,localhost'

WS_TOKEN = os.environ.get('UI_WS_ACTUATOR_TOKEN', 'OE6JhszK24hqgPSMWQbQ4BTuSzriaqL-')
WS_URL = f'ws://127.0.0.1:8000/ws/ui/actuator/?id=selftest-actuator&token={WS_TOKEN}'

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = ''):
    line = f'[{"PASS" if ok else "FAIL"}] {name}' + (f' - {detail}' if detail else '')
    print(line)
    (PASSED if ok else FAILED).append(name)


def setup_django():
    import django
    django.setup()


def create_profile() -> int:
    from django.contrib.auth import get_user_model
    from ui_automation.models import Project, UiDeviceProfile
    U = get_user_model()
    user, _ = U.objects.get_or_create(username='selftest_user', defaults={'is_active': True})
    project, _ = Project.objects.get_or_create(name='selftest_project')
    profile, _ = UiDeviceProfile.objects.update_or_create(
        project=project, name='selftest_device',
        defaults={
            'avd_name': 'SelfTest_AVD',
            'android_version': '14',
            'device_name': 'Pixel 6',
            'screen_resolution': '',
            'status': 'stopped',
            'creator': user,
        },
    )
    return profile.id


def get_status(profile_id: int) -> str:
    from ui_automation.models import UiDeviceProfile
    return UiDeviceProfile.objects.get(id=profile_id).status


def cleanup(profile_id: int):
    from ui_automation.models import UiDeviceProfile
    UiDeviceProfile.objects.filter(id=profile_id).delete()


def build_payload(args: dict) -> str:
    from ui_automation.socket_models import (
        SocketDataModel, QueueModel, ResponseCode, NoticeType, UiSocketEnum,
    )
    payload = SocketDataModel(
        code=ResponseCode.SUCCESS,
        msg='result',
        user='selftest_user',
        is_notice=NoticeType.WEB,
        data=QueueModel(func_name=UiSocketEnum.APP_DEVICE_RESULT, func_args=args),
    )
    return payload.model_dump_json()


async def run(profile_id: int):
    import websockets
    from asgiref.sync import sync_to_async

    async with websockets.connect(WS_URL) as ws:
        print('执行器 WebSocket 已连接')

        # 步骤 3：发送 running
        await ws.send(build_payload({
            'action': 'start', 'status': 'running',
            'avd_name': 'SelfTest_AVD', 'udid': 'emulator-5556',
        }))
        await asyncio.sleep(1.5)
        status = await sync_to_async(get_status)(profile_id)
        check('start/running 落库', status == 'running', f'status={status}')

        # 步骤 5：发送 stopped
        await ws.send(build_payload({
            'action': 'stop', 'status': 'stopped',
            'avd_name': 'SelfTest_AVD',
        }))
        await asyncio.sleep(1.5)
        status = await sync_to_async(get_status)(profile_id)
        check('stop/stopped 落库', status == 'stopped', f'status={status}')

        # 错误场景
        await ws.send(build_payload({
            'action': 'start', 'status': 'error',
            'avd_name': 'SelfTest_AVD', 'message': 'mock failure',
        }))
        await asyncio.sleep(1.5)
        status = await sync_to_async(get_status)(profile_id)
        check('error 落库', status == 'error', f'status={status}')


def main() -> int:
    setup_django()
    print('=== APP 设备结果落库自测 ===')
    profile_id = create_profile()
    print(f'临时设备记录: id={profile_id}')
    try:
        asyncio.run(run(profile_id))
    except Exception as exc:
        check('端到端链路', False, repr(exc))
    finally:
        cleanup(profile_id)
    print(f'=== 结果: {len(PASSED)} passed, {len(FAILED)} failed ===')
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
