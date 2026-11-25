# 导入 path 以声明本应用路由。
from django.urls import path

# 导入视图。
from .views import DeviceCodeSourceView, DeviceCommandCatalogView, DeviceCommandExecuteView

# 路由列表（由 wharttest_django.urls 以 /api/device-tools/ 前缀挂载）。
urlpatterns = [
    path("catalog/", DeviceCommandCatalogView.as_view(), name="device-command-catalog"),
    path("device-codes/", DeviceCodeSourceView.as_view(), name="device-code-source"),
    path("execute/", DeviceCommandExecuteView.as_view(), name="device-command-execute"),
]
