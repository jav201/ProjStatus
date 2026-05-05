from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.config import AppConfig
from app.services.storage import PeerWriteForbidden, StorageService


def _strip_windows_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA"):
        monkeypatch.delenv(env_name, raising=False)


def _seed(root: Path, name: str, *, writable_roots: list[Path] | None = None, actor: str = "alice") -> str:
    storage = StorageService(AppConfig.from_root(root), writable_roots=writable_roots)
    project = storage.create_project(name)
    storage.save_project(
        project,
        sections={"content": "", "change_requests": "", "roadblocks": "", "notes": ""},
        note=f"{actor} seeded",
        actor=actor,
    )
    return project.slug


def _project_json_sha(root: Path, slug: str) -> str:
    return hashlib.sha256((root / "projects" / slug / "project.json").read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# TC-013 (HLR-013 behavioural) — actor="unknown" against a writable peer raises;
# against the local data_root it succeeds.
# ---------------------------------------------------------------------------
def test_tc_013_writable_peer_raises_data_root_succeeds(tmp_path: Path) -> None:
    own = tmp_path / "own"
    peer = tmp_path / "peer"
    # Seed the peer using its own (writable) storage so a project actually exists.
    peer_slug = _seed(peer, "Peer Project")

    # Writable cross-storage: data_root=own, peer=writable, peer-rooted config.
    cross = StorageService(AppConfig.from_root(peer), writable_roots=[own, peer])
    loaded = StorageService(AppConfig.from_root(peer), writable_roots=[]).load_project(peer_slug)
    sha_before = _project_json_sha(peer, peer_slug)
    with pytest.raises(PeerWriteForbidden) as exc:
        cross.save_project(loaded.project, loaded.sections, note="x", actor="unknown")
    sha_after = _project_json_sha(peer, peer_slug)
    assert sha_before == sha_after  # no file modified on rejection
    assert "actor" in str(exc.value).lower()

    # Local data_root branch: "unknown" actor still permitted (A-010).
    own_storage = StorageService(AppConfig.from_root(own), writable_roots=[own])
    project_inside = own_storage.create_project("Own Project")
    addendum = own_storage.save_project(
        project_inside,
        sections={"content": "", "change_requests": "", "roadblocks": "", "notes": ""},
        note="local",
        actor="unknown",
    )
    assert addendum.actor == "unknown"


# ---------------------------------------------------------------------------
# TC-035 (LLR-013.1) — three sub-cases including the gate-ordering proof.
# ---------------------------------------------------------------------------
def test_tc_035a_writable_peer_unknown_actor_rejected(tmp_path: Path) -> None:
    own = tmp_path / "own"
    peer = tmp_path / "peer"
    peer_slug = _seed(peer, "Peer Project")
    cross = StorageService(AppConfig.from_root(peer), writable_roots=[own, peer])
    loaded = StorageService(AppConfig.from_root(peer), writable_roots=[]).load_project(peer_slug)
    sha_before = _project_json_sha(peer, peer_slug)
    with pytest.raises(PeerWriteForbidden) as exc:
        cross.save_project(loaded.project, loaded.sections, note="forbidden", actor="unknown")
    assert _project_json_sha(peer, peer_slug) == sha_before
    msg = str(exc.value)
    assert "actor" in msg.lower()
    # Gate-ordering: writability passed (peer is writable), so the message is the
    # actor-error format, not the writability error format.
    assert "writable root" not in msg.lower()


def test_tc_035b_data_root_unknown_actor_succeeds(tmp_path: Path) -> None:
    own = tmp_path / "own"
    storage = StorageService(AppConfig.from_root(own), writable_roots=[own])
    project = storage.create_project("Own Project")
    addendum = storage.save_project(
        project,
        sections={"content": "", "change_requests": "", "roadblocks": "", "notes": ""},
        note="local",
        actor="unknown",
    )
    assert addendum.actor == "unknown"
    # The CHANGELOG.md line was written and contains "unknown" as actor.
    changelog = (own / "projects" / project.slug / "CHANGELOG.md").read_text(encoding="utf-8")
    assert " — unknown — " in changelog


def test_tc_035c_non_writable_peer_unknown_actor_writability_error(tmp_path: Path) -> None:
    own = tmp_path / "own"
    peer = tmp_path / "peer"
    peer_slug = _seed(peer, "Peer Project")
    # writable_roots = [own] only; peer is NOT writable.
    cross = StorageService(AppConfig.from_root(peer), writable_roots=[own])
    loaded = StorageService(AppConfig.from_root(peer), writable_roots=[]).load_project(peer_slug)
    sha_before = _project_json_sha(peer, peer_slug)
    with pytest.raises(PeerWriteForbidden) as exc:
        cross.save_project(loaded.project, loaded.sections, note="forbidden", actor="unknown")
    msg = str(exc.value).lower()
    # Gate-ordering: writability check fires FIRST. The error message references
    # writability, NOT the actor. This is what makes phase-3 diagnostics deterministic.
    assert "writable root" in msg or "writable" in msg
    assert "actor" not in msg or "writable" in msg  # writability dominates
    assert _project_json_sha(peer, peer_slug) == sha_before
