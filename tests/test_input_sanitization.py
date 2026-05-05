from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from app.config import AppConfig
from app.models import Addendum, ProjectSnapshot, Project
from app.services.storage import (
    StorageService,
    _append_changelog,
    _sanitize_changelog_field,
)
from app.settings import Settings, _sanitize_user_candidate


# ---------------------------------------------------------------------------
# TC-036 — LLR-013.2: sanitize Settings.user
# ---------------------------------------------------------------------------
def test_tc_036_env_with_newline_falls_through_to_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROJSTATUS_USER", "alice\nfake")
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'data_root = "{(tmp_path / "self").as_posix()}"\nuser = "bob"\n')
    monkeypatch.setattr("app.settings.CONFIG_PATH", cfg)
    monkeypatch.delenv("PROJSTATUS_DATA_ROOT", raising=False)

    settings = Settings.load()
    # Env source rejected; config source taken.
    assert settings.user == "bob"


def test_tc_036_long_input_is_capped_at_64(monkeypatch: pytest.MonkeyPatch) -> None:
    long = "a" * 200
    monkeypatch.setenv("PROJSTATUS_USER", long)
    result = _sanitize_user_candidate(long)
    assert result is not None
    assert len(result) == 64
    assert result == "a" * 64


def test_tc_036_null_byte_is_stripped() -> None:
    result = _sanitize_user_candidate("ali\x00ce")
    assert result == "alice"


def test_tc_036_unicode_rlo_is_stripped() -> None:
    # U+202E RIGHT-TO-LEFT OVERRIDE — defeats the (claimed) qualifier display.
    result = _sanitize_user_candidate("alice‮evil")
    assert result == "aliceevil"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("​alice​bob​", "alicebob"),  # ZWSPs stripped
        ("‌alice‍", "alice"),               # ZWNJ + ZWJ stripped
        ("﻿alice", "alice"),                      # BOM stripped
        (" alice ", "alice"),                # NBSP becomes empty after strip
        ("alice", "alice"),                      # NEL stripped
    ],
)
def test_tc_036_zero_width_and_special_whitespace_stripped(raw: str, expected: str) -> None:
    assert _sanitize_user_candidate(raw) == expected


def test_tc_036_sanitizer_never_returns_unknown_from_non_fall_through() -> None:
    # The sanitizer never SYNTHESIZES "unknown" — only the final fall-through in
    # _resolve_user does. Verify that a candidate that would be rejected returns None,
    # not the literal string "unknown".
    assert _sanitize_user_candidate(None) is None
    assert _sanitize_user_candidate("") is None
    assert _sanitize_user_candidate("   ") is None  # only whitespace
    assert _sanitize_user_candidate("\nhello") is None  # rejected for newline


# ---------------------------------------------------------------------------
# TC-037 — LLR-013.3: sanitize CHANGELOG headline / note
# ---------------------------------------------------------------------------
def test_tc_037_markdown_link_brackets_escaped() -> None:
    # x[a](js:1)y → x&#91;a&#93;(js:1)y — markdown-link syntax broken.
    result = _sanitize_changelog_field("x[a](js:1)y")
    assert result == "x&#91;a&#93;(js:1)y"


def test_tc_037_html_tags_escaped() -> None:
    # <script>alert(1)</script> → &lt;script&gt;alert(1)&lt;/script&gt;
    result = _sanitize_changelog_field("<script>alert(1)</script>")
    assert result == "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_tc_037_pre_escape_blocks_entity_bypass() -> None:
    # CR-001 closure: a user who types &#91; into the change_note must NOT have
    # the literal `[` reconstructed by a downstream HTML viewer. The pre-escape
    # converts & → &amp; first, so &#91; becomes &amp;#91; on disk.
    result = _sanitize_changelog_field("&#91;click&#93;(js:1)")
    assert result == "&amp;#91;click&amp;#93;(js:1)"
    # Critical: the result does NOT contain the bare "&#91;" sequence — that
    # would have been the unmitigated bypass.
    assert "&#91;" not in result.replace("&amp;#91;", "")


def test_tc_037_newlines_collapse_to_spaces() -> None:
    raw = "line1\nline2\rline3\r\nline4"
    result = _sanitize_changelog_field(raw)
    # \r and \n each become single spaces (in order).
    assert result == "line1 line2 line3  line4"
    assert "\n" not in result and "\r" not in result


def test_tc_037_pipe_escape_for_markdown_tables() -> None:
    result = _sanitize_changelog_field("col1 | col2 | col3")
    assert result == "col1 &#124; col2 &#124; col3"


def test_tc_037_post_escape_cap_at_200() -> None:
    # 250-char input with 50 '[' and 50 ']' characters.
    raw = ("[" * 50) + ("a" * 150) + ("]" * 50)
    assert len(raw) == 250
    result = _sanitize_changelog_field(raw)
    # Each '[' → '&#91;' (5 chars), each ']' → '&#93;' (5 chars). Pre-cap length is
    # 50*5 + 150 + 50*5 = 650. Cap takes first 200.
    assert len(result) == 200
    # The first chars are '&#91;' repeated.
    assert result.startswith("&#91;&#91;&#91;")


def test_tc_037_thousand_newlines_become_spaces_then_cap() -> None:
    raw = "x" + ("\n" * 1000)
    result = _sanitize_changelog_field(raw)
    # Newlines → spaces, no escapes apply, cap at 200.
    assert len(result) == 200
    # Leading "x" then 199 spaces.
    assert result[0] == "x"
    assert result[1:] == " " * 199


# ---------------------------------------------------------------------------
# Integration check — CHANGELOG.md on disk gets sanitized fields.
# ---------------------------------------------------------------------------
def test_tc_037_integration_changelog_on_disk_is_sanitized(tmp_path: Path) -> None:
    storage = StorageService(AppConfig.from_root(tmp_path), writable_roots=[tmp_path])
    project = storage.create_project("Integration Test")
    storage.save_project(
        project,
        sections={"content": "", "change_requests": "", "roadblocks": "", "notes": ""},
        note="<script>x</script>[a](javascript:alert)|piped",
        actor="alice",
    )
    changelog = (tmp_path / "projects" / project.slug / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "&lt;script&gt;" in changelog
    assert "&#91;a&#93;" in changelog
    assert "&#124;piped" in changelog
    # Original raw content does NOT appear unsanitized.
    assert "<script>" not in changelog
    assert "[a](javascript" not in changelog
