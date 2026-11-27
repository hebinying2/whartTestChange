"""阶段 3/4 链路自测：APP 实时画面定向转发 + 元素采集路由。"""
import asyncio
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wharttest_django.settings')

_results = []
def check(name, ok, detail=''):
    _results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail and not ok else ''))


def main():
    os.environ.setdefault('POSTGRES_HOST', '127.0.0.1')
    os.environ.setdefault('POSTGRES_PORT', '5432')
    os.environ.setdefault('POSTGRES_DB', 'wharttest')
    os.environ.setdefault('POSTGRES_USER', 'postgres')
    os.environ.setdefault('POSTGRES_PASSWORD', 'postgres')

    import django
    django.setup()

    from asgiref.sync import async_to_sync
    from ui_automation.consumers import UiAutomationConsumer, SocketUserManager
    from ui_automation.socket_models import UiSocketEnum

    # ---- 枚举完备性 ----
    for name in ('APP_SCREEN_START', 'APP_SCREEN_FRAME', 'APP_SCREEN_INPUT',
                 'APP_SCREEN_STATUS', 'APP_SCREEN_STOP', 'APP_ELEMENTS_DUMP',
                 'APP_ELEMENTS_RESULT'):
        assert getattr(UiSocketEnum, name), name
    check('画面/元素枚举完备', True)

    def make_actuator():
        c = UiAutomationConsumer.__new__(UiAutomationConsumer)
        c.user_id = 'actuator-screen-test'
        c.is_actuator = True
        c._current_func_name = None
        return c

    def make_web(user_id):
        c = UiAutomationConsumer.__new__(UiAutomationConsumer)
        c.user_id = user_id
        c.is_actuator = False
        c.sent = []
        async def _sj(m):
            c.sent.append(json.loads(m.model_dump_json()))
        c.send_json = _sj
        return c

    act = make_actuator()
    web_admin = make_web('admin')
    web_other = make_web('other_user')
    SocketUserManager._web_users['admin'] = web_admin
    SocketUserManager._web_users['other_user'] = web_other

    # ---- 1. 帧按 user 定向：admin 收到，other_user 不收到 ----
    act._current_func_name = UiSocketEnum.APP_SCREEN_FRAME
    async_to_sync(act.handle_app_screen_frame)(
        {'frame': {'data': 'fake-b64'}}, 'admin')
    got_admin = [m for m in web_admin.sent
                 if m['data']['func_name'] == UiSocketEnum.APP_SCREEN_FRAME]
    got_other = [m for m in web_other.sent
                 if m['data']['func_name'] == UiSocketEnum.APP_SCREEN_FRAME]
    check('帧定向转发给发起人 admin', len(got_admin) == 1
          and got_admin[0]['data']['func_args']['frame']['data'] == 'fake-b64')
    check('帧不发给其他用户 other_user', len(got_other) == 0)

    # ---- 2. 发起人断线时帧静默丢弃（不抛异常） ----
    SocketUserManager._web_users.pop('admin', None)
    act._current_func_name = UiSocketEnum.APP_SCREEN_FRAME
    async_to_sync(act.handle_app_screen_frame)(
        {'frame': {'data': 'x'}}, 'admin')
    check('发起人断线帧丢弃', True)
    SocketUserManager._web_users['admin'] = web_admin

    # ---- 3. task_token 剥离（帧消息不回显令牌） ----
    SocketUserManager._web_users['admin'] = web_admin
    web_admin.sent.clear()
    act._current_func_name = UiSocketEnum.APP_SCREEN_FRAME
    async_to_sync(act.handle_app_screen_frame)(
        {'frame': {'data': 'y'}, 'task_token': 'tok-123'}, 'admin')
    m = [m for m in web_admin.sent
         if m['data']['func_name'] == UiSocketEnum.APP_SCREEN_FRAME][0]
    check('帧消息剥离 task_token', 'task_token' not in m['data']['func_args'])

    # ---- 4. 元素采集结果定向转发 ----
    web_admin.sent.clear()
    act._current_func_name = UiSocketEnum.APP_ELEMENTS_RESULT
    async_to_sync(act.handle_app_elements_result)(
        {'status': 'success', 'nodes': [{'locator_type': 'resource_id'}], 'count': 1},
        'admin')
    got = [m for m in web_admin.sent
           if m['data']['func_name'] == UiSocketEnum.APP_ELEMENTS_RESULT]
    check('元素采集结果定向转发', len(got) == 1 and got[0]['data']['func_args']['count'] == 1)

    # ---- 5. 前端指令路由注册（画面 3 消息 + 元素 dump 均映射到转发 handler） ----
    web_c = UiAutomationConsumer.__new__(UiAutomationConsumer)
    web_c.is_actuator = False
    # 直接检查 route_message 的映射表（重放 handler_map 构造逻辑）
    import inspect
    src = inspect.getsource(UiAutomationConsumer.route_message)
    for fn in ('APP_SCREEN_START', 'APP_SCREEN_INPUT', 'APP_SCREEN_STOP',
               'APP_ELEMENTS_DUMP'):
        assert fn in src, fn
    check('前端画面/采集指令已注册转发路由', True)

    # ---- 6. 执行器消息路由注册 ----
    src = inspect.getsource(UiAutomationConsumer.route_message)
    assert 'APP_SCREEN_FRAME: self.handle_app_screen_frame' in src
    assert 'APP_ELEMENTS_RESULT: self.handle_app_elements_result' in src
    check('执行器帧/元素回传已注册路由', True)

    # ---- 7. 帧消息组广播关闭（handle_case_result 走广播，帧走定向）----
    src = inspect.getsource(UiAutomationConsumer.handle_app_screen_frame)
    assert 'group_send' not in src
    check('帧不走组广播（定向转发）', True)

    for k in ('admin', 'other_user'):
        SocketUserManager._web_users.pop(k, None)

    passed = sum(1 for _, ok, _ in _results if ok)
    failed = len(_results) - passed
    print(f'=== 结果: {passed} passed, {failed} failed ===')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
