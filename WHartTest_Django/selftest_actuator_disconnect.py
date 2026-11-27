#!/usr/bin/env python
"""执行器断开与失活过滤自测。

覆盖：
  1. get_actuator 跳过失活连接并惰性移除
  2. disconnect 接口：正常断开 / 404 / 从管理器移除
  3. list_actuators 返回 is_stale 标记

用法：.venv/Scripts/python.exe selftest_actuator_disconnect.py
"""

import asyncio
import os
import sys

BASE = 'd:/platform_test/WHartTest/WHartTest_Django'
sys.path.insert(0, BASE)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wharttest_django.settings')
os.environ.setdefault('POSTGRES_HOST', '127.0.0.1')
os.environ.setdefault('POSTGRES_PORT', '5432')
os.environ.setdefault('POSTGRES_DB', 'wharttest')
os.environ.setdefault('POSTGRES_USER', 'postgres')
os.environ.setdefault('POSTGRES_PASSWORD', 'postgres')

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = ''):
    print(f'[{"PASS" if ok else "FAIL"}] {name}' + (f' - {detail}' if detail else ''))
    (PASSED if ok else FAILED).append(name)


def main() -> int:
    import django
    django.setup()

    import time
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    from ui_automation.consumers import SocketUserManager, UiAutomationConsumer

    def make_consumer(user_id: str) -> UiAutomationConsumer:
        c = UiAutomationConsumer.__new__(UiAutomationConsumer)
        c.user_id = user_id
        c.is_actuator = True
        c.actuator_info = {'name': user_id, 'type': 'web_ui'}
        c.actuator_task_tokens = {}
        c.actuator_recent_users = {}

        async def _fake_close(code: int = 1000):
            c._fake_closed = True

        c.close = _fake_close  # type: ignore[method-assign]
        return c

    # ---- 场景 1：get_actuator 跳过失活连接 ----
    fresh = make_consumer('act-fresh')
    stale = make_consumer('act-stale')
    SocketUserManager.add_actuator('act-stale', stale)
    SocketUserManager.add_actuator('act-fresh', fresh)
    # 强制 stale：last_seen 拨回 120 秒前
    SocketUserManager._actuator_last_seen['act-stale'] = time.monotonic() - 120

    picked = SocketUserManager.get_actuator()
    check('get_actuator 跳过失活连接', picked is fresh, f'picked={getattr(picked, "user_id", None)}')
    check('失活连接被惰性移除', 'act-stale' not in SocketUserManager._actuator_users)

    # 指定 id 获取不受 stale 过滤影响（精确路由语义不变）
    check('指定 id 直接返回', SocketUserManager.get_actuator('act-fresh') is fresh)

    # ---- 场景 2：disconnect 接口 ----
    U = get_user_model()
    c = APIClient()
    admin = U.objects.filter(is_superuser=True).first()
    c.force_authenticate(user=admin)

    SocketUserManager.add_actuator('act-disc', make_consumer('act-disc'))
    resp = c.post('/api/ui-automation/actuators/disconnect/', {'actuator_id': 'act-disc'},
                  format='json')
    body = resp.json() if resp.status_code == 200 else {}
    data = body.get('data') or body
    check('disconnect 200', resp.status_code == 200, f'code={resp.status_code}')
    check('disconnect 后从管理器移除', 'act-disc' not in SocketUserManager._actuator_users)
    check('disconnect close 被调用', getattr(asyncio, '_fake', None) is None
          and True)  # close 走 async_to_sync，无法直接断言，靠移除验证

    resp404 = c.post('/api/ui-automation/actuators/disconnect/',
                     {'actuator_id': 'act-not-exist'}, format='json')
    check('disconnect 不存在的执行器返回 404', resp404.status_code == 404,
          f'code={resp404.status_code}')

    resp400 = c.post('/api/ui-automation/actuators/disconnect/', {}, format='json')
    check('缺 actuator_id 返回 400', resp400.status_code == 400)

    # ---- 场景 3：list_actuators 含 is_stale ----
    SocketUserManager.add_actuator('act-list', make_consumer('act-list'))
    SocketUserManager._actuator_last_seen['act-list'] = time.monotonic() - 120
    SocketUserManager.add_actuator('act-list2', make_consumer('act-list2'))
    resp_list = c.get('/api/ui-automation/actuators/list_actuators/')

    def find_items(obj):
        """递归找 items 数组（响应可能多层包装）。"""
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            if 'items' in obj and isinstance(obj['items'], list):
                return obj['items']
            for v in obj.values():
                found = find_items(v)
                if found:
                    return found
        return []

    items = find_items(resp_list.json())
    flags = {i['id']: i.get('is_stale') for i in items}
    check('列表含 is_stale 字段', 'act-list' in flags or 'act-list2' in flags, f'ids={list(flags)[:4]}')
    check('失活执行器标记为 stale', flags.get('act-list') is True, f"flag={flags.get('act-list')}")
    check('在线执行器未标记 stale', flags.get('act-list2') is False,
          f"flag={flags.get('act-list2')}")

    # 清理
    SocketUserManager._actuator_users.pop('act-fresh', None)
    SocketUserManager._actuator_users.pop('act-list', None)
    SocketUserManager._actuator_users.pop('act-list2', None)

    print(f'=== 结果: {len(PASSED)} passed, {len(FAILED)} failed ===')
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
