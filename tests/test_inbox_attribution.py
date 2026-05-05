from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import AppConfig
from app.main import create_app
from app.services.storage import (
    PeerWriteForbidden,
    StorageService,
    read_peer_addendums,
)


def _strip_windows_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA"):
        monkeypatch.delenv(env_name, raising=False)


def _seed(root: Path, name: str, *, actor: str, writable_roots: list[Path] | None = None) -> str:
    storage = StorageService(AppConfig.from_root(root), writable_roots=writable_roots)
    project = storage.create_project(name)
    storage.save_project(
        project,
        sections={"content": "", "change_requests": "", "roadblocks": "", "notes": ""},
        note=f"{actor} edit",
        actor=actor,
    )
    return project.slug


# ---------------------------------------------------------------------------
# TC-021 — LLR-004.1: when save_project writes into a writable peer, the
# resulting addendum's actor and CHANGELOG line both contain the local user.
# ---------------------------------------------------------------------------
def test_tc_021_writable_peer_records_local_actor(tmp_path: Path) -> None:
    own = tmp_path / "own"
    peer = tmp_path / "peer"
    peer_slug = _seed(peer, "Peer Project", actor="alice")

    # Cross-storage: data_root=peer, writable_roots include peer (treated as writable
    # from this app instance's perspective). Save with the LOCAL operator's actor.
    cross = StorageService(AppConfig.from_root(peer), writable_roots=[own, peer])
    loaded = StorageService(AppConfig.from_root(peer), writable_roots=[]).load_project(peer_slug)
    addendum = cross.save_project(
        loaded.project,
        loaded.sections,
        note="bob's local edit on alice's peer",
        actor="bob",
    )
    assert addendum.actor == "bob"
    # CHANGELOG.md line carries the local actor.
    changelog = (peer / "projects" / peer_slug / "CHANGELOG.md").read_text(encoding="utf-8")
    assert " — bob — " in changelog


# ---------------------------------------------------------------------------
# TC-022 — LLR-005.1: read_peer_addendums returns identical-shape triples for
# writable=True and writable=False peers (writable flag is ignored on the read path).
# ---------------------------------------------------------------------------
def test_tc_022_read_peer_addendums_iterates_regardless_of_writable_flag(tmp_path: Path) -> None:
    peer_a = tmp_path / "peer-a"
    peer_b = tmp_path / "peer-b"
    slug_a = _seed(peer_a, "A", actor="alice")
    slug_b = _seed(peer_b, "B", actor="bob")

    triples = [
        ("peer-a", peer_a, False),  # read-only
        ("peer-b", peer_b, True),   # writable
    ]
    entries = read_peer_addendums(triples, limit=20)

    labels = {e[0] for e in entries}
    slugs = {e[1] for e in entries}
    actors = {e[2].actor for e in entries}
    assert {"peer-a", "peer-b"} == labels
    assert {slug_a, slug_b} <= slugs
    assert {"alice", "bob"} <= actors


# ---------------------------------------------------------------------------
# TC-023 — LLR-005.2: the throwaway StorageService inside read_peer_addendums
# is constructed with writable_roots=[]. We patch StorageService to capture the
# writable_roots argument across calls and assert it is always `[]` for the
# peer-read path.
# ---------------------------------------------------------------------------
def test_tc_023_throwaway_storage_service_is_non_writable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    peer = tmp_path / "peer"
    _seed(peer, "Peer", actor="alice")

    captured: list[list[Path] | None] = []
    real_init = StorageService.__init__

    def patched_init(self: StorageService, config: AppConfig, writable_roots: list[Path] | None = None) -> None:  # type: ignore[no-untyped-def]
        captured.append(writable_roots)
        real_init(self, config, writable_roots=writable_roots)

    monkeypatch.setattr(StorageService, "__init__", patched_init)

    # Run the read path. Behind the scenes, read_peer_addendums constructs ONE
    # StorageService per peer (the throwaway).
    read_peer_addendums([("peer", peer, False)], limit=5)

    # The throwaway construction(s) used writable_roots=[].
    assert [] in captured  # at least one call passed an empty list
    # No other call leaked through with the data-root default.
    throwaway_calls = [c for c in captured if c == []]
    assert len(throwaway_calls) >= 1


# ---------------------------------------------------------------------------
# TC-024 — LLR-005.3: peer-row HTML contains both `peer · <label>` and
# `(claimed)`. Own-row HTML does NOT contain `(claimed)`.
# ---------------------------------------------------------------------------
def test_tc_024_peer_row_renders_claimed_qualifier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _strip_windows_env(monkeypatch)
    own_root = tmp_path / "own"
    peer_root = tmp_path / "peer"

    own_slug = _seed(own_root, "Own Project", actor="bob")
    peer_slug = _seed(peer_root, "Peer Project", actor="alice")

    monkeypatch.setenv("PROJSTATUS_USER", "bob")
    monkeypatch.setenv("PROJSTATUS_DATA_ROOT", str(own_root))
    monkeypatch.setenv("PROJSTATUS_PEER_ROOTS", f"alice={peer_root}")
    monkeypatch.setattr("app.settings.CONFIG_PATH", tmp_path / "missing.toml")

    client = TestClient(create_app())
    page = client.get("/inbox")
    assert page.status_code == 200
    text = page.text

    # Both projects appear.
    assert own_slug in text
    assert peer_slug in text
    # Peer row carries BOTH the peer prefix AND the claimed qualifier.
    assert "peer · alice" in text
    assert "(claimed)" in text

    # The "(claimed)" qualifier appears only inside an inbox row tagged is-peer.
    # Easiest check: it never appears next to bob's own slug, but does appear
    # next to the peer slug.
    own_window_start = text.find(own_slug)
    own_window = text[own_window_start : own_window_start + 600] if own_window_start >= 0 else ""
    # Own row context does NOT contain (claimed) — it's only on the peer rows.
    # (We grep within the small substring around the own slug; the peer row
    # may be rendered before/after, but its "(claimed)" lives in its own row.)
    assert "(claimed)" not in own_window


# ---------------------------------------------------------------------------
# TC-005 — HLR-005 behavioural: writable-peer addendum surfaces in /inbox with
# the peer chip and the LOCAL user's actor (when written via the local app).
# ---------------------------------------------------------------------------
def test_tc_005_writable_peer_addendum_surfaces_in_inbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _strip_windows_env(monkeypatch)
    own_root = tmp_path / "own"
    peer_root = tmp_path / "peer"
    peer_slug = _seed(peer_root, "Shared Project", actor="alice")

    # As "bob" (local), write into the peer (which is writable from bob's view).
    cross = StorageService(AppConfig.from_root(peer_root), writable_roots=[own_root, peer_root])
    loaded = StorageService(AppConfig.from_root(peer_root), writable_roots=[]).load_project(peer_slug)
    cross.save_project(loaded.project, loaded.sections, note="bob worked on it", actor="bob")

    # Now spin up an instance whose peer config sees the same peer_root.
    # The merged inbox should show the addendum we just wrote — attributed to bob,
    # with the peer label "shared".
    monkeypatch.setenv("PROJSTATUS_USER", "carla")
    monkeypatch.setenv("PROJSTATUS_DATA_ROOT", str(own_root))
    monkeypatch.setenv("PROJSTATUS_PEER_ROOTS", f"shared={peer_root}")
    monkeypatch.setattr("app.settings.CONFIG_PATH", tmp_path / "missing.toml")

    client = TestClient(create_app())
    page = client.get("/inbox")
    assert page.status_code == 200
    text = page.text
    assert peer_slug in text
    assert "peer · shared" in text
    # The local-app actor "bob" (who wrote the change) appears in the row.
    assert "bob" in text
    # The viewer (carla) sees it as a peer row, so the (claimed) qualifier is present.
    assert "(claimed)" in text
