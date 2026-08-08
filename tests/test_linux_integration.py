import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from antigravity_updater import cli
from antigravity_updater import systemd as systemd_integration
from antigravity_updater.paths import ScopePaths, resolve_scope


def _user_paths(tmp_path):
    return ScopePaths(
        scope="user",
        base_dir=tmp_path / "data" / "apps",
        lock_file=tmp_path / "state" / "updater.lock",
        state_dir=tmp_path / "state",
        launcher_dir=tmp_path / "data" / "applications",
        unit_dir=tmp_path / "config" / "systemd" / "user",
        config_dir=tmp_path / "config" / "antigravity-updater",
        systemctl=("systemctl", "--user"),
        requires_root=False,
    )


def _active_installation(core, paths, name="Antigravity", version="1.2.3"):
    history = paths.base_dir / f"{name}_VERSOES"
    version_dir = history / f"{name}-{version}"
    version_dir.mkdir(parents=True)
    executable = "antigravity" if name == "Antigravity" else "antigravity-ide"
    binary = version_dir / executable
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    (version_dir / "version.txt").write_text(f"{version}\n", encoding="utf-8")
    (paths.base_dir / name).symlink_to(version_dir.relative_to(paths.base_dir))
    return version_dir


def test_resolve_escopo_usuario_respeita_xdg(tmp_path):
    paths = resolve_scope(
        "user",
        environment={
            "XDG_DATA_HOME": str(tmp_path / "xdg-data"),
            "XDG_STATE_HOME": str(tmp_path / "xdg-state"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg-config"),
        },
        home=tmp_path / "home",
    )

    assert paths.base_dir == tmp_path / "xdg-data" / "antigravity-updater" / "apps"
    assert paths.lock_file == tmp_path / "xdg-state" / "antigravity-updater" / "updater.lock"
    assert paths.launcher_dir == tmp_path / "xdg-data" / "applications"
    assert paths.unit_dir == tmp_path / "xdg-config" / "systemd" / "user"
    assert paths.systemctl == ("systemctl", "--user")
    assert not paths.requires_root


def test_resolve_escopo_usuario_ignora_xdg_relativo(tmp_path):
    paths = resolve_scope(
        "user",
        environment={"XDG_DATA_HOME": "data-relativa"},
        home=tmp_path,
    )

    assert paths.base_dir == tmp_path / ".local" / "share" / "antigravity-updater" / "apps"


def test_resolve_escopo_sistema_preserva_caminhos_historicos():
    paths = resolve_scope("system")

    assert paths.base_dir == Path("/opt/antigravity_apps")
    assert paths.lock_file == Path("/run/lock/antigravity-updater.lock")
    assert paths.requires_root


def test_launcher_xdg_e_instalado_e_removido(updater_module, tmp_path):
    paths = _user_paths(tmp_path)
    updater_module.configurar_caminhos(paths.base_dir, paths.lock_file, paths.launcher_dir)
    _active_installation(updater_module, paths)

    assert updater_module.criar_atalho("Antigravity")
    launcher = paths.launcher_dir / "antigravity-hub.desktop"
    content = launcher.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content
    assert f'Exec="{paths.base_dir}/Antigravity/antigravity"' in content
    assert stat.S_IMODE(launcher.stat().st_mode) == 0o644
    assert updater_module.remover_atalho("Antigravity")
    assert not launcher.exists()


def test_desinstalacao_remove_apenas_catalogo_gerenciado(updater_module, tmp_path):
    paths = _user_paths(tmp_path)
    updater_module.configurar_caminhos(paths.base_dir, paths.lock_file, paths.launcher_dir)
    active = _active_installation(updater_module, paths)
    updater_module.gravar_estado("Antigravity", active)
    assert updater_module.criar_atalho("Antigravity")

    assert updater_module.desinstalar_aplicativo("Antigravity")
    assert not (paths.base_dir / "Antigravity").exists()
    assert not (paths.base_dir / "Antigravity_VERSOES").exists()
    assert not (paths.base_dir / ".Antigravity-state").exists()
    assert not (paths.launcher_dir / "antigravity-hub.desktop").exists()


def test_desinstalacao_recusa_link_ativo_nao_gerenciado(updater_module, tmp_path):
    paths = _user_paths(tmp_path)
    paths.base_dir.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    (paths.base_dir / "Antigravity").symlink_to(external)
    updater_module.configurar_caminhos(paths.base_dir, paths.lock_file, paths.launcher_dir)

    with pytest.raises(RuntimeError, match="não é um link gerenciado"):
        updater_module.desinstalar_aplicativo("Antigravity")
    assert external.is_dir()


def test_desinstalacao_remove_link_gerenciado_quebrado(updater_module, tmp_path):
    paths = _user_paths(tmp_path)
    paths.base_dir.mkdir(parents=True)
    link = paths.base_dir / "Antigravity"
    link.symlink_to("Antigravity_VERSOES/Antigravity-inexistente")
    updater_module.configurar_caminhos(paths.base_dir, paths.lock_file, paths.launcher_dir)

    assert updater_module.desinstalar_aplicativo("Antigravity")
    assert not link.is_symlink()


def test_unidades_systemd_de_usuario_usam_cli_e_escopo_corretos(tmp_path):
    paths = _user_paths(tmp_path)
    service, timer = systemd_integration.render_units(
        paths,
        Path("/usr/bin/python3"),
        Path("/opt/updater/upgrade.py"),
        "Mon..Fri 02:00",
    )

    assert '"update" "--both" "--user"' in service
    assert f'Environment="XDG_DATA_HOME={paths.launcher_dir.parent}"' in service
    assert "NoNewPrivileges=true" in service
    assert "UMask=0077" in service
    assert "OnCalendar=Mon..Fri 02:00" in timer
    with pytest.raises(ValueError, match="Calendário"):
        systemd_integration.render_units(paths, Path("/usr/bin/python3"), Path("/app.py"), "daily\n[Service]")


def test_instala_e_remove_unidades_systemd_atomicamente(monkeypatch, tmp_path):
    paths = _user_paths(tmp_path)
    commands = []

    def run(command):
        commands.append(tuple(command))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(systemd_integration, "_run", run)
    systemd_integration.install_units(paths, Path("/usr/bin/python3"), Path("/app/upgrade.py"))

    service = paths.unit_dir / systemd_integration.SERVICE_NAME
    timer = paths.unit_dir / systemd_integration.TIMER_NAME
    assert service.is_file() and timer.is_file()
    assert stat.S_IMODE(service.stat().st_mode) == 0o644
    assert commands[-1] == ("systemctl", "--user", "enable", "--now", systemd_integration.TIMER_NAME)

    systemd_integration.remove_units(paths)
    assert not service.exists() and not timer.exists()
    assert commands[-1] == ("systemctl", "--user", "daemon-reload")


def test_mutacao_no_escopo_usuario_nao_exige_root(monkeypatch, tmp_path):
    paths = _user_paths(tmp_path)
    monkeypatch.setattr(cli, "resolve_scope", lambda _scope: paths)
    monkeypatch.setattr(cli.core, "verificar_privilegios", pytest.fail)

    assert cli.main(["prune", "2", "--hub", "--user"]) == 0
    assert paths.lock_file.is_file()
    assert stat.S_IMODE(paths.lock_file.parent.stat().st_mode) == 0o700


def test_systemd_de_usuario_nao_exige_root(monkeypatch, tmp_path):
    paths = _user_paths(tmp_path)
    installed = []
    monkeypatch.setattr(cli, "resolve_scope", lambda _scope: paths)
    monkeypatch.setattr(cli.core, "verificar_privilegios", pytest.fail)
    monkeypatch.setattr(
        cli.systemd_integration,
        "install_units",
        lambda selected, *_args: installed.append(selected),
    )

    assert cli.main(["systemd", "install", "--user"]) == 0
    assert installed == [paths]


@pytest.mark.parametrize(
    ("arguments", "command", "scope"),
    [
        (["update", "--user", "--hub"], "update", "user"),
        (["--user", "--hub"], "update", "user"),
        (["uninstall", "--system", "--ide"], "uninstall", "system"),
        (["launcher", "install", "--user"], "launcher", "user"),
        (["systemd", "status", "--user"], "systemd", "user"),
    ],
)
def test_cli_aceita_comandos_do_m5(arguments, command, scope):
    parsed = cli.parse_args(arguments)
    assert parsed.command == command
    assert parsed.scope == scope
