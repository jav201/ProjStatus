"""Per-machine settings: data root, peer roots for the cross-folder inbox, and user identity.

Resolution order (first match wins): env var → ~/.config/projstatus/config.toml → default.
The config file is optional; missing or unreadable files fall back to defaults silently.
"""
from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


CONFIG_PATH = Path.home() / ".config" / "projstatus" / "config.toml"

# LLR-012.1: warn-once-per-process tracker for demoted writable peer roots.
# Mirrors the _PEER_WARNED pattern in storage.py.
_DEMOTED_WARNED: set[str] = set()


# LLR-013.2: characters stripped from candidate user strings.
#  - Control chars (\x00-\x1f, \x7f)
#  - Unicode bidi/RTL overrides (U+202A LRE, U+202B RLE, U+202C PDF, U+202D LRO,
#    U+202E RLO, U+2066 LRI, U+2067 RLI, U+2068 FSI, U+2069 PDI)
#  - Zero-width / NBSP / NEL (CR-005): U+200B ZWSP, U+200C ZWNJ, U+200D ZWJ,
#    U+FEFF BOM, U+0085 NEL, U+00A0 NBSP
_USER_STRIP_CHARS = (
    "".join(chr(c) for c in range(0x00, 0x20))
    + "\x7f"
    + "‪‫‬‭‮⁦⁧⁨⁩"
    + "​‌‍﻿ "
)
_USER_STRIP_TRANS = str.maketrans("", "", _USER_STRIP_CHARS)
_USER_MAX_LEN = 64


def _sanitize_user_candidate(raw: str | None) -> str | None:
    """Apply LLR-013.2 sanitization to a single user-source candidate.

    Returns the sanitized non-empty string when the candidate is acceptable,
    or `None` to signal the caller should fall through to the next source.
    Rejects (returns None) any input that originally contained `\\r` or `\\n`.
    Strips control chars, Unicode bidi overrides, and zero-width characters,
    then caps length at 64 chars. Never synthesizes the literal string `"unknown"`.
    """
    if raw is None:
        return None
    if "\r" in raw or "\n" in raw:
        return None
    cleaned = raw.translate(_USER_STRIP_TRANS).strip()
    if not cleaned:
        return None
    return cleaned[:_USER_MAX_LEN]


def _resolve_user(file_value: str | None) -> str:
    # LLR-013.2: each source is sanitized; failures fall through to the next.
    candidate = _sanitize_user_candidate(os.environ.get("PROJSTATUS_USER"))
    if candidate is not None:
        return candidate
    candidate = _sanitize_user_candidate(str(file_value) if file_value else None)
    if candidate is not None:
        return candidate
    try:
        candidate = _sanitize_user_candidate(os.getlogin().split(".")[0].split("_")[0])
    except OSError:
        candidate = None
    return candidate or "unknown"


def _resolve_data_root(file_value: str | None, code_root: Path) -> Path:
    raw = os.environ.get("PROJSTATUS_DATA_ROOT") or file_value or str(code_root)
    root = Path(raw).expanduser()
    # Mirror StorageService's mkdir-on-init behavior so a brand-new mount path works.
    # Refuse to silently create an entirely missing tree (likely a typo).
    if not root.exists() and not root.parent.exists():
        raise SystemExit(f"PROJSTATUS_DATA_ROOT parent does not exist: {root.parent}")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _resolve_peer_roots(file_value: object | None) -> list[tuple[str, Path, bool]]:
    """Parse `label=path,label=path` from env (writable always False), or a list of
    `[{label, path, writable?}]` from TOML (writable defaults to False; non-bool coerces
    to False per LLR-002.1)."""
    raw = os.environ.get("PROJSTATUS_PEER_ROOTS", "").strip()
    triples: list[tuple[str, str, bool]] = []
    if raw:
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if "=" not in chunk:
                continue
            label, path = chunk.split("=", 1)
            label, path = label.strip(), path.strip()
            if label and path:
                triples.append((label, path, False))
    elif isinstance(file_value, list):
        for entry in file_value:
            if isinstance(entry, dict) and entry.get("label") and entry.get("path"):
                writable = entry.get("writable", False) is True
                triples.append((str(entry["label"]).strip(), str(entry["path"]).strip(), writable))
    return [(label, Path(path).expanduser(), writable) for label, path, writable in triples]


def _dangerous_writable_predicate(resolved_path: Path, data_root: Path) -> str | None:
    """LLR-012.1: classify a resolved writable peer-root path as dangerous, returning
    a short predicate name (`root`, `home-dir`, `data-root-ancestor`,
    `ssh-credentials`, `aws-credentials`, `system-bin`, `windows-appdata`, …) when
    the path matches a block-list predicate, or None when it is safe.
    """
    # Filesystem roots: POSIX `/`, Windows `C:\`, etc.
    if resolved_path == Path(resolved_path.anchor or "/"):
        return "filesystem-root"
    # `Path.home()` itself.
    home = Path.home().resolve(strict=False)
    if resolved_path == home:
        return "home-dir"
    # Ancestor of (or equal to) data_root.
    if data_root.is_relative_to(resolved_path):
        return "data-root-ancestor"
    # Sensitive home-directory children (POSIX-style; many also exist on WSL/Cygwin).
    sensitive_home_children = {
        "ssh-credentials": home / ".ssh",
        "aws-credentials": home / ".aws",
        "config-dir": home / ".config",
        "gnupg-credentials": home / ".gnupg",
        "kube-config": home / ".kube",
        "docker-config": home / ".docker",
    }
    for name, sensitive in sensitive_home_children.items():
        sensitive_resolved = sensitive.resolve(strict=False)
        if resolved_path == sensitive_resolved or sensitive_resolved.is_relative_to(resolved_path):
            return name
        if resolved_path.is_relative_to(sensitive_resolved):
            return name
    # POSIX system directories.
    for posix_root in ("/etc", "/usr", "/var", "/bin", "/sbin"):
        candidate = Path(posix_root)
        try:
            candidate_resolved = candidate.resolve(strict=False)
        except OSError:
            continue
        if not candidate_resolved.exists() and candidate.anchor != resolved_path.anchor:
            continue  # path doesn't exist on this OS — skip silently
        if resolved_path == candidate_resolved or resolved_path.is_relative_to(candidate_resolved):
            return f"system-bin:{posix_root}"
    # Windows env-var-driven sensitive locations.
    for env_name in ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA"):
        env_value = os.environ.get(env_name)
        if not env_value:
            continue
        try:
            env_path = Path(env_value).resolve(strict=False)
        except OSError:
            continue
        if resolved_path == env_path or resolved_path.is_relative_to(env_path):
            return f"windows-{env_name.lower()}"
    return None


def _demote_dangerous_writable_peers(
    peer_roots: list[tuple[str, Path, bool]], data_root: Path
) -> list[tuple[str, Path, bool]]:
    """LLR-012.1: post-pass on resolved peer triples. Demotes any writable entry whose
    resolved path matches a dangerous-path predicate; emits one stderr warning per
    demoted entry per process lifetime; leaves non-writable entries and safe writable
    entries untouched.
    """
    resolved_data_root = data_root.resolve(strict=False)
    out: list[tuple[str, Path, bool]] = []
    for label, path, writable in peer_roots:
        if not writable:
            out.append((label, path, writable))
            continue
        resolved = path.resolve(strict=False)
        predicate = _dangerous_writable_predicate(resolved, resolved_data_root)
        if predicate is None:
            out.append((label, path, writable))
            continue
        warning_key = f"{label}={resolved}"
        if warning_key not in _DEMOTED_WARNED:
            print(
                f"WARNING: peer-root {label!r} demoted to read-only — path {resolved} "
                f"is unsafe to mark writable (matched: {predicate})",
                file=sys.stderr,
            )
            _DEMOTED_WARNED.add(warning_key)
        out.append((label, path, False))
    return out


@dataclass(frozen=True)
class Settings:
    data_root: Path
    peer_roots: list[tuple[str, Path, bool]] = field(default_factory=list)
    user: str = "unknown"

    @classmethod
    def load(cls, code_root: Path | None = None) -> "Settings":
        code_root = (code_root or Path(__file__).resolve().parents[1]).resolve()
        file_data: dict[str, object] = {}
        if CONFIG_PATH.exists():
            try:
                with CONFIG_PATH.open("rb") as f:
                    file_data = tomllib.load(f) or {}
            except (OSError, tomllib.TOMLDecodeError) as exc:
                print(f"[projstatus] Ignoring malformed {CONFIG_PATH}: {exc}", file=sys.stderr)
        data_root = _resolve_data_root(file_data.get("data_root"), code_root)  # type: ignore[arg-type]
        peer_roots = _resolve_peer_roots(file_data.get("peer_roots"))
        # LLR-012.1: demote dangerous writable peer-root paths AFTER both
        # _resolve_peer_roots and _resolve_data_root have completed, since the
        # ancestor-of-data-root check needs data_root.
        peer_roots = _demote_dangerous_writable_peers(peer_roots, data_root)
        return cls(
            data_root=data_root,
            peer_roots=peer_roots,
            user=_resolve_user(file_data.get("user")),  # type: ignore[arg-type]
        )
