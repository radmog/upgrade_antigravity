import os
from pathlib import Path

import pytest


def _criar_versao(base, nome_app, versao, exit_code=0):
    raiz = base / f"{nome_app}_VERSOES"
    destino = raiz / f"{nome_app}-{versao}"
    destino.mkdir(parents=True)
    executavel = "antigravity" if nome_app == "Antigravity" else "antigravity-ide"
    script = destino / executavel
    script.write_text(
        f"#!/bin/sh\nprintf 'runtime-{versao}\\n'\nexit {exit_code}\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    (destino / "version.txt").write_text(f"{versao}\n", encoding="utf-8")
    return destino


def _configurar_base(updater_module, monkeypatch, tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    monkeypatch.setattr(updater_module, "DIRETORIO_BASE", str(base))
    return base


def test_lista_versoes_e_identifica_ativa(updater_module, monkeypatch, tmp_path):
    base = _configurar_base(updater_module, monkeypatch, tmp_path)
    antiga = _criar_versao(base, "Antigravity", "1.2.3")
    nova = _criar_versao(base, "Antigravity", "2.0.0")
    (base / "Antigravity").symlink_to(nova.relative_to(base))

    versoes = updater_module.listar_versoes("Antigravity")

    assert [item["version"] for item in versoes] == ["2.0.0", "1.2.3"]
    assert next(item for item in versoes if item["active"])["path"] == str(nova)
    assert updater_module.obter_versao_ativa("Antigravity") == str(nova)
    assert antiga.is_dir()


def test_health_check_executa_binario_sem_interface(updater_module, monkeypatch, tmp_path):
    base = _configurar_base(updater_module, monkeypatch, tmp_path)
    versao = _criar_versao(base, "Antigravity", "1.0.0")

    assert updater_module.testar_saude_versao("Antigravity", versao) == "runtime-1.0.0"


def test_ativacao_atomica_registra_anterior(updater_module, monkeypatch, tmp_path):
    base = _configurar_base(updater_module, monkeypatch, tmp_path)
    anterior = _criar_versao(base, "Antigravity", "1.0.0")
    nova = _criar_versao(base, "Antigravity", "2.0.0")
    link = base / "Antigravity"
    link.symlink_to(anterior.relative_to(base))

    runtime = updater_module.ativar_versao_atomica("Antigravity", nova)

    assert runtime == "runtime-2.0.0"
    assert link.is_symlink()
    assert link.resolve() == nova
    assert updater_module.ler_estado("Antigravity") == {
        "active": str(nova),
        "previous": str(anterior),
    }


def test_falha_pos_ativacao_restaura_link_anterior(updater_module, monkeypatch, tmp_path):
    base = _configurar_base(updater_module, monkeypatch, tmp_path)
    anterior = _criar_versao(base, "Antigravity", "1.0.0")
    nova = _criar_versao(base, "Antigravity", "2.0.0")
    link = base / "Antigravity"
    link.symlink_to(anterior.relative_to(base))
    chamadas = iter(["runtime-2.0.0", RuntimeError("falha após ativação")])

    def healthcheck(*_args):
        resultado = next(chamadas)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    monkeypatch.setattr(updater_module, "testar_saude_versao", healthcheck)

    with pytest.raises(RuntimeError, match="falha após ativação"):
        updater_module.ativar_versao_atomica("Antigravity", nova)
    assert link.resolve() == anterior


def test_rollback_usa_estado_e_permite_retorno(updater_module, monkeypatch, tmp_path):
    base = _configurar_base(updater_module, monkeypatch, tmp_path)
    anterior = _criar_versao(base, "Antigravity", "1.0.0")
    nova = _criar_versao(base, "Antigravity", "2.0.0")
    (base / "Antigravity").symlink_to(nova.relative_to(base))
    updater_module.gravar_estado("Antigravity", nova, anterior)

    versao, runtime = updater_module.rollback_aplicativo("Antigravity")

    assert (versao, runtime) == ("1.0.0", "runtime-1.0.0")
    assert (base / "Antigravity").resolve() == anterior
    assert updater_module.ler_estado("Antigravity")["previous"] == str(nova)


def test_prune_preserva_ativa_e_anterior(updater_module, monkeypatch, tmp_path):
    base = _configurar_base(updater_module, monkeypatch, tmp_path)
    antiga = _criar_versao(base, "Antigravity", "1.0.0")
    anterior = _criar_versao(base, "Antigravity", "2.0.0")
    ativa = _criar_versao(base, "Antigravity", "3.0.0")
    (base / "Antigravity").symlink_to(ativa.relative_to(base))
    updater_module.gravar_estado("Antigravity", ativa, anterior)

    removidas = updater_module.podar_versoes("Antigravity", manter=1)

    assert removidas == ["1.0.0"]
    assert ativa.is_dir()
    assert anterior.is_dir()
    assert not antiga.exists()


def test_link_ativo_fora_do_historico_nao_e_aceito(updater_module, monkeypatch, tmp_path):
    base = _configurar_base(updater_module, monkeypatch, tmp_path)
    externo = tmp_path / "externo"
    externo.mkdir()
    (base / "Antigravity").symlink_to(os.path.relpath(externo, base))

    assert updater_module.obter_versao_ativa("Antigravity") is None

