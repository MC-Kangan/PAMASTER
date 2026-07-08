import os

os.environ.setdefault("PA_ENVIRONMENT", "test")
os.environ.setdefault("PA_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("PA_LLM_PROVIDER", "mock")
os.environ.setdefault("PA_NOTION_ENABLED", "false")
