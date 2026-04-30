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


def _resolve_user(file_value: str | None) -> str:
    if env := os.environ.get("PROJSTATUS_USER"):
        return env.strip()
    if file_value:
        return str(file_value).strip()
    try:
        return os.getlogin().split(".")[0].split("_")[0] or "unknown"
    except OSError:
        return "unknown"


def _resolve_data_root(file_value: str | None, code_root: Path) -> Path:
    raw = os.environ.get("PROJSTATUS_DATA_ROOT") or file_value or str(code_root)
    root = Path(raw).expanduser()
    # Mirror StorageService's mkdir-on-init behavior so a brand-new mount path works.
    # Refuse to silently create an entirely missing tree (likely a typo).
    if not root.exists() and not root.parent.exists():
        raise SystemExit(f"PROJSTATUS_DATA_ROOT parent does not exist: {root.parent}")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _resolve_peer_roots(file_value: object | None) -> list[tuple[str, Path]]:
    """Parse `label=path,label=path` from env, or a list of `[{label, path}]` from TOML."""
    raw = os.environ.get("PROJSTATUS_PEER_ROOTS", "").strip()
    pairs: list[tuple[str, str]] = []
    if raw:
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if "=" not in chunk:
                continue
            label, path = chunk.split("=", 1)
            label, path = label.strip(), path.strip()
            if label and path:
                pairs.append((label, path))
    elif isinstance(file_value, list):
        for entry in file_value:
            if isinstance(entry, dict) and entry.get("label") and entry.get("path"):
                pairs.append((str(entry["label"]).strip(), str(entry["path"]).strip()))
    return [(label, Path(path).expanduser()) for label, path in pairs]


@dataclass(frozen=True)
class Settings:
    data_root: Path
    peer_roots: list[tuple[str, Path]] = field(default_factory=list)
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
        return cls(
            data_root=_resolve_data_root(file_data.get("data_root"), code_root),  # type: ignore[arg-type]
            peer_roots=_resolve_peer_roots(file_data.get("peer_roots")),
            user=_resolve_user(file_data.get("user")),  # type: ignore[arg-type]
        )
