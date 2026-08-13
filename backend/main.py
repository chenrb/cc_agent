"""CC Agent 后端启动入口。

应用装配见 ``backend.app:create_application``；本模块仅暴露模块级 ``app``
供 uvicorn 引用，并提供 ``python -m backend.main`` 开发启动。

运行：
    uv run python -m backend.main
    # 等价：uv run uvicorn backend.main:app --reload --port 8000
"""

import uvicorn

from backend.app import app  # noqa: F401  # re-export for uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
