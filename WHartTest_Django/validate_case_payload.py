"""复现保存 APP 录制用例 400：直接走 serializer 验证。"""
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wharttest_django.settings')
os.environ.setdefault('POSTGRES_HOST', '127.0.0.1')
os.environ.setdefault('POSTGRES_PORT', '5432')
os.environ.setdefault('POSTGRES_DB', 'wharttest')
os.environ.setdefault('POSTGRES_USER', 'postgres')
os.environ.setdefault('POSTGRES_PASSWORD', 'postgres')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import django
django.setup()

from ui_automation.serializers import UiTestCaseSerializer

# 前端 AppScreenViewer.saveAsCase 发出的 payload（与截图 174B 一致量级）
payload = {
    'name': 'APP录制_test',
    'project': 1,
    'module': None,
    'case_type': 'app',
    'app_steps': [
        {'operation_type': 'click', 'locator_type': 'resource_id',
         'locator_value': 'app.lawnchairid/workspace', 'step_id': 1},
    ],
}

s = UiTestCaseSerializer(data=payload)
print('valid:', s.is_valid())
if not s.is_valid():
    print('errors:', s.errors)
else:
    print('OK - payload would save')

# 对照：AppCaseList 页手工创建成功时传的字段（含 priority 等？）
# 打印 model 必填（blank=False 且无 default）字段
from ui_automation.models import UiTestCase
required = []
for f in UiTestCase._meta.get_fields():
    if getattr(f, 'editable', False) and hasattr(f, 'blank') and not f.blank and not f.null and not f.has_default() and not f.primary_key:
        required.append(f.name)
print('model required fields:', required)
