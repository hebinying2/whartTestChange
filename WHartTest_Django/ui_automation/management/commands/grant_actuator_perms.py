"""授予执行器账号 API 权限。

执行器通过账号密码获取 JWT 调用 app-execute-data / execute-data 等接口，
DRF DjangoModelPermissions 要求账号具备 UI 自动化模型的 view/add 权限。
用法：
    python manage.py grant_actuator_perms --username actuator_bot
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError

from ui_automation import models as ui_models


class Command(BaseCommand):
    help = '授予执行器账号 UI 自动化模型权限（加入 actuator 组并置 is_staff）'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True, help='执行器账号用户名')

    def handle(self, *args, **options):
        username = options['username']
        U = get_user_model()
        try:
            user = U.objects.get(username=username)
        except U.DoesNotExist:
            raise CommandError(f'用户不存在: {username}')

        group, _ = Group.objects.get_or_create(name='actuator')
        perms = set()
        for obj in vars(ui_models).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, __import__('django').db.models.Model)
                and getattr(obj._meta, 'app_label', '') == 'ui_automation'
                and not obj._meta.abstract
                and not obj._meta.proxy
            ):
                ct, _ = ContentType.objects.get_or_create(
                    app_label='ui_automation', model=obj._meta.model_name)
                perms.update(Permission.objects.filter(
                    content_type=ct, codename__startswith='view_'))
                perms.update(Permission.objects.filter(
                    content_type=ct, codename__startswith='add_'))
        group.permissions.set(list(perms))
        user.groups.add(group)
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        self.stdout.write(self.style.SUCCESS(
            f'已授予 {username} {len(perms)} 项权限（组 actuator，is_staff=True）'))
