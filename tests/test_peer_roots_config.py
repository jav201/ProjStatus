from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings, _resolve_peer_roots


# TC-001 — HLR-001 behavioural: TOML peer entry with `writable=true` is preserved.
def test_tc_001_writable_true_preserved_from_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROJSTATUS_PEER_ROOTS", raising=False)
    monkeypatch.delenv("PROJSTATUS_DATA_ROOT", raising=False)
    monkeypatch.delenv("PROJSTATUS_USER", raising=False)
    # Strip Windows env vars so pytest's tmp_path (which on Windows lives under
    # %LOCALAPPDATA%\Temp) is NOT incidentally seen as a dangerous writable subtree
    # by LLR-012.1's demotion predicate.
    for env_name in ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA"):
        monkeypatch.delenv(env_name, raising=False)
    cfg = tmp_path / "config.toml"
    target = tmp_path / "self"
    peer = tmp_path / "alice"
    cfg.write_text(
        f'data_root = "{target.as_posix()}"\n'
        f'peer_roots = [{{ label = "alice", path = "{peer.as_posix()}", writable = true }}]\n'
    )
    monkeypatch.setattr("app.settings.CONFIG_PATH", cfg)

    settings = Settings.load()
    assert len(settings.peer_roots) == 1
    label, path, writable = settings.peer_roots[0]
    assert label == "alice"
    assert path == peer
    assert writable is True


# TC-002 — HLR-002 behavioural: TOML peer entry omitting `writable` defaults to False.
def test_tc_002_writable_defaults_false_when_omitted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROJSTATUS_PEER_ROOTS", raising=False)
    monkeypatch.delenv("PROJSTATUS_DATA_ROOT", raising=False)
    monkeypatch.delenv("PROJSTATUS_USER", raising=False)
    cfg = tmp_path / "config.toml"
    target = tmp_path / "self"
    peer = tmp_path / "bob"
    cfg.write_text(
        f'data_root = "{target.as_posix()}"\n'
        f'peer_roots = [{{ label = "bob", path = "{peer.as_posix()}" }}]\n'
    )
    monkeypatch.setattr("app.settings.CONFIG_PATH", cfg)

    settings = Settings.load()
    assert settings.peer_roots[0][2] is False


# TC-015 — LLR-001.1: `_resolve_peer_roots` returns `(label, path, writable)` triples
# for both TOML and env-var sources; env-var path always sets writable=False.
def test_tc_015_resolve_peer_roots_triple_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    # TOML branch — list of dicts
    monkeypatch.delenv("PROJSTATUS_PEER_ROOTS", raising=False)
    toml_input = [
        {"label": "x", "path": "/tmp/x", "writable": True},
        {"label": "y", "path": "/tmp/y", "writable": False},
        {"label": "z", "path": "/tmp/z"},  # writable omitted
    ]
    triples = _resolve_peer_roots(toml_input)
    assert len(triples) == 3
    assert triples[0] == ("x", Path("/tmp/x"), True)
    assert triples[1] == ("y", Path("/tmp/y"), False)
    assert triples[2] == ("z", Path("/tmp/z"), False)

    # Env-var branch — comma-joined `label=path` pairs always force writable=False.
    monkeypatch.setenv("PROJSTATUS_PEER_ROOTS", "alpha=/tmp/a,beta=/tmp/b")
    env_triples = _resolve_peer_roots(None)
    assert len(env_triples) == 2
    assert env_triples[0] == ("alpha", Path("/tmp/a"), False)
    assert env_triples[1] == ("beta", Path("/tmp/b"), False)


# TC-016 — LLR-001.2: create_app stores triples on app.state.peer_roots; bool per peer.
def test_tc_016_app_state_peer_roots_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # When create_app is given root_dir, peer_roots is forced to [].
    app = create_app(tmp_path)
    assert app.state.peer_roots == []

    # When create_app is called without root_dir, Settings.load() runs and the peer
    # triples flow through. Set up a real peer fixture and verify the bool type.
    peer = tmp_path / "peerland"
    monkeypatch.setenv("PROJSTATUS_DATA_ROOT", str(tmp_path / "self"))
    monkeypatch.setenv("PROJSTATUS_PEER_ROOTS", f"peerland={peer}")
    monkeypatch.setattr("app.settings.CONFIG_PATH", tmp_path / "missing.toml")
    app2 = create_app()
    triples = app2.state.peer_roots
    assert len(triples) == 1
    label, path, writable = triples[0]
    assert label == "peerland"
    assert path == peer
    assert isinstance(writable, bool)
    assert writable is False  # env-var path is always non-writable


# TC-017 — LLR-002.1: missing `writable` key → False; non-bool value coerces to False.
@pytest.mark.parametrize(
    "raw_writable,expected",
    [
        (None, False),       # key omitted (we'll simulate this branch separately)
        (True, True),
        (False, False),
        ("yes", False),       # non-bool string
        (1, False),           # non-bool int (truthy in Python, but not `is True`)
        (0, False),
        ("true", False),      # string, not the bool literal
    ],
)
def test_tc_017_writable_coerces_to_false_when_not_bool(raw_writable: object, expected: bool) -> None:
    entry: dict[str, object] = {"label": "lab", "path": "/tmp/lab"}
    if raw_writable is not None:
        entry["writable"] = raw_writable
    triples = _resolve_peer_roots([entry])
    assert len(triples) == 1
    assert triples[0][2] is expected
