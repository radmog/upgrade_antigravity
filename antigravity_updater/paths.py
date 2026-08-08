"""Resolução centralizada de caminhos para instalações de usuário e sistema."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class ScopePaths:
    scope: str
    base_dir: Path
    lock_file: Path
    launcher_dir: Path
    unit_dir: Path
    systemctl: Tuple[str, ...]
    requires_root: bool


def _xdg_path(environment: Mapping[str, str], variable: str, fallback: Path) -> Path:
    configured = environment.get(variable, "").strip()
    candidate = Path(configured).expanduser() if configured else fallback
    return candidate if candidate.is_absolute() else fallback


def resolve_scope(
    scope: str,
    environment: Optional[Mapping[str, str]] = None,
    home: Optional[Path] = None,
) -> ScopePaths:
    """Resolve caminhos sem criar arquivos ou diretórios."""
    if scope not in ("user", "system"):
        raise ValueError(f"Escopo desconhecido: {scope}")
    if scope == "system":
        return ScopePaths(
            scope="system",
            base_dir=Path("/opt/antigravity_apps"),
            lock_file=Path("/run/lock/antigravity-updater.lock"),
            launcher_dir=Path("/usr/local/share/applications"),
            unit_dir=Path("/etc/systemd/system"),
            systemctl=("systemctl",),
            requires_root=True,
        )

    env = os.environ if environment is None else environment
    user_home = Path.home() if home is None else home
    data_home = _xdg_path(env, "XDG_DATA_HOME", user_home / ".local" / "share")
    state_home = _xdg_path(env, "XDG_STATE_HOME", user_home / ".local" / "state")
    config_home = _xdg_path(env, "XDG_CONFIG_HOME", user_home / ".config")
    return ScopePaths(
        scope="user",
        base_dir=data_home / "antigravity-updater" / "apps",
        lock_file=state_home / "antigravity-updater" / "updater.lock",
        launcher_dir=data_home / "applications",
        unit_dir=config_home / "systemd" / "user",
        systemctl=("systemctl", "--user"),
        requires_root=False,
    )
