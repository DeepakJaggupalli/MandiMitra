"""Shared paths, catalog access and the agent run log used by every pipeline step."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
CATALOG_PATH = DATA / "catalog.json"


def load_catalog() -> dict:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        return json.load(f)


def norm(text: str) -> str:
    """Lower-case, strip accents/punctuation and squeeze spaces (keeps Telugu letters)."""
    text = unicodedata.normalize("NFC", str(text)).strip().lower()
    text = re.sub(r"[\s_\-./,]+", " ", text)
    return text.strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class RunLog:
    """Every agent action is logged (design doc: guardrails)."""

    def __init__(self) -> None:
        self.entries: list[dict] = []

    def add(self, agent: str, action: str, detail: str, level: str = "info") -> None:
        entry = {"ts": now_iso(), "agent": agent, "action": action, "detail": detail, "level": level}
        self.entries.append(entry)
        print(f"[{entry['ts']}] {agent}.{action}: {detail}", flush=True)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
