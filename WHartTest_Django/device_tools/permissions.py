# 导入 DRF 权限基类。
from rest_framework import permissions

# 设备指令查询权限项：菜单显示与接口调用共用。
DEVICE_COMMAND_PERMISSION = "device_tools.view_device_command"


class HasDeviceCommandPermission(permissions.BasePermission):
    """仅允许具备设备指令查询权限的用户访问（超级用户默认放行）。"""

    message = "没有设备指令查询权限"

    def has_permission(self, request, view):
        # 匿名用户直接拒绝。
        user = request.user
        if not user or user.is_anonymous:
            return False
        # 超级用户拥有全部权限。
        if user.is_superuser:
            return True
        # 其余用户按权限项判断。
        return user.has_perm(DEVICE_COMMAND_PERMISSION)
