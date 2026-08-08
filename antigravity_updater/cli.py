"""Interface de linha de comando do Antigravity Updater."""

import argparse
import json
import os
import shutil
import sys
from collections import deque
from dataclasses import replace
from pathlib import Path
from typing import List, Optional, Sequence

from . import __version__
from . import cache as cache_module
from . import core
from . import observability
from . import settings as settings_module
from . import systemd as systemd_integration
from .paths import ScopePaths, resolve_scope


TARGET_NAMES = {
    "hub": "--hub",
    "antigravity": "--hub",
    "ide": "--ide",
    "antigravity-ide": "--ide",
}


def _add_targets(parser: argparse.ArgumentParser) -> None:
    targets = parser.add_mutually_exclusive_group()
    targets.add_argument("--hub", action="store_const", const="hub", dest="target", help="somente o Hub")
    targets.add_argument("--ide", action="store_const", const="ide", dest="target", help="somente o IDE")
    targets.add_argument("--both", action="store_const", const="both", dest="target", help="ambos (padrão)")
    parser.set_defaults(target="both")


def _add_scope(parser: argparse.ArgumentParser) -> None:
    scopes = parser.add_mutually_exclusive_group()
    scopes.add_argument("--user", action="store_const", const="user", dest="scope", help="instalação do usuário")
    scopes.add_argument("--system", action="store_const", const="system", dest="scope", help="instalação do sistema")
    parser.set_defaults(scope="system")


def _add_channel(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--channel", choices=("stable", "preview"), help="sobrescrever o canal configurado")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="antigravity-upgrade",
        description="Instala, consulta e gerencia versões do Antigravity no Linux.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="COMANDO")

    update = subparsers.add_parser("update", help="instalar ou atualizar aplicativos")
    _add_targets(update)
    _add_scope(update)
    _add_channel(update)
    update.add_argument("--force", "-f", action="store_true", help="reinstalar mesmo na versão atual")
    update.add_argument("--policy", choices=("latest", "notify-only"), help="sobrescrever a política configurada")

    check = subparsers.add_parser("check", help="verificar atualizações sem alterar a instalação")
    _add_targets(check)
    _add_scope(check)
    _add_channel(check)

    changelog = subparsers.add_parser("changelog", help="consultar notas oficiais sem exigir root")
    _add_scope(changelog)
    changelog.set_defaults(target="both")

    current = subparsers.add_parser("current", help="mostrar versões ativas sem exigir root")
    _add_targets(current)
    _add_scope(current)

    history = subparsers.add_parser("list", help="listar versões instaladas sem exigir root")
    _add_targets(history)
    _add_scope(history)

    rollback = subparsers.add_parser("rollback", help="ativar uma versão anterior")
    _add_targets(rollback)
    _add_scope(rollback)
    rollback.add_argument("version", nargs="?", help="versão específica; requer --hub ou --ide")

    prune = subparsers.add_parser("prune", help="remover versões antigas")
    _add_targets(prune)
    _add_scope(prune)
    prune.add_argument("keep", nargs="?", type=int, default=2, help="quantidade mínima a manter (padrão: 2)")

    uninstall = subparsers.add_parser("uninstall", help="remover aplicativos e seu histórico gerenciado")
    _add_targets(uninstall)
    _add_scope(uninstall)
    uninstall.add_argument(
        "--keep-systemd",
        action="store_true",
        help="não remover o timer ao desinstalar ambos",
    )

    launcher = subparsers.add_parser("launcher", help="instalar ou remover launchers XDG")
    launcher.add_argument("action", choices=("install", "remove"), help="ação sobre os launchers")
    _add_targets(launcher)
    _add_scope(launcher)

    systemd = subparsers.add_parser("systemd", help="gerenciar o serviço e timer systemd")
    systemd.add_argument("action", choices=("install", "remove", "status"), help="ação sobre as unidades")
    _add_scope(systemd)
    systemd.add_argument("--calendar", default="daily", help="expressão OnCalendar usada na instalação")

    config = subparsers.add_parser("config", help="consultar ou alterar a configuração")
    config.add_argument("action", choices=("show", "path", "set", "reset"))
    config.add_argument("key", nargs="?")
    config.add_argument("value", nargs="?")
    _add_scope(config)

    cache = subparsers.add_parser("cache", help="consultar ou limpar o cache HTTP")
    cache.add_argument("action", choices=("status", "clear"))
    _add_scope(cache)

    logs = subparsers.add_parser("logs", help="mostrar eventos recentes do log estruturado")
    logs.add_argument("--tail", type=int, default=20, help="quantidade de eventos (padrão: 20)")
    _add_scope(logs)
    return parser


def _clean(value: str) -> str:
    return value.lower().lstrip("-")


def normalize_legacy_args(arguments: Sequence[str]) -> List[str]:
    """Converte a sintaxe histórica para os subcomandos atuais."""
    args = list(arguments)
    if not args:
        return args

    cleaned = [_clean(item) for item in args]
    first = cleaned[0]
    management = next((item for item in cleaned if item in ("current", "list", "rollback", "prune")), None)
    if management:
        result = [management]
        for item, normalized in zip(args, cleaned):
            if normalized == management:
                continue
            target = TARGET_NAMES.get(normalized)
            result.append(target if target else item)
        return result

    numeric = {
        "1": ["update", "--both"],
        "2": ["update", "--hub"],
        "3": ["update", "--ide"],
        "4": ["update", "--both", "--force"],
        "5": ["changelog"],
        "6": ["check", "--both"],
        "7": ["current", "--both"],
        "8": ["list", "--both"],
        "9": ["rollback", "--both"],
        "10": ["prune", "2", "--both"],
        "11": ["config", "show"],
        "12": ["cache", "status"],
        "13": ["logs"],
        "14": ["launcher", "install", "--both"],
        "15": ["systemd", "status"],
        "16": ["uninstall", "--both"],
        "17": ["exit"],
    }
    if first in numeric:
        result = numeric[first]
        if result[0] != "exit":
            result += [item for item, normalized in zip(args[1:], cleaned[1:]) if normalized in ("user", "system")]
        return result

    if first in ("user", "system") and len(args) > 1:
        normalized_args = normalize_legacy_args(args[1:])
        return normalized_args + [args[0]]

    aliases = {
        "both": ["update", "--both"],
        "all": ["update", "--both"],
        "hub": ["update", "--hub"],
        "antigravity": ["update", "--hub"],
        "ide": ["update", "--ide"],
        "antigravity-ide": ["update", "--ide"],
        "reinstall": ["update", "--both", "--force"],
        "force": ["update", "--both", "--force"],
        "f": ["update", "--both", "--force"],
        "changelog": ["changelog"],
        "changes": ["changelog"],
        "release-notes": ["changelog"],
        "exit": ["exit"],
        "quit": ["exit"],
    }
    if first in aliases:
        result = aliases[first]
        if result[0] == "update" and "force" in cleaned[1:] and "--force" not in result:
            result = result + ["--force"]
        result += [item for item, normalized in zip(args[1:], cleaned[1:]) if normalized in ("user", "system")]
        return result

    return args


def parse_args(arguments: Optional[Sequence[str]] = None) -> argparse.Namespace:
    raw = sys.argv[1:] if arguments is None else arguments
    if list(raw) in (["--user"], ["--system"]):
        return argparse.Namespace(command=None, scope=_clean(raw[0]))
    normalized = normalize_legacy_args(raw)
    if normalized and normalized[0] == "exit":
        return argparse.Namespace(command="exit", target="both")
    return build_parser().parse_args(normalized)


def _selected_apps(target: str) -> List[str]:
    if target == "hub":
        return ["Antigravity"]
    if target == "ide":
        return ["Antigravity_IDE"]
    return ["Antigravity", "Antigravity_IDE"]


def _cached_fetch(cache: cache_module.TextCache, url: str, logger) -> str:
    result = cache.fetch(url, core.fetch_url)
    observability.event(logger, "cache_fetch", url=url, status=result.status)
    return result.text


def _show_changelog(cache: cache_module.TextCache, logger) -> int:
    spinner = core.TerminalSpinner("Buscando changelog oficial")
    spinner.start()
    core.conteudo_changelog = _cached_fetch(cache, core.URL_CHANGELOG, logger)
    if not core.conteudo_changelog:
        spinner.stop(success=False, final_msg="Falha ao buscar o changelog oficial")
        print(f"{core.CLR_BLUE}Consulte: {core.obter_url_changelog('hub')}{core.CLR_RESET}")
        return 1
    spinner.stop(success=True, final_msg="Changelog oficial carregado com sucesso!")
    return 0 if core.consultar_changelog() else 1


def _load_remote_catalog(cache: cache_module.TextCache, logger) -> bool:
    spinner = core.TerminalSpinner("Buscando versões e mapeando dependências dinâmicas")
    spinner.start()
    html_content = _cached_fetch(cache, "https://antigravity.google/download", logger)
    if not html_content:
        spinner.stop(success=False, final_msg="Falha ao buscar a página de downloads")
        return False
    core.conteudo_total = html_content
    for js in core.re.findall(r'(?:src|href)="([^"]+\.js)"', html_content):
        js_url = js if js.startswith(("http://", "https://")) else f"https://antigravity.google/{js.lstrip('/')}"
        core.conteudo_total += "\n" + _cached_fetch(cache, js_url, logger)
    core.conteudo_changelog = _cached_fetch(cache, core.URL_CHANGELOG, logger)
    spinner.stop(success=True, final_msg="Versões, links e changelog carregados com sucesso!")
    return True


def _prepare_user_lock(paths: ScopePaths) -> None:
    parent = paths.lock_file.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if parent.is_symlink() or parent.stat().st_uid != os.geteuid():
        raise RuntimeError(f"Diretório de lock inseguro: {parent}")
    parent.chmod(0o700)


def _begin_mutation(paths: ScopePaths, needs_temporary: bool = False) -> bool:
    if paths.requires_root:
        core.verificar_privilegios()
    try:
        if paths.scope == "user":
            _prepare_user_lock(paths)
        core.adquirir_bloqueio()
        if needs_temporary:
            core.preparar_diretorios()
    except (OSError, RuntimeError) as error:
        print(f"{core.CLR_FAIL}{error}{core.CLR_RESET}")
        core.liberar_recursos()
        return False
    return True


def _settings_for_command(namespace: argparse.Namespace, configured: settings_module.Settings):
    updates = {}
    if getattr(namespace, "channel", None):
        updates["channel"] = namespace.channel
    if getattr(namespace, "policy", None):
        updates["policy"] = namespace.policy
    return settings_module.validate(replace(configured, **updates))


def _process_remote_apps(target: str, configured: settings_module.Settings, force: bool = False):
    results = []
    if target in ("both", "hub"):
        results.append(
            core.atualizar_aplicativo(
                "Antigravity",
                "antigravity-hub",
                "hub",
                forcar=force,
                canal=configured.channel,
                politica=configured.policy,
                versao_fixada=configured.pin_hub,
            )
        )
    if target in ("both", "ide"):
        results.append(
            core.atualizar_aplicativo(
                "Antigravity_IDE",
                "stable",
                "ide",
                forcar=force,
                canal=configured.channel,
                politica=configured.policy,
                versao_fixada=configured.pin_ide,
            )
        )
    return results


def _run_update(
    target: str,
    force: bool,
    paths: ScopePaths,
    configured: settings_module.Settings,
    cache: cache_module.TextCache,
    logger,
    show_diagnostics: bool = True,
) -> int:
    if not _begin_mutation(paths, needs_temporary=True):
        return 1
    try:
        if show_diagnostics:
            core.exibir_diagnosticos()
        if not _load_remote_catalog(cache, logger):
            return 1
        results = _process_remote_apps(target, configured, force=force)
        success = all(results)
        if success:
            for app in _selected_apps(target):
                core.podar_versoes(app, configured.retention)
        if success:
            print(f"\n{core.CLR_GREEN}Processo concluído com sucesso!{core.CLR_RESET}")
        else:
            print(f"\n{core.CLR_FAIL}Processo concluído com falhas.{core.CLR_RESET}")
        observability.event(
            logger,
            "update_completed",
            success=success,
            scope=paths.scope,
            channel=configured.channel,
            policy=configured.policy,
        )
        observability.notify(
            configured.notifications,
            "Antigravity Updater",
            "Atualização concluída." if success else "A atualização terminou com falhas.",
        )
        return core.codigo_saida(success)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"{core.CLR_FAIL}Erro durante a atualização: {error}{core.CLR_RESET}")
        observability.event(logger, "update_failed", scope=paths.scope, error=str(error))
        observability.notify(
            configured.notifications,
            "Antigravity Updater",
            "A atualização terminou com falhas.",
        )
        return 1
    finally:
        core.liberar_recursos()


def _run_check(
    target: str,
    configured: settings_module.Settings,
    cache: cache_module.TextCache,
    logger,
) -> int:
    checking = replace(configured, policy="notify-only")
    if not _load_remote_catalog(cache, logger):
        return 1
    success = all(_process_remote_apps(target, checking))
    observability.event(logger, "check_completed", success=success, channel=checking.channel)
    observability.notify(
        checking.notifications,
        "Antigravity Updater",
        "Verificação de versões concluída." if success else "A verificação de versões falhou.",
    )
    return core.codigo_saida(success)


def _run_mutation(namespace: argparse.Namespace, paths: ScopePaths) -> int:
    if not _begin_mutation(paths):
        return 1
    try:
        apps = _selected_apps(namespace.target)
        if namespace.command == "rollback":
            version = namespace.version
            if version and len(apps) != 1:
                raise ValueError("Informe --hub ou --ide ao solicitar uma versão específica.")
            for app in apps:
                selected, runtime = core.rollback_aplicativo(app, version)
                print(f"{core.CLR_GREEN}✓ {app} revertido para {selected} ({runtime}).{core.CLR_RESET}")
        elif namespace.command == "prune":
            if namespace.keep < 1:
                raise ValueError("A retenção precisa ser pelo menos 1.")
            for app in apps:
                removed = core.podar_versoes(app, namespace.keep)
                summary = ", ".join(removed) if removed else "nenhuma"
                print(f"{app}: versões removidas: {summary}")
        elif namespace.command == "uninstall":
            for app in apps:
                changed = core.desinstalar_aplicativo(app)
                status = "removido" if changed else "não estava instalado"
                print(f"{app}: {status}")
            if namespace.target == "both" and not namespace.keep_systemd:
                unit_files = (
                    paths.unit_dir / systemd_integration.SERVICE_NAME,
                    paths.unit_dir / systemd_integration.TIMER_NAME,
                )
                if any(candidate.exists() or candidate.is_symlink() for candidate in unit_files):
                    systemd_integration.remove_units(paths)
                    print(f"Timer systemd removido do escopo {paths.scope}.")
        elif namespace.command == "launcher":
            for app in apps:
                if namespace.action == "install":
                    if not core.criar_atalho(app):
                        raise ValueError(f"Não existe uma instalação ativa de {app}.")
                    print(f"{app}: launcher instalado")
                else:
                    changed = core.remover_atalho(app)
                    status = "launcher removido" if changed else "launcher inexistente"
                    print(f"{app}: {status}")
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"{core.CLR_FAIL}Erro: {error}{core.CLR_RESET}")
        return 1
    finally:
        core.liberar_recursos()


def _run_config(namespace: argparse.Namespace, paths: ScopePaths) -> int:
    if namespace.action != "set" and (namespace.key is not None or namespace.value is not None):
        print(f"{core.CLR_FAIL}Erro: {namespace.action} não aceita KEY ou VALUE.{core.CLR_RESET}")
        return 1
    if namespace.action == "path":
        print(paths.config_file)
        return 0
    if namespace.action == "show":
        try:
            current = settings_module.load(paths.config_file)
        except ValueError as error:
            print(f"{core.CLR_FAIL}Erro: {error}{core.CLR_RESET}")
            return 1
        print(json.dumps(settings_module.public_dict(current), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if not _begin_mutation(paths):
        return 1
    try:
        if namespace.action == "reset":
            if paths.config_file.is_dir() and not paths.config_file.is_symlink():
                raise ValueError(f"O caminho de configuração não é um arquivo: {paths.config_file}")
            if paths.config_file.exists() or paths.config_file.is_symlink():
                paths.config_file.unlink()
            print("Configuração restaurada para os padrões.")
            return 0
        if not namespace.key or namespace.value is None:
            raise ValueError("config set exige KEY e VALUE.")
        current = settings_module.load(paths.config_file)
        updated = settings_module.with_value(current, namespace.key, namespace.value)
        settings_module.save(
            paths.config_file,
            updated,
            mode=0o644 if paths.scope == "system" else 0o600,
            directory_mode=0o755 if paths.scope == "system" else 0o700,
        )
        print(f"{namespace.key}={settings_module.public_dict(updated)[namespace.key]}")
        return 0
    except (OSError, ValueError) as error:
        print(f"{core.CLR_FAIL}Erro: {error}{core.CLR_RESET}")
        return 1
    finally:
        core.liberar_recursos()


def _run_cache(namespace: argparse.Namespace, paths: ScopePaths, cache: cache_module.TextCache) -> int:
    if namespace.action == "status":
        stats = cache.stats()
        print(json.dumps({"path": str(paths.cache_dir), **stats}, ensure_ascii=False, sort_keys=True))
        return 0
    if not _begin_mutation(paths):
        return 1
    try:
        removed = cache.clear()
        print(f"Cache limpo: {removed} arquivo(s) removido(s).")
        return 0
    except (OSError, ValueError) as error:
        print(f"{core.CLR_FAIL}Erro: {error}{core.CLR_RESET}")
        return 1
    finally:
        core.liberar_recursos()


def _show_logs(namespace: argparse.Namespace, paths: ScopePaths) -> int:
    if namespace.tail < 1 or namespace.tail > 1000:
        print(f"{core.CLR_FAIL}Erro: --tail precisa estar entre 1 e 1000.{core.CLR_RESET}")
        return 1
    try:
        if paths.log_file.is_symlink() or not paths.log_file.is_file():
            print("Nenhum evento registrado.")
            return 0
        with paths.log_file.open("r", encoding="utf-8") as handle:
            for line in deque(handle, maxlen=namespace.tail):
                print(line, end="")
        return 0
    except OSError as error:
        print(f"{core.CLR_FAIL}Erro ao ler logs: {error}{core.CLR_RESET}")
        return 1


def _interactive_request(scope="system") -> argparse.Namespace:
    choice = core.menu_selecao(scope)
    mapping = {
        "1": argparse.Namespace(command="update", target="both", force=False, scope=scope),
        "2": argparse.Namespace(command="update", target="hub", force=False, scope=scope),
        "3": argparse.Namespace(command="update", target="ide", force=False, scope=scope),
        "4": argparse.Namespace(command="update", target="both", force=True, scope=scope),
        "5": argparse.Namespace(command="changelog", target="both", scope=scope),
        "6": argparse.Namespace(command="check", target="both", scope=scope),
        "7": argparse.Namespace(command="current", target="both", scope=scope),
        "8": argparse.Namespace(command="list", target="both", scope=scope),
        "9": argparse.Namespace(command="rollback", target="both", version=None, scope=scope),
        "10": argparse.Namespace(command="prune", target="both", keep=2, scope=scope),
        "11": argparse.Namespace(command="config", action="show", key=None, value=None, scope=scope),
        "12": argparse.Namespace(command="cache", action="status", scope=scope),
        "13": argparse.Namespace(command="logs", tail=20, scope=scope),
        "14": argparse.Namespace(command="launcher", action="install", target="both", scope=scope),
        "15": argparse.Namespace(command="systemd", action="status", calendar="daily", scope=scope),
        "16": argparse.Namespace(
            command="uninstall",
            target="both",
            keep_systemd=False,
            confirm=True,
            scope=scope,
        ),
        "17": argparse.Namespace(command="exit", target="both", scope=scope),
    }
    return mapping[choice]


def _run_systemd(namespace: argparse.Namespace, paths: ScopePaths) -> int:
    if namespace.action == "status":
        return systemd_integration.show_status(paths)
    if not _begin_mutation(paths):
        return 1
    try:
        entrypoint = Path(sys.argv[0]).resolve()
        if entrypoint.name == "cli.py":
            repository_entrypoint = Path(__file__).resolve().parents[1] / "upgrade.py"
            installed_entrypoint = shutil.which("antigravity-upgrade")
            if repository_entrypoint.is_file():
                entrypoint = repository_entrypoint
            elif installed_entrypoint:
                entrypoint = Path(installed_entrypoint).resolve()
        if not entrypoint.is_file():
            raise RuntimeError("Não foi possível identificar a entrada executável da CLI.")
        if namespace.action == "install":
            systemd_integration.install_units(paths, Path(sys.executable), entrypoint, namespace.calendar)
            print(f"Timer systemd instalado no escopo {paths.scope}.")
        else:
            systemd_integration.remove_units(paths)
            print(f"Timer systemd removido do escopo {paths.scope}.")
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"{core.CLR_FAIL}Erro: {error}{core.CLR_RESET}")
        return 1
    finally:
        core.liberar_recursos()


def run(namespace: argparse.Namespace) -> int:
    diagnostics_shown = False
    if namespace.command is None:
        core.exibir_diagnosticos()
        diagnostics_shown = True
        namespace = _interactive_request(getattr(namespace, "scope", "system"))
    if namespace.command == "exit":
        print(f"\n{core.CLR_BLUE}Saindo sem realizar alterações.{core.CLR_RESET}\n")
        return 0
    if namespace.command == "uninstall" and getattr(namespace, "confirm", False):
        confirmation = input("Digite REMOVER para confirmar a desinstalação de ambos: ").strip()
        if confirmation != "REMOVER":
            print("Desinstalação cancelada.")
            return 0
    paths = resolve_scope(getattr(namespace, "scope", "system"))
    core.configurar_caminhos(paths.base_dir, paths.lock_file, paths.launcher_dir)
    if namespace.command == "config":
        logger = observability.configure(paths.log_file, "INFO")
        observability.event(logger, "command_started", command="config", scope=paths.scope)
        result = _run_config(namespace, paths)
        observability.event(
            logger,
            "command_finished",
            command="config",
            scope=paths.scope,
            exit_code=result,
        )
        return result
    try:
        configured = settings_module.load(paths.config_file)
        configured = _settings_for_command(namespace, configured)
    except ValueError as error:
        print(f"{core.CLR_FAIL}Erro na configuração: {error}{core.CLR_RESET}")
        return 1
    logger = observability.configure(paths.log_file, configured.log_level)
    observability.event(logger, "command_started", command=namespace.command, scope=paths.scope)
    cache = cache_module.TextCache(paths.cache_dir, configured.cache_ttl)

    def finish(code: int) -> int:
        observability.event(
            logger,
            "command_finished",
            command=namespace.command,
            scope=paths.scope,
            exit_code=code,
        )
        return code

    if namespace.command == "changelog":
        return finish(_show_changelog(cache, logger))
    if namespace.command == "cache":
        return finish(_run_cache(namespace, paths, cache))
    if namespace.command == "logs":
        return finish(_show_logs(namespace, paths))
    if namespace.command in ("current", "list"):
        try:
            core.exibir_estado_aplicativos(
                _selected_apps(namespace.target),
                detalhado=namespace.command == "list",
            )
            return finish(0)
        except OSError as error:
            print(f"{core.CLR_FAIL}Erro ao consultar versões: {error}{core.CLR_RESET}")
            return finish(1)
    if namespace.command == "check":
        return finish(_run_check(namespace.target, configured, cache, logger))
    if namespace.command == "update":
        if configured.policy == "notify-only":
            return finish(_run_check(namespace.target, configured, cache, logger))
        return finish(
            _run_update(
                namespace.target,
                namespace.force,
                paths,
                configured,
                cache,
                logger,
                show_diagnostics=not diagnostics_shown,
            )
        )
    if namespace.command in ("rollback", "prune", "uninstall", "launcher"):
        return finish(_run_mutation(namespace, paths))
    if namespace.command == "systemd":
        return finish(_run_systemd(namespace, paths))
    raise ValueError(f"Comando desconhecido: {namespace.command}")


def main(arguments: Optional[Sequence[str]] = None) -> int:
    return run(parse_args(arguments))


if __name__ == "__main__":
    sys.exit(main())
