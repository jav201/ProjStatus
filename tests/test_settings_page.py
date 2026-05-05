from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def _strip_windows_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA"):
        monkeypatch.delenv(env_name, raising=False)


def _client_with_peers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    user: str = "bob",
    writable_peer: bool,
    include_missing_peer: bool,
) -> TestClient:
    """Build a TestClient whose Settings.load resolves a writable + missing peer mix."""
    _strip_windows_env(monkeypatch)
    own = tmp_path / "own"
    own.mkdir(parents=True, exist_ok=True)
    peer_dir = tmp_path / "alice"
    peer_dir.mkdir(parents=True, exist_ok=True)
    missing_dir = tmp_path / "ghost-not-existing"

    cfg = tmp_path / "config.toml"
    peer_entries: list[str] = []
    if writable_peer:
        peer_entries.append(
            f'{{ label = "alice", path = "{peer_dir.as_posix()}", writable = true }}'
        )
    else:
        peer_entries.append(
            f'{{ label = "alice", path = "{peer_dir.as_posix()}" }}'
        )
    if include_missing_peer:
        peer_entries.append(
            f'{{ label = "ghost", path = "{missing_dir.as_posix()}" }}'
        )
    cfg.write_text(
        f'data_root = "{own.as_posix()}"\n'
        f'user = "{user}"\n'
        f'peer_roots = [{", ".join(peer_entries)}]\n'
    )
    monkeypatch.setattr("app.settings.CONFIG_PATH", cfg)
    monkeypatch.delenv("PROJSTATUS_DATA_ROOT", raising=False)
    monkeypatch.delenv("PROJSTATUS_USER", raising=False)
    monkeypatch.delenv("PROJSTATUS_PEER_ROOTS", raising=False)
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# TC-010 — HLR-010 behavioural: GET /settings returns 200 + body contains
# data_root, every peer label, and the user string.
# ---------------------------------------------------------------------------
def test_tc_010_get_settings_renders_all_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client_with_peers(
        tmp_path, monkeypatch, user="bob", writable_peer=True, include_missing_peer=False
    )
    response = client.get("/settings")
    assert response.status_code == 200
    text = response.text
    # data_root path appears (some path-segment match — the resolved path on disk).
    assert (tmp_path / "own").as_posix() in text or (tmp_path / "own").name in text
    assert "alice" in text  # peer label
    assert "bob" in text     # user


# ---------------------------------------------------------------------------
# TC-031 — LLR-010.1: literal substrings RW / RO / unreachable per peer state.
# ---------------------------------------------------------------------------
def test_tc_031_peer_rows_render_rw_ro_and_unreachable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Writable peer + missing peer in the same render.
    client = _client_with_peers(
        tmp_path, monkeypatch, user="bob", writable_peer=True, include_missing_peer=True
    )
    response = client.get("/settings")
    assert response.status_code == 200
    text = response.text
    assert "RW" in text          # writable peer
    assert "unreachable" in text  # missing-path peer
    # Note: with writable_peer=True, no read-only peer is configured in this scenario,
    # so RO is exercised below in a separate test to avoid coupling assertions.


def test_tc_031_read_only_peer_renders_ro(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client_with_peers(
        tmp_path, monkeypatch, user="bob", writable_peer=False, include_missing_peer=False
    )
    response = client.get("/settings")
    assert response.status_code == 200
    text = response.text
    assert "RO" in text


# ---------------------------------------------------------------------------
# TC-032 — LLR-010.2 (inspection): no <form>, <input>, <button type=submit>,
# or method=post markup in settings.html. Template extends base.html.
# ---------------------------------------------------------------------------
def test_tc_032_settings_template_is_non_mutating() -> None:
    template_path = Path(__file__).resolve().parents[1] / "app" / "templates" / "settings.html"
    text = template_path.read_text(encoding="utf-8")
    # Case-insensitive grep equivalents.
    assert "<form" not in text.lower()
    assert "<input" not in text.lower()
    # `<button type="submit">` or `type='submit'` (any whitespace variant).
    assert re.search(r"<button[^>]*type\s*=\s*[\"']submit[\"']", text, flags=re.IGNORECASE) is None
    # `method="post"` / `method='post'`.
    assert re.search(r"method\s*=\s*[\"']post[\"']", text, flags=re.IGNORECASE) is None
    # First non-comment line is `{% extends "base.html" %}`.
    first_meaningful_line = next(
        line for line in text.splitlines()
        if line.strip() and not line.strip().startswith("{#")
    )
    assert first_meaningful_line.strip() == '{% extends "base.html" %}'


# ---------------------------------------------------------------------------
# TC-011 — HLR-011 behavioural + TC-033 — LLR-011.1: POST/PUT/PATCH/DELETE
# against /settings each return 405.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_tc_011_and_tc_033_mutating_methods_return_405(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    client = _client_with_peers(
        tmp_path, monkeypatch, user="bob", writable_peer=False, include_missing_peer=False
    )
    response = client.request(method, "/settings")
    assert response.status_code == 405


# ---------------------------------------------------------------------------
# TC-033 — LLR-011.1 (inspection-style): no @app.post/put/patch/delete handler
# is registered for the /settings path. Verified by inspecting the FastAPI route
# table directly so a future bypass-by-convention isn't possible.
# ---------------------------------------------------------------------------
def test_tc_033_no_mutating_handler_registered(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    settings_routes = [r for r in app.routes if getattr(r, "path", "") == "/settings"]
    assert settings_routes, "expected at least one route on /settings"
    for route in settings_routes:
        methods = getattr(route, "methods", set()) or set()
        # FastAPI's default GET route also exposes HEAD; that's allowed by HLR-011.
        assert methods.issubset({"GET", "HEAD"}), (
            f"unexpected mutating method registered on /settings: {methods}"
        )


# ---------------------------------------------------------------------------
# Sidebar integration: /settings is reachable via the sidebar nav (LLR-010.1
# acceptance: "the page is reachable from the sidebar via build_sidebar_context").
# ---------------------------------------------------------------------------
def test_tc_010_sidebar_link_to_settings_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client_with_peers(
        tmp_path, monkeypatch, user="bob", writable_peer=False, include_missing_peer=False
    )
    home = client.get("/")
    assert home.status_code == 200
    # The sidebar renders a link whose href includes "/settings".
    assert 'href="/settings"' in home.text or "/settings" in home.text
