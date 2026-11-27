"""Appium Android 执行器（APP UI 自动化第一版）。

只支持原生 APP 的基础操作与断言；Hybrid / 复杂手势不在第一版范围。
"""

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger('actuator.appium')


class AppiumExecutor:
    """基于 Appium UiAutomator2 的原生 APP 执行器。"""

    def __init__(self, *, appium_server_url: str = 'http://127.0.0.1:4723', timeout: int = 30):
        self.appium_server_url = appium_server_url.rstrip('/')
        self.timeout = timeout
        self._driver: Any = None

    def build_capabilities(self, *, udid: str, device_name: str,
                           app_package: str | None = None,
                           app_activity: str | None = None,
                           app_path: str | None = None) -> dict:
        """构建 Android UiAutomator2 capabilities。"""
        caps = {
            'platformName': 'Android',
            'automationName': 'UiAutomator2',
            'deviceName': device_name,
            'udid': udid,
            'newCommandTimeout': 300,
            'autoGrantPermissions': True,
        }
        if app_path:
            caps['app'] = str(app_path)
        if app_package:
            caps['appPackage'] = app_package
        if app_activity:
            caps['appActivity'] = app_activity
        return caps

    def start_session(self, capabilities: dict):
        """创建 Appium session（Appium-Python-Client v4+ 需用 Options 对象）。"""
        try:
            from appium import webdriver
            from appium.options.android import UiAutomator2Options
        except ImportError as exc:
            raise RuntimeError('未安装 Appium-Python-Client，无法执行 APP 用例') from exc
        # 异常残留的旧会话先关闭，保证「执行错误后可自动恢复」
        self.close_session()
        logger.info('创建 Appium session: %s', capabilities)
        options = UiAutomator2Options()
        options.load_capabilities(capabilities)
        self._driver = webdriver.Remote(self.appium_server_url, options=options)
        return self._driver

    def press_back(self):
        """按系统返回键。"""
        if not self._driver:
            raise RuntimeError('Appium session 未创建')
        self._driver.back()

    def swipe(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: int = 300):
        """滑动屏幕（绝对坐标）。"""
        if not self._driver:
            raise RuntimeError('Appium session 未创建')
        self._driver.swipe(start_x, start_y, end_x, end_y, duration)

    def activate_app(self, app_package: str):
        """拉起/切换到指定 APP。"""
        if not self._driver:
            raise RuntimeError('Appium session 未创建')
        self._driver.activate_app(app_package)

    def close_session(self):
        """关闭 Appium session。"""
        if self._driver:
            try:
                self._driver.quit()
            except Exception as exc:
                logger.warning('关闭 Appium session 失败: %r', exc)
            finally:
                self._driver = None

    def page_source_skip_idle(self, *, udid: str, device_name: str,
                              app_package: str) -> str:
        """采集控件树 XML（绕过 idle 检测，元素采集降级通道）。

        adb uiautomator dump 在页面存在持续动画（图表刷新/加载动效）时
        会一直报 "could not get idle state"。此方法用 Appium attach 到
        前台应用（不重启），并置 waitForIdleTimeout=0，page_source
        不再等待界面静止。返回 XML 与 uiautomator dump 同构。
        """
        caps = self.build_capabilities(
            udid=udid, device_name=device_name, app_package=app_package)
        # attach 到已在运行的 app，不重启（重启会破坏录制现场）
        caps['forceAppLaunch'] = False
        caps['appWaitForLaunch'] = False
        caps['appWaitActivity'] = '*'
        caps['skipDeviceInitialization'] = True
        self.start_session(caps)
        try:
            try:
                self._driver.update_settings({'waitForIdleTimeout': 0})
            except Exception as exc:
                logger.warning('设置 waitForIdleTimeout 失败（继续采集）: %r', exc)
            # attach 后 a11y 树就绪需要数秒，立即取 page_source 只会拿到
            # 空壳 FrameLayout（实测）；等待后才有完整控件树
            import time
            time.sleep(3)
            return self._driver.page_source
        finally:
            self.close_session()

    def _locator(self, locator_type: str, locator_value: str) -> tuple[str, str]:
        """将平台定位表达式转换为 Appium 定位器。"""
        from appium.webdriver.common.appiumby import AppiumBy

        normalized = locator_type.strip().lower()
        if normalized in ('accessibility_id', 'accessibility-id'):
            return AppiumBy.ACCESSIBILITY_ID, locator_value
        if normalized in ('android_id', 'resource_id', 'resource-id'):
            return AppiumBy.ID, locator_value
        if normalized in ('android_xpath', 'xpath'):
            return AppiumBy.XPATH, locator_value
        if normalized == 'class_name':
            return AppiumBy.CLASS_NAME, locator_value
        if normalized == 'uiautomator':
            return AppiumBy.ANDROID_UIAUTOMATOR, locator_value
        raise ValueError(f'不支持的 APP 定位类型: {locator_type}')

    def find_element(self, locator_type: str, locator_value: str, timeout: int = 10) -> Any:
        """按定位表达式查找元素，支持有限等待。"""
        if not self._driver:
            raise RuntimeError('Appium session 未创建')
        from selenium.webdriver.support.ui import WebDriverWait

        by, value = self._locator(locator_type, locator_value)
        return WebDriverWait(self._driver, timeout).until(lambda d: d.find_element(by, value))

    def _run_element_operation(self, operation: str, locator: dict, value: Any = None):
        """执行基础元素操作。"""
        if not isinstance(locator, dict):
            raise ValueError('locator 必须是对象')
        element = self.find_element(
            locator.get('locator_type', ''),
            locator.get('locator_value', ''),
            timeout=int(locator.get('wait_time', 10)),
        )
        op = operation.strip().lower()
        if op == 'click':
            element.click()
        elif op in ('input', 'fill'):
            element.clear()
            element.send_keys(str(value or ''))
        elif op == 'clear':
            element.clear()
        else:
            raise ValueError(f'不支持的 APP 元素操作: {operation}')

    def assert_element(self, locator: dict, *, visible: bool = True) -> bool:
        """断言元素存在或可见。"""
        element = self.find_element(
            locator.get('locator_type', ''),
            locator.get('locator_value', ''),
            timeout=int(locator.get('wait_time', 10)),
        )
        return element.is_displayed() if visible else element is not None

    def screenshot(self, output_path: str) -> str:
        """保存当前设备截图。"""
        if not self._driver:
            raise RuntimeError('Appium session 未创建')
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self._driver.get_screenshot_as_png()
        path.write_bytes(data)
        return str(path)

    def execute_simple_steps(self, steps: list[dict],
                             screenshot_dir: str = './data/screenshots') -> dict:
        """执行简化步骤列表，返回汇总结果。

        step 示例:
        {
            "operation_type": "click",
            "locator": {"locator_type": "accessibility_id",
                        "locator_value": "login",
                        "wait_time": 10},
            "value": "xxx"
        }
        """
        if not steps:
            return {
                'status': 'success',
                'total_steps': 0,
                'passed_steps': 0,
                'failed_steps': 0,
                'steps': [],
            }

        started = time.perf_counter()
        results = []
        passed = 0
        failed = 0
        for index, step in enumerate(steps, start=1):
            step_id = step.get('step_id', index)
            try:
                op = str(step.get('operation_type', 'click')).strip().lower()
                if op in ('wait', 'sleep'):
                    time.sleep(float(step.get('value') or 1))
                elif op in ('launch_app', 'activate_app'):
                    package = str(step.get('value') or step.get('app_package') or '').strip()
                    if not package:
                        raise ValueError('launch_app 需要 value 指定包名')
                    self.activate_app(package)
                elif op == 'press_back':
                    self.press_back()
                elif op in ('swipe', 'scroll'):
                    coords = str(step.get('value') or '').strip()
                    parts = [p.strip() for p in coords.split(',')]
                    if len(parts) < 4:
                        raise ValueError('swipe 需要 value 形如 "x1,y1,x2,y2"')
                    self.swipe(int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]),
                               int(parts[4]) if len(parts) > 4 else 300)
                elif op == 'screenshot':
                    screenshot_path = self.screenshot(
                        str(Path(screenshot_dir) / f'app-step-{step_id}.png'))
                    results.append({'step_id': step_id, 'status': 'success',
                                    'message': '已截图', 'screenshot': screenshot_path,
                                    'duration': 0})
                    passed += 1
                    continue
                elif op.startswith('assert'):
                    self.assert_element(step.get('locator', {}))
                else:
                    self._run_element_operation(
                        op, step.get('locator', {}), step.get('value'))
                passed += 1
                results.append({'step_id': step_id, 'status': 'success',
                                'message': '', 'duration': 0})
            except Exception as exc:
                failed += 1
                try:
                    screenshot_path = self.screenshot(
                        str(Path(screenshot_dir) / f'app-step-{step_id}.png'))
                except Exception:
                    screenshot_path = ''
                results.append({'step_id': step_id, 'status': 'failed',
                                'message': str(exc), 'screenshot': screenshot_path,
                                'duration': 0})
                break

        duration = round(time.perf_counter() - started, 2)
        return {
            'status': 'success' if failed == 0 else 'failed',
            'total_steps': len(steps),
            'passed_steps': passed,
            'failed_steps': failed,
            'duration': duration,
            'steps': results,
        }
