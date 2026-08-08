"""Interface de linha de comando do Antigravity Updater."""

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from . import __version__
from . import core
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
    update.add_argument("--force", "-f", action="store_true", help="reinstalar mesmo na versão atual")

    changelog = subparsers.add_parser("changelog", help="consultar notas oficiais sem exigir root")
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
        "6": ["exit"],
        "7": ["current", "--both"],
        "8": ["list", "--both"],
        "9": ["rollback", "--both"],
        "10": ["prune", "2", "--both"],
    }
    if first in numeric:
        return numeric[first]

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
    normalized = normalize_legacy_args(raw)
    if normalized == ["exit"]:
        return argparse.Namespace(command="exit", target="both")
    return build_parser().parse_args(normalized)


def _selected_apps(target: str) -> List[str]:
    if target == "hub":
        return ["Antigravity"]
    if target == "ide":
        return ["Antigravity_IDE"]
    return ["Antigravity", "Antigravity_IDE"]


def _show_changelog() -> int:
    spinner = core.TerminalSpinner("Buscando changelog oficial")
    spinner.start()
    core.conteudo_changelog = core.fetch_url(core.URL_CHANGELOG)
    if not core.conteudo_changelog:
        spinner.stop(success=False, final_msg="Falha ao buscar o changelog oficial")
        print(f"{core.CLR_BLUE}Consulte: {core.obter_url_changelog('hub')}{core.CLR_RESET}")
        return 1
    spinner.stop(success=True, final_msg="Changelog oficial carregado com sucesso!")
    return 0 if core.consultar_changelog() else 1


def _load_remote_catalog() -> bool:
    spinner = core.TerminalSpinner("Buscando versões e mapeando dependências dinâmicas")
    spinner.start()
    html_content = core.fetch_url("https://antigravity.google/download")
    if not html_content:
        spinner.stop(success=False, final_msg="Falha ao buscar a página de downloads")
        return False
    core.conteudo_total = html_content
    for js in core.re.findall(r'(?:src|href)="([^"]+\.js)"', html_content):
        js_url = js if js.startswith(("http://", "https://")) else f"https://antigravity.google/{js.lstrip('/')}"
        core.conteudo_total += "\n" + core.fetch_url(js_url)
    core.conteudo_changelog = core.fetch_url(core.URL_CHANGELOG)
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


def _run_update(target: str, force: bool, paths: ScopePaths) -> int:
    if not _begin_mutation(paths, needs_temporary=True):
        return 1
    try:
        core.exibir_diagnosticos()
        if not _load_remote_catalog():
            return 1
        results = []
        if target in ("both", "hub"):
            results.append(core.atualizar_aplicativo("Antigravity", "antigravity-hub", "hub", forcar=force))
        if target in ("both", "ide"):
            results.append(core.atualizar_aplicativo("Antigravity_IDE", "stable", "ide", forcar=force))
        success = all(results)
        if success:
            print(f"\n{core.CLR_GREEN}Processo concluído com sucesso!{core.CLR_RESET}")
        else:
            print(f"\n{core.CLR_FAIL}Processo concluído com falhas.{core.CLR_RESET}")
        return core.codigo_saida(success)
    finally:
        core.liberar_recursos()


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


def _interactive_request() -> argparse.Namespace:
    choice = core.menu_selecao()
    mapping = {
        "1": argparse.Namespace(command="update", target="both", force=False),
        "2": argparse.Namespace(command="update", target="hub", force=False),
        "3": argparse.Namespace(command="update", target="ide", force=False),
        "4": argparse.Namespace(command="update", target="both", force=True),
        "5": argparse.Namespace(command="changelog", target="both"),
        "6": argparse.Namespace(command="exit", target="both"),
        "7": argparse.Namespace(command="current", target="both"),
        "8": argparse.Namespace(command="list", target="both"),
        "9": argparse.Namespace(command="rollback", target="both", version=None),
        "10": argparse.Namespace(command="prune", target="both", keep=2),
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
    if namespace.command is None:
        namespace = _interactive_request()
    if namespace.command == "exit":
        print(f"\n{core.CLR_BLUE}Saindo sem realizar alterações.{core.CLR_RESET}\n")
        return 0
    if namespace.command == "changelog":
        return _show_changelog()
    paths = resolve_scope(getattr(namespace, "scope", "system"))
    core.configurar_caminhos(paths.base_dir, paths.lock_file, paths.launcher_dir)
    if namespace.command in ("current", "list"):
        try:
            core.exibir_estado_aplicativos(
                _selected_apps(namespace.target),
                detalhado=namespace.command == "list",
            )
            return 0
        except OSError as error:
            print(f"{core.CLR_FAIL}Erro ao consultar versões: {error}{core.CLR_RESET}")
            return 1
    if namespace.command == "update":
        return _run_update(namespace.target, namespace.force, paths)
    if namespace.command in ("rollback", "prune", "uninstall", "launcher"):
        return _run_mutation(namespace, paths)
    if namespace.command == "systemd":
        return _run_systemd(namespace, paths)
    raise ValueError(f"Comando desconhecido: {namespace.command}")


def main(arguments: Optional[Sequence[str]] = None) -> int:
    return run(parse_args(arguments))


if __name__ == "__main__":
    sys.exit(main())
