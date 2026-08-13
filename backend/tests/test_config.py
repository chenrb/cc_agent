# backend/tests/test_config.py
import os
import subprocess
import sys
from pathlib import Path

from backend.auth import config

# 仓库根（backend/tests/test_config.py → 上两级）
_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# resolve_cookie_secure
# --------------------------------------------------------------------------
def test_cookie_secure_auto(monkeypatch):
    monkeypatch.setattr(config, "_COOKIE_SECURE", None)
    assert config.resolve_cookie_secure("https") is True
    assert config.resolve_cookie_secure("http") is False


def test_cookie_secure_forced_true(monkeypatch):
    monkeypatch.setattr(config, "_COOKIE_SECURE", True)
    # 即便请求是 http，也强制 Secure
    assert config.resolve_cookie_secure("http") is True


def test_cookie_secure_forced_false(monkeypatch):
    monkeypatch.setattr(config, "_COOKIE_SECURE", False)
    # 即便请求是 https，也强制不 Secure
    assert config.resolve_cookie_secure("https") is False


# --------------------------------------------------------------------------
# JWT_SECRET 必填校验（子进程隔离：config 在 import 时即校验）
# --------------------------------------------------------------------------
def _import_config_in_subprocess(env: dict) -> subprocess.CompletedProcess:
    """在新进程中导入 config，返回结果。"""
    proc_env = dict(os.environ)
    proc_env.update(env)
    return subprocess.run(
        [sys.executable, "-c",
         "from backend.auth.config import JWT_SECRET; print(JWT_SECRET)"],
        capture_output=True, text=True, env=proc_env, cwd=str(_ROOT),
    )


def test_missing_jwt_secret_raises():
    # 无论环境，缺 JWT_SECRET 都拒绝启动
    result = _import_config_in_subprocess({"JWT_SECRET": ""})
    assert result.returncode != 0
    assert "JWT_SECRET" in result.stderr


def test_with_jwt_secret_ok():
    secret = "a-secret-" + "0123456789abcdef" * 2
    result = _import_config_in_subprocess({"JWT_SECRET": secret})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == secret
