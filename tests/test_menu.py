import argparse

import pytest

from antigravity_updater import cli, core


def test_sair_e_ultima_opcao_do_menu():
    numbers = [number for number, _description in core.MENU_OPCOES]
    descriptions = [description for _number, description in core.MENU_OPCOES]

    assert numbers == list(range(1, len(core.MENU_OPCOES) + 1))
    assert core.MENU_OPCOES[-1] == (17, "Sair")
    assert all(description != "Sair" for description in descriptions[:-1])


def test_menu_exibe_escopo_e_aceita_ultima_opcao(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _prompt: "17")

    assert core.menu_selecao("user") == "17"
    output = capsys.readouterr().out
    assert "ESCOPO: USUÁRIO" in output
    assert output.rfind("Sair") > output.find("Desinstalar Ambos")


def test_cancelamento_do_menu_equivale_a_sair(monkeypatch):
    def interrupted(_prompt):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", interrupted)

    assert core.menu_selecao() == "17"


def test_menu_interativo_preserva_escopo_usuario(monkeypatch):
    monkeypatch.setattr(cli.core, "menu_selecao", lambda scope: "6")

    request = cli._interactive_request("user")

    assert request.command == "check"
    assert request.scope == "user"


def test_cli_aceita_escopo_isolado_para_abrir_menu():
    assert cli.parse_args(["--user"]) == argparse.Namespace(command=None, scope="user")
    assert cli.parse_args(["--system"]) == argparse.Namespace(command=None, scope="system")


def test_aliases_numericos_preservam_escopo_e_saida():
    check = cli.parse_args(["6", "--user"])

    assert check.command == "check"
    assert check.scope == "user"
    assert cli.parse_args(["--user", "17"]).command == "exit"


def test_desinstalacao_do_menu_exige_confirmacao(monkeypatch, capsys):
    namespace = argparse.Namespace(
        command="uninstall",
        target="both",
        keep_systemd=False,
        confirm=True,
        scope="user",
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "não")
    monkeypatch.setattr(cli, "resolve_scope", pytest.fail)

    assert cli.run(namespace) == 0
    assert "cancelada" in capsys.readouterr().out
