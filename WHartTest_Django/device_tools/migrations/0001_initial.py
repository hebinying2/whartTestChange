# 导入迁移 API。
from django.db import migrations, models


def create_permission_and_grant_staff(apps, schema_editor):
    """
    创建设备指令查询权限，并授予已有的管理员用户。

    说明：Django 的 post_migrate 会自动创建模型权限，但 A）执行顺序在迁移之后，
    B）不会补授给已存在的 staff 用户。这里显式 get_or_create 并授权，保证
    已有管理员升级后立即可用。
    """
    # 使用历史模型，避免依赖当前模型定义。
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    User = apps.get_model("auth", "User")

    # 条件：内容类型尚未建立；动作：创建；结果：权限能挂到 device_tools 应用下。
    content_type, _ = ContentType.objects.get_or_create(
        app_label="device_tools",
        model="devicecommand",
    )

    # 条件：权限不存在；动作：创建；结果：与模型 Meta.permissions 保持一致，避免重复。
    permission, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename="view_device_command",
        defaults={"name": "Can view device command"},
    )

    # 条件：存在管理员；动作：补授权限；结果：老账号无需手工授权即可看到菜单。
    for user in User.objects.filter(is_staff=True, is_active=True):
        user.user_permissions.add(permission)


def revoke_permission(apps, schema_editor):
    """回滚：删除权限项（用户关联由 Django 级联清理）。"""
    Permission = apps.get_model("auth", "Permission")
    Permission.objects.filter(
        content_type__app_label="device_tools",
        codename="view_device_command",
    ).delete()


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        # 仅登记模型状态，不建表（managed=False）。
        migrations.CreateModel(
            name="DeviceCommand",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
            ],
            options={
                "verbose_name": "设备指令",
                "verbose_name_plural": "设备指令",
                "managed": False,
                "default_permissions": (),
                "permissions": [("view_device_command", "Can view device command")],
            },
        ),
        migrations.RunPython(create_permission_and_grant_staff, revoke_permission),
    ]
