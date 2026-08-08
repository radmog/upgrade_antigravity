import io
import os
import stat
import tarfile
import urllib.error
from pathlib import Path

import pytest


def test_detecta_arquiteturas_suportadas(updater_module):
    assert updater_module.detectar_arquitetura("x86_64") == "linux-x64"
    assert updater_module.detectar_arquitetura("aarch64") == "linux-arm"
    assert updater_module.detectar_arquitetura("arm64") == "linux-arm"


def test_rejeita_arquitetura_desconhecida(updater_module):
    with pytest.raises(ValueError, match="Arquitetura não suportada"):
        updater_module.detectar_arquitetura("riscv64")


def test_codigo_saida_reflete_resultado_agregado(updater_module):
    assert updater_module.codigo_saida(True) == 0
    assert updater_module.codigo_saida(False) == 1


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({"LC_ALL": "pt_BR.UTF-8"}, "pt"),
        ({"LC_MESSAGES": "es_ES.UTF-8"}, "es"),
        ({"LANG": "C"}, "en"),
    ],
)
def test_detecta_idioma(updater_module, monkeypatch, environment, expected):
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    assert updater_module.obter_idioma_sistema() == expected


def test_extrai_changelog_por_aplicativo(updater_module, fixture_dir):
    updater_module.conteudo_changelog = (fixture_dir / "changelog.html").read_text(encoding="utf-8")

    assert updater_module.obter_versao_mais_recente("hub") == "1.2.3"
    assert updater_module.obter_versao_mais_recente("ide") == "4.5.6"

    notes = updater_module.obter_notas_versao("hub", "1.2.3")
    assert notes == {
        "titulo": "Antigravity Hub 1.2.3",
        "resumo": "Uma versão de teste & estável.",
        "grupos": [("Correções", ["Corrige a atualização automática."])],
    }


def test_fixture_documenta_formato_atual_da_pagina_de_download(fixture_dir):
    content = (fixture_dir / "download.html").read_text(encoding="utf-8")
    assert "antigravity-hub/1.2.3/linux-x64" in content
    assert "stable/4.5.6/linux-arm" in content


def test_importar_modulo_nao_cria_diretorios(updater_module, monkeypatch, tmp_path):
    base = tmp_path / "base"
    monkeypatch.setattr(updater_module, "DIRETORIO_BASE", str(base))

    assert not base.exists()
    temporary = Path(updater_module.preparar_diretorios(tmp_path))
    assert base.is_dir()
    assert temporary.is_dir()
    assert stat.S_IMODE(temporary.stat().st_mode) == 0o700
    updater_module.limpar_diretorio_temporario()
    assert not temporary.exists()


def test_lock_impede_segunda_execucao(updater_module, tmp_path):
    lock = tmp_path / "updater.lock"
    updater_module.adquirir_bloqueio(str(lock))
    try:
        with pytest.raises(RuntimeError, match="já está em execução"):
            updater_module.adquirir_bloqueio(str(lock))
    finally:
        updater_module.liberar_bloqueio()


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/app.tar.gz",
        "https://user:password@example.com/app.tar.gz",
        "https://example.com/app.zip",
        "not-a-url",
    ],
)
def test_rejeita_url_de_download_insegura(updater_module, url):
    with pytest.raises(ValueError):
        updater_module.validar_url_download(url)


class _RespostaBytes:
    def __init__(self, content, url="https://example.com/app.tar.gz"):
        self.content = io.BytesIO(content)
        self.headers = {"Content-Length": str(len(content))}
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def info(self):
        return self.headers

    def geturl(self):
        return self.url

    def read(self, size=-1):
        return self.content.read(size)


def test_download_retenta_e_publica_apenas_arquivo_completo(updater_module, monkeypatch, tmp_path):
    conteudo = b"pacote valido"
    respostas = iter([urllib.error.URLError("temporario"), _RespostaBytes(conteudo)])

    def urlopen(*_args, **_kwargs):
        resposta = next(respostas)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    monkeypatch.setattr(updater_module.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(updater_module.time, "sleep", lambda _seconds: None)
    destino = tmp_path / "app.tar.gz"
    checksum = updater_module.hashlib.sha256(conteudo).hexdigest()

    assert updater_module.download_com_progresso(
        "https://example.com/app.tar.gz", destino, "App", checksum
    )
    assert destino.read_bytes() == conteudo
    assert not Path(f"{destino}.part").exists()


def test_download_descarta_parcial_com_checksum_incorreto(updater_module, monkeypatch, tmp_path):
    conteudo = b"conteudo adulterado"
    monkeypatch.setattr(
        updater_module.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _RespostaBytes(conteudo),
    )
    monkeypatch.setattr(updater_module.time, "sleep", lambda _seconds: None)
    destino = tmp_path / "app.tar.gz"

    assert not updater_module.download_com_progresso(
        "https://example.com/app.tar.gz", destino, "App", "0" * 64
    )
    assert not destino.exists()
    assert not Path(f"{destino}.part").exists()


def test_download_rejeita_redirecionamento_para_http(updater_module, monkeypatch, tmp_path):
    monkeypatch.setattr(
        updater_module.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _RespostaBytes(b"dados", "http://example.com/app.tar.gz"),
    )
    monkeypatch.setattr(updater_module.time, "sleep", lambda _seconds: None)
    destino = tmp_path / "app.tar.gz"

    assert not updater_module.download_com_progresso(
        "https://example.com/app.tar.gz", destino, "App"
    )
    assert not destino.exists()


def _criar_tar(caminho, membros):
    with tarfile.open(caminho, "w:gz") as archive:
        for nome, conteudo, modo in membros:
            info = tarfile.TarInfo(nome)
            info.size = len(conteudo)
            info.mode = modo
            archive.addfile(info, io.BytesIO(conteudo))


def test_extrai_pacote_valido_em_staging(updater_module, tmp_path):
    pacote = tmp_path / "app.tar.gz"
    _criar_tar(pacote, [("app/antigravity", b"#!/bin/sh\n", 0o755)])
    staging = tmp_path / "staging"
    staging.mkdir()

    updater_module.extrair_pacote_seguro(pacote, staging)

    executavel = updater_module.validar_instalacao_extraida("Antigravity", staging)
    assert Path(executavel).is_file()
    assert os.access(executavel, os.X_OK)


def test_bloqueia_path_traversal_no_pacote(updater_module, tmp_path):
    pacote = tmp_path / "malicioso.tar.gz"
    _criar_tar(pacote, [("app/../../fora", b"perigo", 0o644)])
    staging = tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(ValueError, match="Caminho inseguro"):
        updater_module.extrair_pacote_seguro(pacote, staging)
    assert not (tmp_path / "fora").exists()


def test_bloqueia_escrita_atraves_de_symlink(updater_module, tmp_path):
    pacote = tmp_path / "link.tar.gz"
    with tarfile.open(pacote, "w:gz") as archive:
        link = tarfile.TarInfo("app/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "destino"
        archive.addfile(link)
        arquivo = tarfile.TarInfo("app/link/arquivo")
        arquivo.size = 4
        archive.addfile(arquivo, io.BytesIO(b"data"))
    staging = tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(ValueError, match="através de um link"):
        updater_module.extrair_pacote_seguro(pacote, staging)


def test_staging_registra_manifesto_e_publica_versao(updater_module, monkeypatch, tmp_path):
    pacote = tmp_path / "app.tar.gz"
    _criar_tar(pacote, [("app/antigravity", b"#!/bin/sh\n", 0o4755)])
    base = tmp_path / "base"
    session = tmp_path / "session"
    session.mkdir()
    monkeypatch.setattr(updater_module, "DIRETORIO_BASE", str(base))
    monkeypatch.setattr(updater_module, "PASTA_TMP", str(session))

    destino = updater_module.preparar_versao_em_staging(
        "Antigravity",
        "1.2.3",
        pacote,
        "https://example.com/app.tar.gz",
        "a" * 64,
        True,
    )

    manifesto = Path(destino) / ".install-manifest.json"
    assert manifesto.is_file()
    assert stat.S_IMODE(Path(destino).stat().st_mode) == 0o755
    assert stat.S_IMODE((Path(destino) / "antigravity").stat().st_mode) & 0o6000 == 0
    assert '"checksum_verified": true' in manifesto.read_text(encoding="utf-8")
    assert (Path(destino) / "version.txt").read_text(encoding="utf-8") == "1.2.3\n"


def test_readme_nao_executa_servico_com_usuario_sem_privilegio():
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    assert "User=rguedes" not in readme
    assert readme.count("User=root") == 2
