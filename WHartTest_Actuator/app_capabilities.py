"""APP 自动化能力检测与 Appium capabilities 构建。"""

import logging
import os
import shutil

from adb_manager import get_adb_path
from emulator_manager import get_emulator_path

logger = logging.getLogger('actuator.app_capabilities')


def detect_app_tools() -> dict:
    """检测本机 APP 自动化工具链。"""
    appium = shutil.which('appium')
    return {
        'adb': bool(get_adb_path()),
        'emulator': bool(get_emulator_path()),
        'appium': bool(appium),
        'appium_path': appium,
        'android_home': os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT') or '',
    }


def detect_app_capability(*, max_device_slots: int = 1) -> dict:
    """上报给平台的 APP 执行能力。"""
    tools = detect_app_tools()
    return {
        'supported_platforms': ['android'] if tools.get('adb') and tools.get('emulator') else [],
        'supported_device_types': ['emulator'],
        'max_device_slots': max_device_slots,
        'installed_tools': tools,
        'is_ready': all([tools.get('adb'), tools.get('emulator'), tools.get('appium')]),
    }


def build_android_capabilities(*, udid: str, device_name: str,
                               app_package: str | None = None,
                               app_activity: str | None = None,
                               app_path: str | None = None) -> dict:
    """构建第一版 Android UiAutomator2 capabilities。"""
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
