from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "project"


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def sha1_file(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def dumps_pretty(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str) + "\n"


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def format_date(value: date | None) -> str:
    return value.isoformat() if value else ""


def date_to_duration_days(start: date | None, due: date | None) -> int:
    if not start or not due:
        return 1
    delta = (due - start).days
    return max(delta + 1, 1)


def due_from_duration(start: date | None, duration_days: int) -> date | None:
    if not start:
        return None
    return start + timedelta(days=max(duration_days - 1, 0))
