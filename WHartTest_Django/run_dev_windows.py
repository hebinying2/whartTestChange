"""Windows 本地开发 ASGI 启动入口。

uvicorn 在 Windows 上默认使用 ProactorEventLoop，而 psycopg 异步模式
（LangGraph AsyncPostgresSaver）需要 SelectorEventLoop。必须在 uvicorn
创建事件循环之前设置策略，因此单独提供该入口。
"""

import asyncio
import sys

if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "wharttest_django.asgi:application",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
