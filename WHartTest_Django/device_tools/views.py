"""
设备指令查询接口。

浏览器 -> Django（本应用）-> 设备接入网关，api-key 只在本次请求中透传，
不落库、不写日志。服务地址由后端配置固定，前端只读展示，避免代理被
当作任意地址跳板（SSRF）。
"""

# 导入 json，用于请求体序列化与响应解析。
import json
import logging
import re
import ssl
import time

# 导入 httpx 作为上游代理客户端。
import httpx

# 导入 Django 配置读取入口。
from django.conf import settings
from django.db import connections

# 导入 DRF 视图与响应工具。
from rest_framework import status as drf_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

# 导入目录配置与权限类。
from .catalog import (
    DEVICE_ACTION_PATH_TEMPLATE,
    DEVICE_ACTION_PRODUCT_TYPE,
    build_catalog_payload,
    get_action,
    get_product,
)
from .permissions import HasDeviceCommandPermission

# 模块级日志记录器（只记录不含机密的元信息）。
logger = logging.getLogger(__name__)

# 设备编号白名单：字母、数字及 . _ : -，最长 64。
VID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
# 请求体大小上限（64KB）。
MAX_BODY_BYTES = 64 * 1024
# 响应体读取上限（1MB），超出只返回截断内容。
MAX_RESPONSE_BYTES = 1024 * 1024
# 上游请求超时（秒）。
UPSTREAM_TIMEOUT = 15.0
# api-key 长度上限，防止异常超大请求头。
MAX_API_KEY_LENGTH = 1024


class DeviceCommandCatalogView(APIView):
    """返回设备类型、查询指令与参数定义，供前端渲染表单。"""

    permission_classes = [IsAuthenticated, HasDeviceCommandPermission]

    def get(self, request):
        # 服务地址由后端白名单提供，前端只允许从该列表中选择。
        host = str(getattr(settings, "DEVICE_ACCESS_HOST", "") or "").rstrip("/")
        host_options = list(getattr(settings, "DEVICE_ACCESS_HOSTS", []) or [host])
        return Response(build_catalog_payload(host, host_options))


class DeviceCodeSourceView(APIView):
    """从可配置的测试环境数据库中获取设备编码候选列表。"""

    permission_classes = [IsAuthenticated, HasDeviceCommandPermission]

    # 表/字段名只允许字母数字下划线，避免直接拼 SQL 造成注入。
    DB_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def get(self, request):
        table = str(getattr(settings, "DEVICE_CODE_DB_TABLE", "") or "").strip()
        column = str(getattr(settings, "DEVICE_CODE_DB_COLUMN", "") or "").strip()
        alias = str(getattr(settings, "DEVICE_CODE_DB_ALIAS", "default") or "default").strip()

        # 未配置数据源时保持工具可用，前端仍允许手工输入设备编码。
        if not table or not column:
            return Response({"configured": False, "items": [], "error": ""})

        if alias not in connections.databases:
            return Response({"configured": False, "items": [], "error": "设备编码数据源别名不存在"})

        if (
            not self.DB_IDENTIFIER_PATTERN.fullmatch(table)
            or not self.DB_IDENTIFIER_PATTERN.fullmatch(column)
        ):
            return Response({"configured": False, "items": [], "error": "设备编码数据源配置非法"})

        limit = int(getattr(settings, "DEVICE_CODE_DB_LIMIT", 200) or 200)
        limit = max(1, min(limit, 1000))

        sql = f'SELECT "{column}" FROM "{table}" ORDER BY 1 LIMIT {limit}'
        try:
            with connections[alias].cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
        except Exception as exc:
            # 数据源查询失败时降级为可手工输入，避免阻塞主流程。
            logger.warning("设备编码数据源查询失败 table=%s column=%s error=%r", table, column, exc)
            return Response({"configured": True, "items": [], "error": "设备编码查询失败"})

        items = [str(row[0]).strip() for row in rows if row[0] is not None and str(row[0]).strip()]
        return Response({"configured": True, "items": items, "error": ""})


class DeviceCommandExecuteView(APIView):
    """代理执行设备查询指令，返回上游状态、耗时与响应内容。"""

    permission_classes = [IsAuthenticated, HasDeviceCommandPermission]

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}

        product_type = str(payload.get("productType") or "").strip()
        vid = str(payload.get("vid") or "").strip()
        host = str(payload.get("host") or "").strip().rstrip("/")
        # api-key 属于机密：仅保存在局部变量中，禁止写入日志或响应。
        api_key = str(payload.get("apiKey") or "").strip()
        body = payload.get("body")

        # 设备类型必须在目录内，避免任意路径拼接。
        if not get_product(product_type):
            return Response(
                {"detail": f"不支持的设备类型：{product_type or '(空)'}"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        # 设备编号直接进入 URL 路径，必须严格校验。
        if not VID_PATTERN.match(vid):
            return Response(
                {"detail": "设备编号不合法：仅允许字母、数字及 . _ : -，且不超过 64 位。"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        if not api_key:
            return Response(
                {"detail": "请填写 api-key。"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )
        if len(api_key) > MAX_API_KEY_LENGTH:
            return Response(
                {"detail": "api-key 长度超出限制。"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        # Body 必须是 JSON 对象，且 serviceId 必须在目录内。
        if not isinstance(body, dict) or not body:
            return Response(
                {"detail": "请求体必须是非空 JSON 对象。"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )
        service_id = body.get("serviceId")
        if not isinstance(service_id, int) or not get_action(product_type, service_id):
            return Response(
                {"detail": f"查询指令不存在：{service_id}"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        try:
            # 紧凑序列化，避免多余空白占用上游带宽。
            body_bytes = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError):
            return Response(
                {"detail": "请求体无法序列化为 JSON。"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )
        if len(body_bytes) > MAX_BODY_BYTES:
            return Response(
                {"detail": "请求体过大，上限 64KB。"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        # 服务地址必须在后端白名单内，避免代理被用作任意地址跳板。
        allowed_hosts = [
            str(item).strip().rstrip("/")
            for item in getattr(settings, "DEVICE_ACCESS_HOSTS", [])
            if str(item).strip()
        ]
        default_host = str(getattr(settings, "DEVICE_ACCESS_HOST", "") or "").rstrip("/")
        if not default_host:
            return Response(
                {"detail": "后端未配置 DEVICE_ACCESS_HOST。"},
                status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        if not host:
            host = default_host
        if host not in allowed_hosts:
            return Response(
                {"detail": "服务地址不在允许列表内。"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        url = host + DEVICE_ACTION_PATH_TEMPLATE.replace("{productType}", DEVICE_ACTION_PRODUCT_TYPE).replace("{vid}", vid)

        started = time.perf_counter()
        try:
            # follow_redirects=False：避免被上游重定向带到非预期地址。
            with httpx.Client(
                timeout=httpx.Timeout(UPSTREAM_TIMEOUT),
                follow_redirects=False,
                verify=ssl.create_default_context(),
            ) as client:
                upstream = client.post(
                    url,
                    content=body_bytes,
                    headers={"api-key": api_key, "content-type": "application/json"},
                )
        except httpx.RequestError as exc:
            # 仅记录异常类型，绝不记录 api-key 或请求头。
            logger.warning("设备网关请求失败 url=%s error=%r", url, exc)
            return Response(
                {"detail": f"设备网关请求失败：{exc.__class__.__name__}"},
                status=drf_status.HTTP_502_BAD_GATEWAY,
            )

        duration_ms = int((time.perf_counter() - started) * 1000)

        raw = upstream.content
        total_size = len(raw)
        truncated = total_size > MAX_RESPONSE_BYTES
        if truncated:
            raw = raw[:MAX_RESPONSE_BYTES]

        text = raw.decode(upstream.encoding or "utf-8", errors="replace")

        # 尽量解析 JSON 供前端格式化展示，解析失败则回退原始文本。
        parsed = None
        is_json = False
        if not truncated:
            try:
                parsed = json.loads(text)
                is_json = True
            except (ValueError, TypeError):
                parsed = None

        return Response(
            {
                "method": "POST",
                "url": url,
                "upstreamStatus": upstream.status_code,
                "durationMs": duration_ms,
                "sizeBytes": total_size,
                "truncated": truncated,
                "headers": {key.lower(): value for key, value in upstream.headers.items()},
                "body": parsed,
                "bodyText": text,
                "isJson": is_json,
            }
        )
