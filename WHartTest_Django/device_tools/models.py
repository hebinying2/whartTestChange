# 导入 Django 模型基类。
from django.db import models


class DeviceCommand(models.Model):
    """
    设备指令查询权限锚点。

    该工具不落库任何请求记录（api-key 属于机密，请求体仅在内存中转发），
    因此这里不建表（managed=False），仅用于承载 `view_device_command`
    权限项，供权限树与前端菜单权限控制使用。
    """

    class Meta:
        # 不创建数据库表。
        managed = False
        # 关闭默认 CRUD 权限，仅保留查询权限。
        default_permissions = ()
        # 权限项：菜单与接口共用。
        permissions = [
            ("view_device_command", "Can view device command"),
        ]
        verbose_name = "设备指令"
        verbose_name_plural = "设备指令"
