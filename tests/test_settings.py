from __future__ import annotations

from pathlib import Path

import pytest

from app.settings import Settings


def test_defaults_with_no_env_or_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROJSTATUS_DATA_ROOT", raising=False)
    monkeypatch.delenv("PROJSTATUS_PEER_ROOTS", raising=False)
    monkeypatch.delenv("PROJSTATUS_USER", raising=False)
    monkeypatch.setattr("app.settings.CONFIG_PATH", tmp_path / "missing.toml")

    settings = Settings.load(code_root=tmp_path)
    assert settings.data_root == tmp_path.resolve()
    assert settings.peer_roots == []
    assert settings.user  # whatever os.getlogin returns or "unknown"


def test_env_overrides_data_root_and_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "alice-data"
    monkeypatch.setenv("PROJSTATUS_DATA_ROOT", str(target))
    monkeypatch.setenv("PROJSTATUS_USER", "alice")
    monkeypatch.setattr("app.settings.CONFIG_PATH", tmp_path / "missing.toml")

    settings = Settings.load()
    assert settings.data_root == target.resolve()
    assert target.exists()  # auto-created
    assert settings.user == "alice"


def test_peer_roots_parsed_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bob = tmp_path / "bob"
    luis = tmp_path / "luis"
    monkeypatch.setenv("PROJSTATUS_DATA_ROOT", str(tmp_path / "self"))
    monkeypatch.setenv("PROJSTATUS_PEER_ROOTS", f"bob={bob},luis={luis}")
    monkeypatch.setattr("app.settings.CONFIG_PATH", tmp_path / "missing.toml")

    settings = Settings.load()
    labels = [label for label, _, _ in settings.peer_roots]
    assert labels == ["bob", "luis"]
    assert settings.peer_roots[0][1] == bob.expanduser()
    # Env-var path has no writable syntax — every entry resolves to writable=False.
    assert all(triple[2] is False for triple in settings.peer_roots)


def test_malformed_peer_roots_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROJSTATUS_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("PROJSTATUS_PEER_ROOTS", "no-equals-sign,, =empty-label,real=/tmp/x")
    monkeypatch.setattr("app.settings.CONFIG_PATH", tmp_path / "missing.toml")

    settings = Settings.load()
    labels = [label for label, _, _ in settings.peer_roots]
    assert labels == ["real"]


def test_toml_file_used_when_env_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROJSTATUS_DATA_ROOT", raising=False)
    monkeypatch.delenv("PROJSTATUS_PEER_ROOTS", raising=False)
    monkeypatch.delenv("PROJSTATUS_USER", raising=False)

    cfg = tmp_path / "config.toml"
    target = tmp_path / "from-toml"
    cfg.write_text(
        f'data_root = "{target.as_posix()}"\nuser = "carla"\n'
        f'peer_roots = [{{ label = "ana", path = "{(tmp_path / "ana").as_posix()}" }}]\n'
    )
    monkeypatch.setattr("app.settings.CONFIG_PATH", cfg)

    settings = Settings.load()
    assert settings.data_root == target.resolve()
    assert settings.user == "carla"
    assert settings.peer_roots[0][0] == "ana"
    # No `writable` key in the TOML entry → defaults to False per LLR-002.1.
    assert settings.peer_roots[0][2] is False
