"""Criação e gerenciamento das unidades systemd do atualizador."""

import os
import subprocess
from pathlib import Path
from typing import Sequence, Tuple

from .paths import ScopePaths


SERVICE_NAME = "antigravity-upgrade.service"
TIMER_NAME = "antigravity-upgrade.timer"


def _unit_argument(value: str) -> str:
    if not value or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError("Argumento inválido para unidade systemd.")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_units(paths: ScopePaths, python: Path, entrypoint: Path, calendar: str = "daily") -> Tuple[str, str]:
    if not calendar.strip() or any(character in calendar for character in "\r\n\x00"):
        raise ValueError("Calendário systemd inválido.")
    scope_flag = "--user" if paths.scope == "user" else "--system"
    command = " ".join(
        _unit_argument(str(item))
        for item in (python, entrypoint, "update", "--both", scope_flag)
    )
    environment_lines = ""
    if paths.scope == "user":
        xdg_values = (
            ("XDG_DATA_HOME", paths.launcher_dir.parent),
            ("XDG_STATE_HOME", paths.lock_file.parent.parent),
            ("XDG_CONFIG_HOME", paths.unit_dir.parents[1]),
        )
        environment_lines = "".join(
            f"Environment={_unit_argument(f'{name}={value}')}\n" for name, value in xdg_values
        )
    service = f"""[Unit]
Description=Atualização do Antigravity
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart={command}
{environment_lines}NoNewPrivileges=true
UMask=0077
"""
    timer = f"""[Unit]
Description=Atualização agendada do Antigravity

[Timer]
OnCalendar={calendar}
Persistent=true

[Install]
WantedBy=timers.target
"""
    return service, timer


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _run(command: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, check=False)


def install_units(
    paths: ScopePaths,
    python: Path,
    entrypoint: Path,
    calendar: str = "daily",
) -> None:
    service, timer = render_units(paths, python, entrypoint, calendar)
    _write_atomic(paths.unit_dir / SERVICE_NAME, service)
    _write_atomic(paths.unit_dir / TIMER_NAME, timer)
    reload_result = _run((*paths.systemctl, "daemon-reload"))
    if reload_result.returncode != 0:
        raise RuntimeError("systemctl daemon-reload falhou.")
    enable_result = _run((*paths.systemctl, "enable", "--now", TIMER_NAME))
    if enable_result.returncode != 0:
        raise RuntimeError("Não foi possível habilitar o timer systemd.")


def remove_units(paths: ScopePaths) -> None:
    _run((*paths.systemctl, "disable", "--now", TIMER_NAME))
    for name in (SERVICE_NAME, TIMER_NAME):
        candidate = paths.unit_dir / name
        if candidate.is_dir():
            raise RuntimeError(f"O caminho da unidade não é um arquivo: {candidate}")
        if candidate.exists() or candidate.is_symlink():
            candidate.unlink()
    reload_result = _run((*paths.systemctl, "daemon-reload"))
    if reload_result.returncode != 0:
        raise RuntimeError("systemctl daemon-reload falhou.")


def show_status(paths: ScopePaths) -> int:
    result = _run((*paths.systemctl, "status", "--no-pager", TIMER_NAME))
    return result.returncode
