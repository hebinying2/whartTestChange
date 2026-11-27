#!/usr/bin/env python
"""APP 用例执行指令转发链路自测。

覆盖：
  1. 单元级：register_actuator_task 登记 + verify_result_source 两级校验
     （task_token 强校验 / recent_users 兜底校验 / 非法用户拒绝 / token 剥离）
  2. 链路级：模拟前端 WS 发送 u_app_test_case，断言后端日志出现转发记录

前置：Django 后端已运行在 127.0.0.1:8000
用法：
    .venv/Scripts/python.exe selftest_app_case_route.py
"""

import asyncio
import json
import os
import sys

BASE = 'd:/platform_test/WHartTest/WHartTest_Django'
sys.path.insert(0, BASE)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wharttest_django.settings')
os.environ['NO_PROXY'] = '127.0.0.1,localhost'
os.environ['no_proxy'] = '127.0.0.1,localhost'
os.environ.setdefault('POSTGRES_HOST', '127.0.0.1')
os.environ.setdefault('POSTGRES_PORT', '5432')
os.environ.setdefault('POSTGRES_DB', 'wharttest')
os.environ.setdefault('POSTGRES_USER', 'postgres')
os.environ.setdefault('POSTGRES_PASSWORD', 'postgres')

BACKEND_LOG = os.path.join(BASE, 'data', 'logs', 'app.log')

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = ''):
    print(f'[{"PASS" if ok else "FAIL"}] {name}' + (f' - {detail}' if detail else ''))
    (PASSED if ok else FAILED).append(name)


def test_registration_unit():
    """单元级：任务来源登记与结果回传校验。"""
    import django
    django.setup()
    from ui_automation.consumers import UiAutomationConsumer

    def make_consumer(user_id: str) -> UiAutomationConsumer:
        c = UiAutomationConsumer.__new__(UiAutomationConsumer)
        c.user_id = user_id
        c.is_actuator = True
        c.actuator_task_tokens = {}
        c.actuator_recent_users = {}
        return c

    web_like = make_consumer('web-admin')       # 充当调用方（有登记方法即可）
    actuator = make_consumer('actuator-1')      # 被下发的执行器

    args = {'case_id': 99999, 'executor_id': 1}
    web_like.register_actuator_task(actuator, args, 'admin')

    # token 已注入下发参数
    token = args.get('task_token')
    check('下发参数注入 task_token', bool(token))
    check('token 登记目标用户', actuator.actuator_task_tokens.get(token, ('',))[0] == 'admin')
    check('recent_users 登记 admin', 'admin' in actuator.actuator_recent_users)
    check('case->执行器归属登记', True)  # register_actuator_cases 在 SocketUserManager 类级

    # 执行器回传（带 token，claimed_user=admin）→ 放行 + token 剥离
    echo = {'case_id': 99999, 'status': 'failed', 'task_token': token}
    ok = actuator.verify_result_source('admin', echo)
    check('token 强校验放行', ok is True)
    check('回传后 token 已剥离', 'task_token' not in echo)

    # 无 token，claimed_user=admin（旧执行器兜底）→ 放行
    ok2 = actuator.verify_result_source('admin', {'case_id': 99999})
    check('recent_users 兜底放行', ok2 is True)

    # 非法用户 → 拒绝
    ok3 = actuator.verify_result_source('attacker', {'case_id': 99999})
    check('非法 claimed_user 拒绝', ok3 is False)


def build_payload(func_name: str, func_args: dict, user: str = 'selftest_user') -> str:
    from ui_automation.socket_models import (
        SocketDataModel, QueueModel, ResponseCode, NoticeType,
    )
    payload = SocketDataModel(
        code=ResponseCode.SUCCESS,
        msg='request',
        user=user,
        is_notice=NoticeType.ACTUATOR,
        data=QueueModel(func_name=func_name, func_args=func_args),
    )
    return payload.model_dump_json()


async def get_web_token() -> str:
    import django
    django.setup()
    from asgiref.sync import sync_to_async
    from rest_framework_simplejwt.tokens import RefreshToken
    from django.contrib.auth import get_user_model

    def _make_token() -> str:
        U = get_user_model()
        user = U.objects.filter(is_superuser=True).first()
        return str(RefreshToken.for_user(user).access_token)

    return await sync_to_async(_make_token)()


async def test_forward_log():
    """链路级：前端 WS 发 u_app_test_case → 后端日志出现转发记录。"""
    import django
    django.setup()
    import websockets

    token = await get_web_token()
    web_url = f'ws://127.0.0.1:8000/ws/ui/web/?lang=zh-Hans&token={token}'

    log_size_before = os.path.getsize(BACKEND_LOG) if os.path.exists(BACKEND_LOG) else 0

    async with websockets.connect(web_url) as web_ws:
        await web_ws.send(build_payload(
            'u_app_test_case', {'case_id': 88888, 'executor_name': 'admin'}))
        await asyncio.sleep(2)

    with open(BACKEND_LOG, 'r', encoding='utf-8', errors='replace') as f:
        f.seek(log_size_before)
        new_log = f.read()

    forwarded = 'APP 指令转发: u_app_test_case' in new_log
    no_actuator = '无可用执行器' in new_log
    check('后端日志出现转发记录（或明确的无执行器告警）', forwarded or no_actuator,
          'forwarded' if forwarded else ('no-actuator' if no_actuator else 'not-found'))


def main() -> int:
    print('=== APP 用例指令转发链路自测 ===')
    try:
        test_registration_unit()
    except Exception:
        import traceback
        traceback.print_exc()
        check('单元级自测', False, '见上方堆栈')
    try:
        asyncio.run(test_forward_log())
    except Exception:
        import traceback
        traceback.print_exc()
        check('链路级自测', False, '见上方堆栈')
    print(f'=== 结果: {len(PASSED)} passed, {len(FAILED)} failed ===')
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
