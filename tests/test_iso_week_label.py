from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.main import create_app
from app.utils import iso_week_label


def test_iso_week_label_w18() -> None:
    assert iso_week_label(date(2026, 4, 27)) == "W18"


@pytest.mark.parametrize(
    "given,expected",
    [
        (date(2024, 12, 29), "W52"),
        (date(2024, 12, 30), "W01"),
        (date(2025, 12, 29), "W01"),
        (date(2025, 12, 31), "W01"),
        (date(2026, 1, 1), "W01"),
        (date(2020, 12, 31), "W53"),
    ],
)
def test_iso_week_label_boundaries(given: date, expected: str) -> None:
    assert iso_week_label(given) == expected


def test_iso_week_label_none_returns_empty() -> None:
    assert iso_week_label(None) == ""


def test_iso_week_label_registered_as_jinja_global(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    env = app.state.templates.env
    assert "iso_week_label" in env.globals
    assert env.globals["iso_week_label"] is iso_week_label
    rendered = env.from_string("{{ iso_week_label(d) }}").render(d=date(2026, 4, 27))
    assert rendered == "W18"
