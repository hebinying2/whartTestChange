#!/usr/bin/env python
"""APP 用例执行链路自测（不依赖真实模拟器/Appium server）。

覆盖：
  1. UiTestCase APP 字段（case_type/app_package/app_steps/device_profile）
  2. app-execute-data 接口返回结构（执行器视角）
  3. AppiumExecutor caps 构建（v4+ options 兼容路径）
  4. execute_simple_steps 动作分发（用桩驱动，验证 launch_app/press_back/swipe/wait/screenshot/断言）

用法：
    .venv/Scripts/python.exe selftest_app_case.py
"""

import os
import sys

BASE_DJANGO = 'd:/platform_test/WHartTest/WHartTest_Django'
BASE_ACTUATOR = 'd:/platform_test/WHartTest/WHartTest_Actuator'
sys.path.insert(0, BASE_DJANGO)
sys.path.insert(0, BASE_ACTUATOR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wharttest_django.settings')

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = ''):
    line = f'[{"PASS" if ok else "FAIL"}] {name}' + (f' - {detail}' if detail else '')
    print(line)
    (PASSED if ok else FAILED).append(name)


def _unwrap(resp_json: dict) -> dict:
    """项目统一响应包装 {status, code, message, data, errors} -> data。"""
    if isinstance(resp_json, dict) and 'data' in resp_json and 'status' in resp_json:
        return resp_json['data'] or {}
    return resp_json or {}


def test_model_and_api():
    """模型字段 + app-execute-data 接口结构（走 Django test client）。"""
    import django
    django.setup()

    from django.contrib.auth import get_user_model
    from ui_automation.models import Project, UiDeviceProfile, UiModule, UiTestCase

    U = get_user_model()
    user, _ = U.objects.get_or_create(username='selftest_user',
                                      defaults={'is_active': True, 'is_superuser': True})
    # DjangoModelPermissions 要求模型权限，直接给超级用户
    user.is_superuser = True
    user.is_staff = True
    user.save(update_fields=['is_superuser', 'is_staff'])
    project, _ = Project.objects.get_or_create(name='selftest_project')
    module, _ = UiModule.objects.get_or_create(
        name='selftest_module', project=project)
    device, _ = UiDeviceProfile.objects.update_or_create(
        project=project, name='selftest_device',
        defaults={'avd_name': 'SelfTest_AVD', 'android_version': '14',
                  'device_name': 'Pixel 6', 'status': 'running', 'creator': user})
    case, _ = UiTestCase.objects.update_or_create(
        project=project, module=module, name='selftest_app_case',
        defaults={
            'case_type': 'app',
            'app_package': 'com.example.app',
            'app_activity': '.MainActivity',
            'app_steps': [
                {'step_id': 1, 'operation_type': 'launch_app', 'value': 'com.example.app'},
                {'step_id': 2, 'operation_type': 'click',
                 'locator': {'locator_type': 'resource_id', 'locator_value': 'btn_login'}},
                {'step_id': 3, 'operation_type': 'assert_visible',
                 'locator': {'locator_type': 'resource_id', 'locator_value': 'home'}},
                {'step_id': 4, 'operation_type': 'press_back'},
                {'step_id': 5, 'operation_type': 'screenshot'},
            ],
            'device_profile': device,
            'creator': user,
        })

    # 模型字段
    check('case_type=app 持久化', case.case_type == 'app')
    check('app_steps JSON 持久化', len(case.app_steps) == 5)
    check('device_profile 绑定', case.device_profile_id == device.id)

    # app-execute-data 接口（执行器视角，走 test client）
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=user)
    resp = client.get(f'/api/ui-automation/testcases/{case.id}/app-execute-data/')
    check('app-execute-data 200', resp.status_code == 200, f'code={resp.status_code}')
    payload = _unwrap(resp.json())
    check('接口含 app_package', payload.get('app_package') == 'com.example.app')
    check('接口含 app_steps(5)', len(payload.get('app_steps') or []) == 5)
    check('接口含 device.avd_name', (payload.get('device') or {}).get('avd_name') == 'SelfTest_AVD')

    # 非 APP 用例应被拒绝
    web_case, _ = UiTestCase.objects.get_or_create(
        project=project, module=module, name='selftest_web_case',
        defaults={'case_type': 'web', 'creator': user})
    resp2 = client.get(f'/api/ui-automation/testcases/{web_case.id}/app-execute-data/')
    check('非 APP 用例返回 400', resp2.status_code == 400, f'code={resp2.status_code}')

    # case_type 过滤
    resp3 = client.get('/api/ui-automation/testcases/',
                       {'project': project.id, 'case_type': 'app'})
    data3 = _unwrap(resp3.json()) if resp3.status_code == 200 else {}
    if isinstance(data3, list):
        items3 = data3
    else:
        items3 = data3.get('items') or data3.get('results') or []
    names = [item['name'] for item in items3]
    check('case_type=app 过滤生效', resp3.status_code == 200 and 'selftest_app_case' in names
          and 'selftest_web_case' not in names, f'names={names}')

    # ---- 编辑保存链路（前端 openEdit 依赖详情接口回显 APP 字段）----
    # 列表行是精简字段，不含 app_package/app_steps（前端拿它回显会丢数据）
    row = next((i for i in items3 if i['name'] == 'selftest_app_case'), None)
    if row is not None:
        check('列表行不含 app_steps（精简字段）', 'app_steps' not in row,
              f"keys={sorted(row.keys())[:8]}...")
        check('列表行含 case_type=app', row.get('case_type') == 'app')

    # 详情接口应含完整 APP 字段（编辑回显数据源）
    resp4 = client.get(f'/api/ui-automation/testcases/{case.id}/')
    detail = _unwrap(resp4.json()) if resp4.status_code == 200 else {}
    check('详情含 app_package', detail.get('app_package') == 'com.example.app')
    check('详情含 app_steps(5)', len(detail.get('app_steps') or []) == 5)
    check('详情含 app_activity', detail.get('app_activity') == '.MainActivity')
    check('详情含 device_profile', detail.get('device_profile') == device.id)

    # 编辑保存（PATCH）后不丢字段
    resp5 = client.patch(
        f'/api/ui-automation/testcases/{case.id}/',
        {'app_package': 'com.edited.app',
         'app_steps': [{'step_id': 1, 'operation_type': 'press_back'}]},
        format='json')
    case.refresh_from_db()
    check('PATCH 保存 app_package', resp5.status_code == 200
          and case.app_package == 'com.edited.app',
          f"code={resp5.status_code} package={case.app_package}")
    check('PATCH 保存 app_steps', len(case.app_steps) == 1)
    check('PATCH 未清空未提交字段', case.app_activity == '.MainActivity')

    # 还原数据
    UiTestCase.objects.filter(id=case.id).update(
        app_package='com.example.app',
        app_steps=[
            {'step_id': 1, 'operation_type': 'launch_app', 'value': 'com.example.app'},
            {'step_id': 2, 'operation_type': 'click',
             'locator': {'locator_type': 'resource_id', 'locator_value': 'btn_login'}},
            {'step_id': 3, 'operation_type': 'assert_visible',
             'locator': {'locator_type': 'resource_id', 'locator_value': 'home'}},
            {'step_id': 4, 'operation_type': 'press_back'},
            {'step_id': 5, 'operation_type': 'screenshot'},
        ])

    # 清理
    UiTestCase.objects.filter(id__in=[case.id, web_case.id]).delete()
    device.delete()


def test_appium_executor():
    """AppiumExecutor：caps 构建 + 步骤动作分发（桩驱动，无真实 Appium）。"""
    import time
    from appium_executor import AppiumExecutor

    executor = AppiumExecutor()

    # caps 构建
    caps = executor.build_capabilities(
        udid='emulator-5556', device_name='Pixel 6',
        app_package='com.example.app', app_activity='.MainActivity')
    check('caps 含 udid/platformName', caps.get('udid') == 'emulator-5556'
          and caps.get('platformName') == 'Android')
    check('caps 含 appPackage/appActivity', caps.get('appPackage') == 'com.example.app'
          and caps.get('appActivity') == '.MainActivity')

    # 桩驱动步骤执行
    calls: list[tuple] = []
    executor._driver = True  # 仅绕过 session 检查

    executor.activate_app = lambda pkg: calls.append(('activate', pkg))  # type: ignore
    executor.press_back = lambda: calls.append(('back',))  # type: ignore
    executor.swipe = lambda *a: calls.append(('swipe', a))  # type: ignore
    executor.screenshot = lambda p: (calls.append(('screenshot', p)), p)[1]  # type: ignore

    steps = [
        {'step_id': 1, 'operation_type': 'wait', 'value': 0.1},
        {'step_id': 2, 'operation_type': 'launch_app', 'value': 'com.example.app'},
        {'step_id': 3, 'operation_type': 'press_back'},
        {'step_id': 4, 'operation_type': 'swipe', 'value': '100,800,100,200,300'},
        {'step_id': 5, 'operation_type': 'screenshot'},
        {'step_id': 6, 'operation_type': 'input',
         'locator': {'locator_type': 'resource_id', 'locator_value': 'x'}, 'value': 'hi'},
    ]
    result = executor.execute_simple_steps(steps, screenshot_dir='./data/selftest')
    # screenshot 调用 2 次：step5 主动截图 + step6 失败自动截图
    check('前 5 步动作正确分发', len(calls) == 5
          and calls[0] == ('activate', 'com.example.app')
          and calls[1] == ('back',)
          and calls[2] == ('swipe', (100, 800, 100, 200, 300))
          and calls[3][0] == 'screenshot' and calls[4][0] == 'screenshot',
          f'calls={calls}')
    check('input 步骤失败即 break', result['status'] == 'failed'
          and result['failed_steps'] == 1 and result['passed_steps'] == 5,
          f"passed={result['passed_steps']} failed={result['failed_steps']}")

    # 空 steps
    empty = executor.execute_simple_steps([])
    check('空步骤返回 success', empty['status'] == 'success' and empty['total_steps'] == 0)

    # 非法定位类型报错
    executor2 = AppiumExecutor()
    executor2._driver = True
    bad = executor2.execute_simple_steps([
        {'step_id': 1, 'operation_type': 'click',
         'locator': {'locator_type': 'css', 'locator_value': '.x'}}])
    check('非法定位类型失败', bad['status'] == 'failed'
          and '不支持的 APP 定位类型' in (bad['steps'][0].get('message') or ''))


def main() -> int:
    print('=== APP 用例执行链路自测 ===')
    try:
        test_model_and_api()
    except Exception as exc:
        check('模型/接口自测', False, repr(exc))
    try:
        test_appium_executor()
    except Exception as exc:
        check('AppiumExecutor 自测', False, repr(exc))
    print(f'=== 结果: {len(PASSED)} passed, {len(FAILED)} failed ===')
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
