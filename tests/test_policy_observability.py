import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from antigravity_updater import cache as cache_module
from antigravity_updater import cli, observability, settings
from antigravity_updater.paths import ScopePaths


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


def test_configuracao_roundtrip_atomico_e_permissoes(tmp_path):
    path = tmp_path / "config" / "config.json"
    configured = settings.Settings(
        channel="preview",
        policy="notify-only",
        retention=4,
        cache_ttl=120,
        notifications="auto",
        log_level="DEBUG",
        pin_hub="2.3.4-beta1",
    )

    settings.save(path, configured)

    assert settings.load(path) == configured
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(path.parent.glob("*.tmp-*"))


def test_configuracao_global_pode_ser_consultada_sem_root(tmp_path):
    path = tmp_path / "etc" / "config.json"

    settings.save(path, settings.Settings(), mode=0o644, directory_mode=0o755)

    assert stat.S_IMODE(path.stat().st_mode) == 0o644
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o755


@pytest.mark.parametrize(
    "data",
    [
        {"unknown": True},
        {"channel": "nightly"},
        {"retention": 0},
        {"retention": True},
        {"cache_ttl": 604801},
        {"pin_ide": "../../escape"},
    ],
)
def test_configuracao_rejeita_valores_invalidos(data):
    with pytest.raises(ValueError):
        settings.from_dict(data)


def test_config_set_converte_tipos_e_remove_pin():
    current = settings.Settings(pin_hub="1.0.0")

    assert settings.with_value(current, "retention", "5").retention == 5
    assert settings.with_value(current, "log_level", "debug").log_level == "DEBUG"
    assert settings.with_value(current, "pin_hub", "none").pin_hub is None


def test_cache_hit_e_fallback_stale(monkeypatch, tmp_path):
    now = [100.0]
    monkeypatch.setattr(cache_module.time, "time", lambda: now[0])
    cache = cache_module.TextCache(tmp_path / "cache", ttl=10)
    calls = []

    first = cache.fetch("https://example.com/data", lambda url: calls.append(url) or "conteudo")
    second = cache.fetch("https://example.com/data", lambda _url: pytest.fail("não deveria buscar"))
    now[0] = 200.0
    stale = cache.fetch("https://example.com/data", lambda _url: "")

    assert first.status == "miss"
    assert second.status == "hit"
    assert stale == cache_module.CacheResult("conteudo", "stale")
    assert calls == ["https://example.com/data"]
    assert stat.S_IMODE(cache.directory.stat().st_mode) == 0o700


def test_cache_clear_recusa_diretorio_simbolico(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "cache"
    linked.symlink_to(real)

    with pytest.raises(ValueError, match="inseguro"):
        cache_module.TextCache(linked, ttl=10).clear()


def test_cache_ttl_zero_desabilita_leitura_e_escrita(tmp_path):
    cache = cache_module.TextCache(tmp_path / "cache", ttl=0)

    result = cache.fetch("https://example.com", lambda _url: "direto")

    assert result == cache_module.CacheResult("direto", "disabled")
    assert not cache.directory.exists()


def test_selecao_de_canal_e_versao_fixada(updater_module):
    stable = "https://example.com/antigravity-hub/2.0.0/linux-x64/app.tar.gz"
    preview = "https://example.com/antigravity-hub/2.1.0-beta1/linux-x64/app.tar.gz"
    older = "https://example.com/antigravity-hub/1.9.0/linux-x64/app.tar.gz"
    content = "\n".join((stable, preview, older))

    assert updater_module.selecionar_url_download(content, "antigravity-hub", "linux-x64") == stable
    assert (
        updater_module.selecionar_url_download(content, "antigravity-hub", "linux-x64", "preview")
        == preview
    )
    assert (
        updater_module.selecionar_url_download(
            content,
            "antigravity-hub",
            "linux-x64",
            "stable",
            "1.9.0",
        )
        == older
    )


def test_politica_ordena_naturalmente_release_candidates(updater_module):
    rc2 = "https://example.com/antigravity-hub/3.0.0-rc2/linux-x64/app.tar.gz"
    rc10 = "https://example.com/antigravity-hub/3.0.0-rc10/linux-x64/app.tar.gz"
    release = "https://example.com/antigravity-hub/3.0.0/linux-x64/app.tar.gz"

    assert (
        updater_module.selecionar_url_download("\n".join((rc2, rc10)), "antigravity-hub", "linux-x64", "preview")
        == rc10
    )
    assert updater_module.chave_versao("3.0.0") > updater_module.chave_versao("3.0.0-rc10")
    assert (
        updater_module.selecionar_url_download("\n".join((rc10, release)), "antigravity-hub", "linux-x64", "preview")
        == release
    )


def test_notify_only_nao_modifica_instalacao(updater_module, monkeypatch, tmp_path):
    url = "https://example.com/antigravity-hub/2.0.0/linux-x64/app.tar.gz"
    updater_module.conteudo_total = url
    monkeypatch.setattr(updater_module, "DIRETORIO_BASE", str(tmp_path / "apps"))
    monkeypatch.setattr(updater_module, "obter_data_servidor", lambda _url: None)
    monkeypatch.setattr(updater_module, "exibir_notas_versao", lambda *_args: None)
    monkeypatch.setattr(updater_module, "download_com_progresso", pytest.fail)
    monkeypatch.setattr(updater_module, "criar_atalho", pytest.fail)

    assert updater_module.atualizar_aplicativo(
        "Antigravity",
        "antigravity-hub",
        "hub",
        politica="notify-only",
    )


def test_log_json_privado(tmp_path):
    log_file = tmp_path / "state" / "logs" / "updater.jsonl"
    logger = observability.configure(log_file, "INFO")
    observability.event(logger, "test_event", scope="user", success=True)
    for handler in logger.handlers:
        handler.flush()

    entry = json.loads(log_file.read_text(encoding="utf-8"))
    assert entry["event"] == "test_event"
    assert entry["scope"] == "user"
    assert entry["success"] is True
    assert stat.S_IMODE(log_file.stat().st_mode) == 0o600


def test_notificacao_usa_argumentos_sem_shell(monkeypatch):
    calls = []
    monkeypatch.setattr(observability.shutil, "which", lambda _name: "/usr/bin/notify-send")
    monkeypatch.setenv("DISPLAY", ":0")

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(observability.subprocess, "run", run)

    assert observability.notify("auto", "Título", "mensagem; $(comando)")
    assert calls[0][0][-1] == "mensagem; $(comando)"
    assert "shell" not in calls[0][1]


def test_cli_config_usuario_nao_exige_root(monkeypatch, tmp_path, capsys):
    paths = _user_paths(tmp_path)
    monkeypatch.setattr(cli, "resolve_scope", lambda _scope: paths)
    monkeypatch.setattr(cli.core, "verificar_privilegios", pytest.fail)

    assert cli.main(["config", "set", "retention", "5", "--user"]) == 0
    assert settings.load(paths.config_file).retention == 5
    assert "retention=5" in capsys.readouterr().out


def test_cli_check_forca_politica_sem_mutacao(monkeypatch, tmp_path):
    paths = _user_paths(tmp_path)
    observed = []
    monkeypatch.setattr(cli, "resolve_scope", lambda _scope: paths)
    monkeypatch.setattr(cli, "_load_remote_catalog", lambda *_args: True)
    monkeypatch.setattr(
        cli,
        "_process_remote_apps",
        lambda target, configured, **_kwargs: observed.append((target, configured)) or [True],
    )
    monkeypatch.setattr(cli.core, "verificar_privilegios", pytest.fail)

    assert cli.main(["check", "--hub", "--user", "--channel", "preview"]) == 0
    assert observed[0][0] == "hub"
    assert observed[0][1].channel == "preview"
    assert observed[0][1].policy == "notify-only"
