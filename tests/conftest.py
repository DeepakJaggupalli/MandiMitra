import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SQLITE_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("POSTGRES_URL", None)
os.environ.setdefault("JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef")
for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
    os.environ.pop(k, None)
