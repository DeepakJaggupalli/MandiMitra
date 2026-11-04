"""Vercel entry point: every /api/* request is rewritten here and served by FastAPI."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.main import app  # noqa: E402,F401
