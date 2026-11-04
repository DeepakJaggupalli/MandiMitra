"""Runtime configuration (all from environment variables)."""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("MANDIMITRA_DATA_DIR", ROOT / "data"))
PROCESSED_DIR = DATA_DIR / "processed"
IS_VERCEL = bool(os.environ.get("VERCEL"))

# Postgres when configured (Neon / Vercel Postgres set one of these), else SQLite.
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or ""
SQLITE_PATH = os.environ.get("SQLITE_PATH") or ("/tmp/mandimitra.db" if IS_VERCEL else str(ROOT / "data" / "local.db"))

JWT_SECRET = os.environ.get("JWT_SECRET") or secrets.token_hex(32)
TOKEN_HOURS = 12

_DEFAULT_STAFF = [
    {"username": "admin", "password": "admin@123", "role": "admin", "name": "Platform admin"},
    {"username": "officer", "password": "officer@123", "role": "officer", "name": "Extension officer (RSK)"},
    {"username": "fpo", "password": "fpo@123", "role": "fpo", "name": "FPO manager"},
]
try:
    STAFF_USERS = json.loads(os.environ["STAFF_USERS"]) if os.environ.get("STAFF_USERS") else _DEFAULT_STAFF
except json.JSONDecodeError:
    STAFF_USERS = _DEFAULT_STAFF

# Optional language model (any OpenAI-compatible chat endpoint: Sarvam, Groq, OpenRouter, Azure, ...).
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_ENABLED = bool(LLM_BASE_URL and LLM_API_KEY and LLM_MODEL)
