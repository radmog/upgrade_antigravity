from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bash_usa_sessao_privada_e_lock():
    script = (ROOT / "upgrade.sh").read_text(encoding="utf-8")
    assert 'PASTA_TMP=""' in script
    assert "mktemp -d" in script
    assert "chmod 700" in script
    assert "flock -n" in script
    assert 'PASTA_TMP="/tmp/antigravity_upgrade"' not in script


def test_bash_protege_download_e_integridade():
    script = (ROOT / "upgrade.sh").read_text(encoding="utf-8")
    assert "--proto-redir '=https'" in script
    assert "--retry 3" in script
    assert 'ARQUIVO_PARCIAL="${ARQUIVO_TAR}.part"' in script
    assert "sha256sum" in script
    assert "--max-filesize" in script


def test_bash_extrai_em_staging_e_valida_executavel():
    script = (ROOT / "upgrade.sh").read_text(encoding="utf-8")
    assert "validar_pacote_tar" in script
    assert 'STAGING=$(mktemp -d' in script
    assert "--strip-components=1" in script
    assert "EXECUTAVEL_ESPERADO" in script
    assert ".install-manifest.json" in script


def test_bash_ativa_atomicamente_e_possui_healthcheck():
    script = (ROOT / "upgrade.sh").read_text(encoding="utf-8")
    assert "ELECTRON_RUN_AS_NODE=1 timeout 15" in script
    assert "trocar_link_atomico" in script
    assert "mv -Tf" in script
    assert "ativar_versao_atomica" in script
    assert "versão anterior preservada" in script


def test_bash_oferece_operacoes_de_historico():
    script = (ROOT / "upgrade.sh").read_text(encoding="utf-8")
    for comando in ("current", "list", "rollback", "prune"):
        assert comando in script
    assert "rollback_aplicativo" in script
    assert "podar_versoes" in script
