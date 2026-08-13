"""CC Agent 后端启动入口。

应用装配见 ``backend.app:create_application``；本模块仅暴露模块级 ``app``
供 uvicorn 引用，并提供 ``python -m backend.main`` 开发启动。

运行：
    uv run python -m backend.main
    # 等价：uv run uvicorn backend.main:app --port 8000
"""

import sys

import uvicorn

from backend.app import app  # noqa: F401  # re-export for uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        # Windows 的 SelectorEventLoop 不支持 asyncio.create_subprocess_exec，
        # 而 uvicorn 的 reload 模式在 win32 下会强制使用 SelectorEventLoop
        # （ProactorEventLoop + multiprocessing spawn 历史上有死锁问题）。
        # agentscope 的 workspace（exec_shell）依赖子进程，故 Windows 下关闭
        # reload；Linux/macOS 的 SelectorEventLoop 支持子进程，保留热重载。
        reload=sys.platform != "win32",
    )
