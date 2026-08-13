# backend/auth/spa.py
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def mount_spa(app: FastAPI) -> None:
    """若 frontend/dist 存在则托管（同源）；否则跳过（dev 由 vite 提供）。"""
    index = _DIST / "index.html"
    if not index.is_file():
        return
    # 静态资源
    assets = _DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="spa-assets")

    @app.get("/{full_path:path}")
    async def _spa(full_path: str):
        # API/已注册路由优先（FastAPI 路由匹配顺序：本路由放最后兜底）
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(index))
