from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

from app.config import AppConfig
from app.services.storage import PeerWriteForbidden, StorageService
from app.settings import Settings, _demote_dangerous_writable_peers


def _strip_windows_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove Windows env vars so pytest's tmp_path under %LOCALAPPDATA% does not
    incidentally trip LLR-012.1's demotion predicate during tests not exercising it.
    """
    for env_name in ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA"):
        monkeypatch.delenv(env_name, raising=False)


def _seed_project(root: Path, name: str, *, writable_roots: list[Path] | None = None) -> str:
    storage = StorageService(AppConfig.from_root(root), writable_roots=writable_roots)
    project = storage.create_project(name)
    return project.slug


def _project_json_sha(root: Path, slug: str) -> str:
    payload = (root / "projects" / slug / "project.json").read_bytes()
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# TC-003 — HLR-003 behavioural: save_project against a non-writable peer raises
# PermissionError and leaves files byte-identical.
# ---------------------------------------------------------------------------
def test_tc_003_non_writable_peer_save_rejected(tmp_path: Path) -> None:
    own_root = tmp_path / "own"
    peer_root = tmp_path / "peer"
    # Seed a project on the peer with the peer's own (writable) StorageService so it exists.
    peer_slug = _seed_project(peer_root, "Peer Project")

    # Build a StorageService rooted at own_root but with writable_roots = [own_root]
    # only (peer is NOT writable). Then load the peer's project via the peer-aware
    # storage and try save_project — must raise.
    own_storage = StorageService(AppConfig.from_root(own_root), writable_roots=[own_root])
    # Load directly from peer to obtain a Project model.
    peer_storage_readonly = StorageService(AppConfig.from_root(peer_root), writable_roots=[])
    loaded = peer_storage_readonly.load_project(peer_slug)

    # Repoint the *own* storage at the peer's project_dir by hand-crafting the
    # _project_dir path (using a config rooted at the peer) — easiest way: instantiate
    # an own-storage with config rooted at peer_root but writable_roots restricted.
    cross_storage = StorageService(AppConfig.from_root(peer_root), writable_roots=[own_root])
    sha_before = _project_json_sha(peer_root, peer_slug)
    with pytest.raises(PeerWriteForbidden) as exc:
        cross_storage.save_project(loaded.project, loaded.sections, note="forbidden", actor="alice")
    sha_after = _project_json_sha(peer_root, peer_slug)
    assert sha_before == sha_after  # byte-identical
    assert "writable root" in str(exc.value).lower() or "writable" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# TC-018 — LLR-003.1: write rejection raises PermissionError, no _write_text called.
# ---------------------------------------------------------------------------
def test_tc_018_save_outside_writable_roots_raises(tmp_path: Path) -> None:
    inside = tmp_path / "inside"
    outside = tmp_path / "outside"
    storage = StorageService(AppConfig.from_root(inside), writable_roots=[inside])

    # Seed an own project (under inside) — should succeed.
    slug_inside = _seed_project(inside, "Inside Project", writable_roots=[inside])
    sha_inside = _project_json_sha(inside, slug_inside)

    # Construct a cross-storage where projects_dir lives under `outside` but
    # writable_roots = [inside]. save_project on a fresh project must fail.
    cross_config = AppConfig.from_root(outside)
    cross_storage = StorageService(cross_config, writable_roots=[inside])
    with pytest.raises(PermissionError):
        # Try to create a project — create_project internally calls save_project.
        cross_storage.create_project("Outside Project")

    # The inside project remains byte-identical (negative-control assertion).
    assert _project_json_sha(inside, slug_inside) == sha_inside


# ---------------------------------------------------------------------------
# TC-019 — LLR-003.2: StorageService accepts writable_roots kwarg; default is
# [data_root] (= projects_dir.parent) when omitted.
# ---------------------------------------------------------------------------
def test_tc_019_storage_service_accepts_writable_roots_kwarg(tmp_path: Path) -> None:
    storage = StorageService(AppConfig.from_root(tmp_path), writable_roots=[tmp_path])
    assert storage._writable_roots == [tmp_path.resolve(strict=False)]

    # Default — when kwarg omitted, it falls back to [projects_dir.parent].
    storage_default = StorageService(AppConfig.from_root(tmp_path / "default"))
    expected = (tmp_path / "default").resolve(strict=False)
    assert storage_default._writable_roots == [expected]


# ---------------------------------------------------------------------------
# TC-020 — LLR-003.3: path canonicalization. A symlinked escape inside a
# writable peer is rejected (skipped on Windows-without-symlink-privilege).
# Also covers the `..`-segment case which doesn't need symlink privilege.
# ---------------------------------------------------------------------------
def test_tc_020_canonicalization_rejects_dotdot_escape(tmp_path: Path) -> None:
    inside = tmp_path / "inside"
    outside = tmp_path / "outside"
    inside.mkdir()
    outside.mkdir()
    storage = StorageService(AppConfig.from_root(inside), writable_roots=[inside])
    # `..`-segment escape: an explicitly crafted project_dir under inside that
    # resolves to outside via `..` should be rejected by _check_writable.
    crafted = inside / "subproj" / ".." / ".." / "outside" / "evil"
    with pytest.raises(PermissionError):
        storage._check_writable(crafted)


def test_tc_020_canonicalization_rejects_symlink_escape(tmp_path: Path) -> None:
    inside = tmp_path / "inside"
    outside = tmp_path / "outside"
    inside.mkdir()
    outside.mkdir()
    link = inside / "evil"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):  # Windows w/o Developer Mode: skip
        pytest.skip("symlink privilege unavailable on this platform")
    storage = StorageService(AppConfig.from_root(inside), writable_roots=[inside])
    with pytest.raises(PermissionError):
        storage._check_writable(link / "victim")


# ---------------------------------------------------------------------------
# TC-012 — HLR-012 behavioural: a `[[peer_roots]] path="/" writable=true` entry
# resolves to writable=False after Settings.load and emits one stderr warning.
# ---------------------------------------------------------------------------
def test_tc_012_root_writable_demoted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    _strip_windows_env(monkeypatch)
    monkeypatch.delenv("PROJSTATUS_PEER_ROOTS", raising=False)
    monkeypatch.delenv("PROJSTATUS_DATA_ROOT", raising=False)
    monkeypatch.delenv("PROJSTATUS_USER", raising=False)
    cfg = tmp_path / "config.toml"
    target = tmp_path / "self"
    # Pick a path that is filesystem root: on POSIX `/`, on Windows `C:\` (or
    # whichever drive `tmp_path` lives on, since `Path("/").resolve()` returns
    # the current drive's root on Windows).
    fs_root = Path(tmp_path.anchor or "/")
    cfg.write_text(
        f'data_root = "{target.as_posix()}"\n'
        f'peer_roots = [{{ label = "bad", path = "{fs_root.as_posix()}", writable = true }}]\n'
    )
    monkeypatch.setattr("app.settings.CONFIG_PATH", cfg)
    # Reset the warn-once tracker so this test sees the warning regardless of order.
    import app.settings as settings_mod
    settings_mod._DEMOTED_WARNED.clear()

    settings = Settings.load()
    assert len(settings.peer_roots) == 1
    label, _path, writable = settings.peer_roots[0]
    assert label == "bad"
    assert writable is False  # demoted

    captured = capsys.readouterr()
    assert "demoted to read-only" in captured.err
    assert "filesystem-root" in captured.err


# ---------------------------------------------------------------------------
# TC-034 — LLR-012.1: every dangerous-path branch demotes; warn-once-per-process.
# ---------------------------------------------------------------------------
def test_tc_034_demotion_branches_and_warn_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    # Strip Windows env vars so the "safe-peer" path under tmp_path (which on Windows
    # lives under %LOCALAPPDATA%\Temp) is NOT incidentally treated as windows-appdata.
    _strip_windows_env(monkeypatch)
    data_root = (tmp_path / "data").resolve(strict=False)
    home = Path.home().resolve(strict=False)
    fs_root = Path(tmp_path.anchor or "/")
    # Build triples covering 4 dangerous branches + 1 safe.
    safe_writable = (tmp_path / "safe-peer").resolve(strict=False)
    triples = [
        ("a-fs-root", fs_root, True),
        ("b-home", home, True),
        ("c-data-root-ancestor", data_root.parent, True),
        ("d-ssh-cred", home / ".ssh", True),
        ("e-safe", safe_writable, True),
    ]
    # Reset the warn-once tracker.
    import app.settings as settings_mod
    settings_mod._DEMOTED_WARNED.clear()

    out = _demote_dangerous_writable_peers(list(triples), data_root)
    assert len(out) == 5
    by_label = {t[0]: t for t in out}
    assert by_label["a-fs-root"][2] is False
    assert by_label["b-home"][2] is False
    assert by_label["c-data-root-ancestor"][2] is False
    assert by_label["d-ssh-cred"][2] is False
    # Safe peer remains writable.
    assert by_label["e-safe"][2] is True

    captured_first = capsys.readouterr()
    # 4 distinct dangerous entries → 4 warning lines.
    assert captured_first.err.count("demoted to read-only") == 4

    # Re-run with the same triples — warn-once means NO new warnings.
    out2 = _demote_dangerous_writable_peers(list(triples), data_root)
    captured_second = capsys.readouterr()
    assert captured_second.err == ""
    # State is the same.
    assert [t[2] for t in out2] == [t[2] for t in out]
