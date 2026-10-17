import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from antigravity_updater import cli, settings

URL = "https://example.invalid/antigravity-cli/1.4.0-123/linux-x64/cli_linux_x64.tar.gz"


def _manifesto(url=URL, sha512="a" * 128):
    return json.dumps({"version": "1.4.0", "url": url, "sha512": sha512})


def _tar_plano(caminho, nome="antigravity", conteudo=b"#!/bin/sh\necho 1.4.0\n"):
    with tarfile.open(caminho, "w:gz") as archive:
        info = tarfile.TarInfo(nome)
        info.size = len(conteudo)
        info.mode = 0o755
        archive.addfile(info, io.BytesIO(conteudo))


def test_manifesto_valido_e_selecao(updater_module):
    manifesto = updater_module.interpretar_manifesto_cli(_manifesto())

    assert manifesto["url"] == URL
    assert updater_module.selecionar_download_manifesto(manifesto) == (URL, "a" * 128)
    assert updater_module.selecionar_download_manifesto(manifesto, versao_fixada="1.4.0-123") == (URL, "a" * 128)
    assert updater_module.selecionar_download_manifesto(manifesto, versao_fixada="1.3.0-1") is None
    assert updater_module.selecionar_download_manifesto(None) is None


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "não é json",
        "[]",
        json.dumps({"url": URL}),
        _manifesto(sha512="curto"),
        _manifesto(url="http://example.invalid/1.0.0/cli.tar.gz"),
        _manifesto(url="https://example.invalid/1.0.0/cli.zip"),
    ],
)
def test_manifesto_malformado_ou_inseguro_e_rejeitado(updater_module, texto):
    assert updater_module.interpretar_manifesto_cli(texto) is None


def test_canal_stable_ignora_preview_no_manifesto(updater_module):
    preview = updater_module.interpretar_manifesto_cli(
        _manifesto(url="https://example.invalid/antigravity-cli/1.5.0-beta1/linux-x64/cli.tar.gz")
    )

    assert updater_module.selecionar_download_manifesto(preview, "stable") is None
    assert updater_module.selecionar_download_manifesto(preview, "preview") is not None


def test_base_dos_manifestos_vem_do_instalador_com_fallback(updater_module):
    script = '#!/bin/bash\nDOWNLOAD_BASE_URL="https://cdn.example.invalid/base/"\n'

    assert updater_module.descobrir_base_manifestos_cli(script) == "https://cdn.example.invalid/base"
    assert updater_module.descobrir_base_manifestos_cli("") == updater_module.URL_MANIFESTOS_CLI
    assert updater_module.descobrir_base_manifestos_cli('DOWNLOAD_BASE_URL="http://inseguro"') == (
        updater_module.URL_MANIFESTOS_CLI
    )


@pytest.mark.parametrize(
    ("arquitetura", "musl", "esperado"),
    [
        ("linux-x64", False, "linux_amd64"),
        ("linux-arm", False, "linux_arm64"),
        ("linux-x64", True, "linux_amd64_musl"),
    ],
)
def test_plataforma_do_cli(updater_module, monkeypatch, arquitetura, musl, esperado):
    monkeypatch.setattr(updater_module.os.path, "exists", lambda _caminho: musl)

    assert updater_module.detectar_plataforma_cli(arquitetura) == esperado


def test_pacote_plano_do_cli_preserva_executavel_na_raiz(updater_module, tmp_path):
    pacote = tmp_path / "cli.tar.gz"
    _tar_plano(pacote)
    staging = tmp_path / "staging"
    staging.mkdir()

    updater_module.extrair_pacote_seguro(pacote, staging, strip=0)

    executavel = updater_module.validar_instalacao_extraida("Antigravity_CLI", staging)
    assert Path(executavel) == staging / "antigravity"


def test_pacote_plano_com_strip_padrao_perde_o_executavel(updater_module, tmp_path):
    """Documenta por que o CLI precisa de strip=0: o padrão remove um nível."""
    pacote = tmp_path / "cli.tar.gz"
    _tar_plano(pacote)
    staging = tmp_path / "staging"
    staging.mkdir()

    updater_module.extrair_pacote_seguro(pacote, staging)

    with pytest.raises(ValueError, match="Executável esperado"):
        updater_module.validar_instalacao_extraida("Antigravity_CLI", staging)


def test_pacote_do_cli_ainda_bloqueia_path_traversal(updater_module, tmp_path):
    pacote = tmp_path / "cli.tar.gz"
    _tar_plano(pacote, nome="../antigravity")
    staging = tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(ValueError, match="inseguro"):
        updater_module.extrair_pacote_seguro(pacote, staging, strip=0)


def test_publicacao_verifica_sha512(updater_module, tmp_path):
    conteudo = b"pacote"
    correto = hashlib.sha512(conteudo).hexdigest()
    parcial = tmp_path / "a.part"
    parcial.write_bytes(conteudo)

    with pytest.raises(Exception, match="SHA-512"):
        updater_module._publicar_download(parcial, tmp_path / "x.tar.gz", "0" * 128, "sha512")
    assert not (tmp_path / "x.tar.gz").exists()

    updater_module._publicar_download(parcial, tmp_path / "x.tar.gz", correto.upper(), "sha512")
    assert (tmp_path / "x.tar.gz").read_bytes() == conteudo


def test_cli_nao_possui_launcher(updater_module, tmp_path):
    updater_module.configurar_caminhos(tmp_path / "apps", tmp_path / "lock", tmp_path / "launchers")

    assert not updater_module.possui_launcher("Antigravity_CLI")
    assert updater_module.caminho_launcher("Antigravity_CLI") is None
    assert updater_module.criar_atalho("Antigravity_CLI") is False
    assert updater_module.remover_atalho("Antigravity_CLI") is False
    assert updater_module.possui_launcher("Antigravity")


def test_instalacao_completa_do_cli_pelo_manifesto(updater_module, monkeypatch, tmp_path):
    pacote = tmp_path / "origem.tar.gz"
    _tar_plano(pacote)
    sha512 = hashlib.sha512(pacote.read_bytes()).hexdigest()
    base = tmp_path / "apps"
    updater_module.configurar_caminhos(base, tmp_path / "lock", tmp_path / "launchers")
    updater_module.preparar_diretorios(tmp_path)
    updater_module.manifesto_cli = updater_module.interpretar_manifesto_cli(_manifesto(sha512=sha512))
    chamadas = []

    def baixar(url, destino, rotulo, checksum, arquivo_parcial=None, algoritmo_checksum="sha256"):
        chamadas.append((url, rotulo, checksum, algoritmo_checksum))
        Path(destino).write_bytes(pacote.read_bytes())
        return True

    monkeypatch.setattr(updater_module, "download_com_progresso", baixar)
    monkeypatch.setattr(updater_module, "obter_data_servidor", lambda _url: None)
    monkeypatch.setattr(updater_module, "obter_checksum_remoto", pytest.fail)

    assert updater_module.atualizar_aplicativo("Antigravity_CLI", None, "cli")

    assert chamadas == [(URL, "Antigravity CLI", sha512, "sha512")]
    ativa = updater_module.obter_versao_ativa("Antigravity_CLI")
    assert Path(ativa).name == "Antigravity_CLI-1.4.0-123"
    assert (base / "Antigravity_CLI" / "antigravity").is_file()
    manifesto = json.loads((Path(ativa) / ".install-manifest.json").read_text(encoding="utf-8"))
    assert manifesto["checksum_verified"] is True
    assert manifesto["checksum_algorithm"] == "sha512"
    assert not list((tmp_path / "launchers").glob("*"))


def test_cli_sem_manifesto_falha_sem_baixar(updater_module, monkeypatch, tmp_path):
    updater_module.configurar_caminhos(tmp_path / "apps", tmp_path / "lock", tmp_path / "launchers")
    updater_module.manifesto_cli = None
    monkeypatch.setattr(updater_module, "download_com_progresso", pytest.fail)

    assert updater_module.atualizar_aplicativo("Antigravity_CLI", None, "cli") is False


def test_selecao_de_alvos():
    assert cli._selected_apps("app") == ["Antigravity"]
    assert cli._selected_apps("hub") == ["Antigravity"]
    assert cli._selected_apps("cli") == ["Antigravity_CLI"]
    assert cli._selected_apps("both") == ["Antigravity", "Antigravity_IDE"]
    assert cli._selected_apps("all") == ["Antigravity", "Antigravity_IDE", "Antigravity_CLI"]


def test_processa_cada_aplicativo_com_o_pin_correto(monkeypatch):
    vistos = []
    monkeypatch.setattr(
        cli.core,
        "atualizar_aplicativo",
        lambda nome, padrao, aba, **kw: vistos.append((nome, padrao, aba, kw["versao_fixada"])) or True,
    )
    configurado = settings.Settings(pin_app="2.0.0", pin_ide="3.0.0", pin_cli="1.4.0-123")

    assert cli._process_remote_apps("all", configurado) == [True, True, True]
    assert vistos == [
        ("Antigravity", "antigravity-hub", "hub", "2.0.0"),
        ("Antigravity_IDE", "stable", "ide", "3.0.0"),
        ("Antigravity_CLI", None, "cli", "1.4.0-123"),
    ]


def test_pin_hub_antigo_continua_funcionando():
    assert settings.from_dict({"pin_hub": "2.0.0"}).pin_app == "2.0.0"
    assert settings.with_value(settings.Settings(), "pin_hub", "1.0.0").pin_app == "1.0.0"
    with pytest.raises(ValueError):
        settings.from_dict({"pin_hub": "1.0.0", "pin_app": "2.0.0"})


def test_config_set_aceita_pin_hub_e_exibe_pin_app(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    assert cli.main(["config", "set", "pin_hub", "2.0.0", "--user"]) == 0
    assert capsys.readouterr().out.strip().endswith("pin_app=2.0.0")
    assert cli.main(["config", "set", "pin_cli", "1.4.0-1", "--user"]) == 0


def test_launcher_ignora_cli_sem_falhar(monkeypatch, capsys):
    monkeypatch.setattr(cli.core, "criar_atalho", lambda app: True)
    paths = type("P", (), {"requires_root": False, "scope": "system"})()
    monkeypatch.setattr(cli, "_begin_mutation", lambda *_a, **_k: True)
    namespace = cli.argparse.Namespace(command="launcher", action="install", target="cli", scope="system")

    assert cli._run_mutation(namespace, paths) == 0
    assert "sem launcher" in capsys.readouterr().out
