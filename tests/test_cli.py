import os
import subprocess
import sys
from pathlib import Path

import pytest

from antigravity_updater import cli


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.geteuid() == 0, reason="o contrato testado exige usuário sem privilégios")
@pytest.mark.parametrize(
    "command",
    [
        [sys.executable, str(ROOT / "upgrade.py"), "--both"],
        ["bash", str(ROOT / "upgrade.sh"), "both"],
    ],
)
def test_instaladores_recusam_execucao_sem_root(command):
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    assert result.returncode == 1
    assert "privilégios de administrador" in result.stdout


def test_scripts_possuem_sintaxe_valida():
    python_result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROOT / "upgrade.py")],
        capture_output=True,
        check=False,
    )
    bash_result = subprocess.run(
        ["bash", "-n", str(ROOT / "upgrade.sh")],
        capture_output=True,
        check=False,
    )
    assert python_result.returncode == 0, python_result.stderr.decode()
    assert bash_result.returncode == 0, bash_result.stderr.decode()


@pytest.mark.parametrize(
    ("arguments", "command", "target"),
    [
        (["--current", "--hub"], "current", "hub"),
        (["--hub", "--current"], "current", "hub"),
        (["--changelog"], "changelog", "both"),
        (["list", "ide"], "list", "ide"),
        (["--both", "--force"], "update", "both"),
        (["rollback", "1.2.3", "hub"], "rollback", "hub"),
        (["10"], "prune", "both"),
    ],
)
def test_cli_preserva_argumentos_historicos(arguments, command, target):
    parsed = cli.parse_args(arguments)
    assert parsed.command == command
    assert parsed.target == target


@pytest.mark.parametrize("command", ["current", "list"])
def test_consultas_locais_nao_exigem_root(monkeypatch, command):
    privilege_check = pytest.fail
    monkeypatch.setattr(cli.core, "verificar_privilegios", privilege_check)
    monkeypatch.setattr(cli.core, "exibir_estado_aplicativos", lambda *_args, **_kwargs: None)

    assert cli.main([command, "--hub"]) == 0


def test_operacao_de_escrita_exige_root(monkeypatch):
    called = []

    def reject():
        called.append(True)
        raise SystemExit(1)

    monkeypatch.setattr(cli.core, "verificar_privilegios", reject)

    with pytest.raises(SystemExit):
        cli.main(["prune", "2", "--hub"])
    assert called == [True]


def test_upgrade_py_encaminha_help_para_cli_estruturada():
    result = subprocess.run(
        [sys.executable, str(ROOT / "upgrade.py"), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    for command in (
        "update",
        "changelog",
        "current",
        "list",
        "rollback",
        "prune",
        "uninstall",
        "launcher",
        "systemd",
    ):
        assert command in result.stdout
