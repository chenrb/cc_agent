import os

os.environ.setdefault("AGENT_DB_NAME", "cc_agent_test.db")
# config 导入时强制要求 JWT_SECRET；测试固定一个，避免缺密钥导致 import 失败
os.environ.setdefault("JWT_SECRET", "cc-agent-test-secret-0123456789abcdef")
