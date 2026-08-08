#!/usr/bin/env python3
import os
import sys
import platform
import atexit
import fcntl
import hashlib
import json
import posixpath
import tempfile
import urllib.request
import urllib.error
import urllib.parse
import gzip
import re
import shutil
import stat
import subprocess
import tarfile
import inspect
import html
import time
import threading
import email.utils
from datetime import datetime

# Cores ANSI para a interface
CLR_RESET = "\033[0m"
CLR_HEADER = "\033[95m"
CLR_BLUE = "\033[94m"
CLR_CYAN = "\033[96m"
CLR_GREEN = "\033[92m"
CLR_WARNING = "\033[93m"
CLR_FAIL = "\033[91m"
CLR_GRAY = "\033[90m"
CLR_WHITE = "\033[37m"

# Diretório base de instalação
DIRETORIO_BASE = "/opt/antigravity_apps"
PASTA_TMP = None
ARQUIVO_LOCK = "/run/lock/antigravity-updater.lock"
URL_CHANGELOG = "https://antigravity.google/changelog"
HTTP_TIMEOUT = 30
HTTP_RETRIES = 3
HEALTHCHECK_TIMEOUT = 15
MAX_DOWNLOAD_BYTES = 4 * 1024 * 1024 * 1024
MAX_EXTRACTED_BYTES = 12 * 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 200_000
LOCK_HANDLE = None

def verificar_privilegios():
    """Interrompe a execução quando o instalador não possui privilégios."""
    if os.geteuid() == 0:
        return
    print(f"{CLR_FAIL}Erro: Este script precisa ser executado com privilégios de administrador (root/sudo).{CLR_RESET}")
    print(f"{CLR_WARNING}Por favor, execute novamente usando: sudo {sys.executable or 'python3'} {os.path.abspath(sys.argv[0])}{CLR_RESET}\n")
    raise SystemExit(1)

# Variável para acumular o conteúdo HTML + JS raspado da web
conteudo_total = ""
conteudo_changelog = ""

# Detecta automaticamente a arquitetura do Ubuntu do usuário
def detectar_arquitetura(arquitetura):
    """Converte a arquitetura do sistema no identificador usado nos downloads."""
    if arquitetura == "x86_64":
        return "linux-x64"
    if arquitetura in ("aarch64", "arm64"):
        return "linux-arm"
    raise ValueError(f"Arquitetura não suportada: {arquitetura}")


ARCH_ALVO = detectar_arquitetura(platform.machine())


def preparar_diretorios(diretorio_temporario=None):
    """Cria uma sessão temporária privada para a execução atual."""
    global PASTA_TMP
    os.makedirs(DIRETORIO_BASE, exist_ok=True)
    PASTA_TMP = tempfile.mkdtemp(prefix="antigravity-upgrade-", dir=diretorio_temporario)
    os.chmod(PASTA_TMP, 0o700)
    return PASTA_TMP


def limpar_diretorio_temporario():
    global PASTA_TMP
    if PASTA_TMP and os.path.isdir(PASTA_TMP):
        shutil.rmtree(PASTA_TMP, ignore_errors=True)
    PASTA_TMP = None


def adquirir_bloqueio(caminho=ARQUIVO_LOCK):
    """Mantém um lock exclusivo enquanto o processo estiver em execução."""
    global LOCK_HANDLE
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(caminho, flags, 0o600)
    os.fchmod(fd, 0o600)
    handle = os.fdopen(fd, "a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise RuntimeError("Outra atualização do Antigravity já está em execução.")
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    LOCK_HANDLE = handle
    return handle


def liberar_bloqueio():
    global LOCK_HANDLE
    if LOCK_HANDLE is not None:
        fcntl.flock(LOCK_HANDLE.fileno(), fcntl.LOCK_UN)
        LOCK_HANDLE.close()
        LOCK_HANDLE = None


def liberar_recursos():
    limpar_diretorio_temporario()
    liberar_bloqueio()


def codigo_saida(sucesso):
    """Traduz o resultado agregado para o contrato de processos Unix."""
    return 0 if sucesso else 1

# Classe para spinner animado
class TerminalSpinner:
    def __init__(self, message="Processando"):
        self.message = message
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.stop_running = threading.Event()
        self.thread = None

    def _spin(self):
        idx = 0
        while not self.stop_running.is_set():
            sys.stdout.write(f"\r{CLR_CYAN}{self.spinner_chars[idx]} {self.message}...{CLR_RESET}")
            sys.stdout.flush()
            idx = (idx + 1) % len(self.spinner_chars)
            time.sleep(0.08)

    def start(self):
        self.stop_running.clear()
        self.thread = threading.Thread(target=self._spin)
        self.thread.daemon = True
        self.thread.start()

    def stop(self, success=True, final_msg=None):
        self.stop_running.set()
        if self.thread:
            self.thread.join()
        sys.stdout.write("\r\033[2K")  # Limpa a linha atual
        if final_msg is None:
            final_msg = self.message
        if success:
            sys.stdout.write(f"{CLR_GREEN}✓ {final_msg}{CLR_RESET}\n")
        else:
            sys.stdout.write(f"{CLR_FAIL}✗ {final_msg}{CLR_RESET}\n")
        sys.stdout.flush()

# Exibe diagnósticos de hardware e do sistema
def exibir_diagnosticos():
    # Coleta de dados
    os_info = f"{platform.system()} {platform.release()}"
    arch_info = ARCH_ALVO
    
    cpu_cores = os.cpu_count() or "N/A"
    cpu_name = "Desconhecido"
    if os.path.exists("/proc/cpuinfo"):
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        cpu_name = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass
    cpu_info = f"{cpu_name} ({cpu_cores} threads)"
    
    mem_total, mem_avail = "N/A", "N/A"
    if os.path.exists("/proc/meminfo"):
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if "MemTotal" in line:
                        mem_total = int(line.split()[1]) // 1024
                    elif "MemAvailable" in line:
                        mem_avail = int(line.split()[1]) // 1024
        except Exception:
            pass
    if mem_total != "N/A" and mem_avail != "N/A":
        mem_used = mem_total - mem_avail
        mem_info = f"Uso: {mem_used}MB / Total: {mem_total}MB"
    else:
        mem_info = "N/A"

    disk_info = "N/A"
    try:
        usage = shutil.disk_usage(DIRETORIO_BASE)
        disponivel_gb = usage.free / 1024 / 1024 / 1024
        total_gb = usage.total / 1024 / 1024 / 1024
        disk_info = f"Disponível: {disponivel_gb:.2f} GB / Total: {total_gb:.2f} GB"
    except Exception:
        pass

    largura_total = 78
    
    print(f"\n{CLR_HEADER}╔{'═' * largura_total}╗{CLR_RESET}")
    titulo = "DIAGNÓSTICOS DO SISTEMA"
    espaco_titulo = (largura_total - len(titulo)) // 2
    rem_titulo = largura_total - len(titulo) - espaco_titulo
    print(f"{CLR_HEADER}║{' ' * espaco_titulo}{titulo}{' ' * rem_titulo}║{CLR_RESET}")
    print(f"{CLR_HEADER}╠{'═' * largura_total}╣{CLR_RESET}")
    
    def print_linha_tabela(label, valor, clr_valor=CLR_WHITE):
        label_str = f" {label}:"
        col1_len = 24
        raw_linha_esq = f"{label_str:<{col1_len}}"
        
        max_val_len = largura_total - col1_len - 2
        if len(valor) > max_val_len:
            valor = valor[:max_val_len - 3] + "..."
            
        raw_linha_completa = f"{raw_linha_esq}{valor}"
        espacos_restantes = largura_total - len(raw_linha_completa)
        
        col_label_colorida = f" {CLR_GRAY}{label}:{CLR_RESET}"
        espacos_col1 = col1_len - len(label_str)
        
        print(f"{CLR_HEADER}║{CLR_RESET}{col_label_colorida}{' ' * espacos_col1}{clr_valor}{valor}{CLR_RESET}{' ' * espacos_restantes}{CLR_HEADER}║{CLR_RESET}")

    print_linha_tabela("Sistema Operacional", os_info)
    print_linha_tabela("Arquitetura Alvo", arch_info, clr_valor=CLR_BLUE)
    print_linha_tabela("Processador (CPU)", cpu_info)
    print_linha_tabela("Memória RAM", mem_info)
    print_linha_tabela("Espaço em Disco", disk_info)
    
    print(f"{CLR_HEADER}╚{'═' * largura_total}╝{CLR_RESET}\n")

# Menu para seleção de instalação/atualização
def menu_selecao():
    largura_total = 78
    print(f"{CLR_HEADER}╔{'═' * largura_total}╗{CLR_RESET}")
    titulo = "MENU DE OPÇÕES DE ATUALIZAÇÃO"
    espaco_titulo = (largura_total - len(titulo)) // 2
    rem_titulo = largura_total - len(titulo) - espaco_titulo
    print(f"{CLR_HEADER}║{' ' * espaco_titulo}{titulo}{' ' * rem_titulo}║{CLR_RESET}")
    print(f"{CLR_HEADER}╠{'═' * largura_total}╣{CLR_RESET}")
    
    def print_opcao(num, desc):
        espacos = largura_total - 5 - len(str(num)) - len(desc)
        print(f"{CLR_HEADER}║{CLR_RESET}  {CLR_CYAN}[{num}]{CLR_WHITE} {desc}{CLR_RESET}{' ' * espacos}{CLR_HEADER}║{CLR_RESET}")
        
    print_opcao(1, "Instalar/Atualizar Ambos (Antigravity & Antigravity IDE)")
    print_opcao(2, "Instalar/Atualizar Apenas Antigravity (Hub)")
    print_opcao(3, "Instalar/Atualizar Apenas Antigravity IDE")
    print_opcao(4, "Forçar Reinstalação de Ambos (Mesmo na mesma versão)")
    print_opcao(5, "Consultar Changelog Oficial (com tradução)")
    print_opcao(6, "Sair")
    print_opcao(7, "Mostrar Versões Ativas")
    print_opcao(8, "Listar Histórico de Versões")
    print_opcao(9, "Rollback de Ambos para a Versão Anterior")
    print_opcao(10, "Limpar Histórico Antigo (Manter 2)")
    print(f"{CLR_HEADER}╚{'═' * largura_total}╝{CLR_RESET}")
    
    while True:
        try:
            opcao = input(f"\n{CLR_WHITE}Digite sua escolha (1-10): {CLR_RESET}").strip()
            if opcao in tuple(str(numero) for numero in range(1, 11)):
                return opcao
            print(f"{CLR_FAIL}Opção inválida! Escolha um número de 1 a 10.{CLR_RESET}")
        except (KeyboardInterrupt, EOFError):
            print(f"\n{CLR_WARNING}Operação cancelada pelo usuário.{CLR_RESET}")
            return "5"

# Função para obter a data de modificação no servidor remoto
def obter_data_servidor(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        method="HEAD"
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
            last_modified = response.info().get("Last-Modified")
            if last_modified:
                dt = email.utils.parsedate_to_datetime(last_modified)
                return dt.astimezone().strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        pass
    return None

# Função para requisições HTTP
def fetch_url(url, retries=HTTP_RETRIES):
    req = urllib.request.Request(
        url,
        headers={"Accept-Encoding": "gzip", "User-Agent": "Mozilla/5.0"}
    )
    for tentativa in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
                content = response.read()
                if response.info().get("Content-Encoding") == "gzip":
                    content = gzip.decompress(content)
                return content.decode("utf-8", errors="ignore")
        except Exception:
            if tentativa < retries:
                time.sleep(tentativa)
    return ""


def validar_url_download(url):
    """Aceita somente URLs HTTPS completas de arquivos tar.gz."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("A URL de download precisa usar HTTPS e possuir um host válido.")
    if parsed.username or parsed.password:
        raise ValueError("A URL de download não pode conter credenciais.")
    if not parsed.path.endswith(".tar.gz"):
        raise ValueError("A URL de download precisa apontar para um arquivo .tar.gz.")
    return url


def obter_checksum_remoto(url):
    """Obtém um SHA-256 publicado ao lado do pacote, quando disponível."""
    conteudo = fetch_url(f"{url}.sha256", retries=1)
    match = re.search(r"(?i)(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", conteudo)
    return match.group(0).lower() if match else None


def calcular_sha256(caminho):
    digest = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()

# Retorna o idioma preferencial do sistema (pt_BR.UTF-8 -> pt).
def obter_idioma_sistema():
    for variavel in ("LC_ALL", "LC_MESSAGES", "LANG"):
        valor = os.environ.get(variavel, "").strip()
        if valor and valor.upper() not in ("C", "POSIX"):
            idioma = re.split(r"[_.@-]", valor, maxsplit=1)[0].lower()
            if re.fullmatch(r"[a-z]{2,3}", idioma):
                return idioma
    return "en"

def limpar_html(fragmento):
    texto = re.sub(r"<[^>]+>", "", fragmento)
    return " ".join(html.unescape(texto).split())

def obter_url_changelog(aba, traduzir=False):
    url_oficial = f"{URL_CHANGELOG}?tab={aba}"
    idioma = obter_idioma_sistema()
    if traduzir and idioma != "en":
        return (
            "https://translate.google.com/translate?sl=en"
            f"&tl={urllib.parse.quote(idioma)}"
            f"&u={urllib.parse.quote(url_oficial, safe='')}"
        )
    return url_oficial

def obter_notas_versao(aba, versao):
    """Extrai as notas exatas de uma versão do HTML oficial do changelog."""
    if not conteudo_changelog:
        return None

    marcador_linha = '<div class="section-row-wrapper"'
    marcador_versao = f'href="/releases?tab={aba}&amp;version={versao}"'
    trecho = next(
        (parte for parte in conteudo_changelog.split(marcador_linha)
         if marcador_versao in parte),
        None,
    )
    if not trecho:
        return None

    titulo_match = re.search(r'<h3\b[^>]*>(.*?)</h3>', trecho, re.DOTALL)
    resumo_match = re.search(
        r'<div class="changes"[^>]*>\s*<p[^>]*>(.*?)</p>',
        trecho,
        re.DOTALL,
    )
    grupos = []
    for detalhe in re.findall(r'<details\b[^>]*>(.*?)</details>', trecho, re.DOTALL):
        nome_match = re.search(r'<summary[^>]*>(.*?)</summary>', detalhe, re.DOTALL)
        if not nome_match:
            continue
        itens = [
            limpar_html(item)
            for item in re.findall(r'<li\b[^>]*>(.*?)</li>', detalhe, re.DOTALL)
        ]
        grupos.append((limpar_html(nome_match.group(1)), [item for item in itens if item]))

    return {
        "titulo": limpar_html(titulo_match.group(1)) if titulo_match else "",
        "resumo": limpar_html(resumo_match.group(1)) if resumo_match else "",
        "grupos": grupos,
    }

def obter_versao_mais_recente(aba):
    if not conteudo_changelog:
        return None
    match = re.search(
        rf'href="/releases\?tab={re.escape(aba)}&amp;version=([^"&]+)"',
        conteudo_changelog,
    )
    return html.unescape(match.group(1)) if match else None

def exibir_notas_versao(nome_app, aba, versao):
    notas = obter_notas_versao(aba, versao)
    print(f"\n  {CLR_HEADER}Notas da versão {versao} — {nome_app}{CLR_RESET}")
    if notas:
        if notas["titulo"]:
            print(f"  {CLR_WHITE}{notas['titulo']}{CLR_RESET}")
        if notas["resumo"]:
            print(f"  {CLR_GRAY}{notas['resumo']}{CLR_RESET}")
        for grupo, itens in notas["grupos"]:
            print(f"  {CLR_CYAN}{grupo}:{CLR_RESET}")
            for item in itens:
                print(f"    {CLR_WHITE}• {item}{CLR_RESET}")
    else:
        print(f"  {CLR_WARNING}⚠ Não foram encontradas notas específicas para esta versão.{CLR_RESET}")

    url_oficial = obter_url_changelog(aba)
    print(f"  {CLR_BLUE}Changelog oficial: {url_oficial}{CLR_RESET}")
    if obter_idioma_sistema() != "en":
        print(f"  {CLR_BLUE}Versão traduzida:  {obter_url_changelog(aba, traduzir=True)}{CLR_RESET}")

def consultar_changelog():
    print(f"\n{CLR_HEADER}CHANGELOG OFICIAL — VERSÕES MAIS RECENTES{CLR_RESET}")
    encontrados = False
    for nome_app, aba in (("Antigravity", "hub"), ("Antigravity_IDE", "ide")):
        versao = obter_versao_mais_recente(aba)
        if versao:
            exibir_notas_versao(nome_app, aba, versao)
            encontrados = True
        else:
            print(f"\n  {CLR_WARNING}⚠ Não foi possível identificar a versão mais recente de {nome_app}.{CLR_RESET}")
            print(f"  {CLR_BLUE}Changelog oficial: {obter_url_changelog(aba)}{CLR_RESET}")
    return encontrados

# Download com barra de progresso animada
def download_com_progresso(url, dest_path, app_name, checksum_esperado=None):
    validar_url_download(url)
    arquivo_parcial = f"{dest_path}.part"
    ultimo_erro = None
    for tentativa in range(1, HTTP_RETRIES + 1):
        downloaded = 0
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
                url_final = response.geturl() if hasattr(response, "geturl") else url
                validar_url_download(url_final)
                total_size = int(response.info().get("Content-Length", 0))
                if total_size > MAX_DOWNLOAD_BYTES:
                    raise ValueError("O pacote excede o limite máximo permitido.")
                with open(arquivo_parcial, "wb") as out_file:
                    while True:
                        buffer = response.read(1024 * 64)
                        if not buffer:
                            break
                        downloaded += len(buffer)
                        if downloaded > MAX_DOWNLOAD_BYTES:
                            raise ValueError("O pacote excede o limite máximo permitido.")
                        out_file.write(buffer)
                        if total_size > 0:
                            percent = min(100, int(100 * downloaded / total_size))
                            bar_str = "#" * (percent // 2) + "." * (50 - percent // 2)
                            sys.stdout.write(
                                f"\r  {CLR_BLUE}Baixando {app_name}: [{bar_str}] {percent}% "
                                f"({downloaded/1024/1024:.1f}MB / {total_size/1024/1024:.1f}MB){CLR_RESET}"
                            )
                            sys.stdout.flush()
            if downloaded == 0:
                raise ValueError("O arquivo baixado está vazio.")
            digest = calcular_sha256(arquivo_parcial)
            if checksum_esperado and digest != checksum_esperado.lower():
                raise ValueError("O SHA-256 do pacote não corresponde ao checksum publicado.")
            os.replace(arquivo_parcial, dest_path)
            sys.stdout.write("\n")
            return True
        except Exception as erro:
            ultimo_erro = erro
            if os.path.exists(arquivo_parcial):
                os.unlink(arquivo_parcial)
            if tentativa < HTTP_RETRIES:
                print(f"\n  {CLR_WARNING}Tentativa {tentativa} falhou; tentando novamente...{CLR_RESET}")
                time.sleep(tentativa)
    sys.stdout.write("\n")
    print(f"  {CLR_FAIL}Erro ao fazer o download após {HTTP_RETRIES} tentativas: {ultimo_erro}{CLR_RESET}")
    return False

# Cria atalho no Desktop do usuário
def criar_atalho(nome_app):
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        try:
            import subprocess
            desktop_dir = subprocess.check_output(["sudo", "-u", sudo_user, "xdg-user-dir", "DESKTOP"]).decode("utf-8").strip()
        except Exception:
            desktop_dir = f"/home/{sudo_user}/Desktop"
    else:
        try:
            import subprocess
            desktop_dir = subprocess.check_output(["xdg-user-dir", "DESKTOP"]).decode("utf-8").strip()
        except Exception:
            desktop_dir = os.path.expanduser("~/Desktop")
        
    if not os.path.exists(desktop_dir):
        return False
        
    shortcut_path = os.path.join(desktop_dir, f"{nome_app}.desktop")
    
    if nome_app == "Antigravity":
        exec_path = os.path.join(DIRETORIO_BASE, "Antigravity", "antigravity")
        icon_path = os.path.join(DIRETORIO_BASE, "Antigravity", "antigravity-logo.png")
        fallback_icon = os.path.join(DIRETORIO_BASE, "Antigravity_IDE", "resources", "app", "out", "vs", "platform", "browserOnboarding", "static", "antigravity.svg")
    else:
        exec_path = os.path.join(DIRETORIO_BASE, "Antigravity_IDE", "antigravity-ide")
        icon_path = os.path.join(DIRETORIO_BASE, "Antigravity_IDE", "antigravity-logo.png")
        fallback_icon = os.path.join(DIRETORIO_BASE, "Antigravity_IDE", "resources", "app", "out", "media", "code-icon.svg")

    if not os.path.exists(icon_path):
        try:
            # Baixa a imagem oficial do logo
            req = urllib.request.Request("https://antigravity.google/assets/image/antigravity-logo.png", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as response, open(icon_path, "wb") as out_file:
                shutil.copyfileobj(response, out_file)
        except Exception:
            if os.path.exists(fallback_icon):
                icon_path = fallback_icon
            else:
                icon_path = "system-run"
            
    content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name={nome_app.replace('_', ' ')}
Comment=Executar {nome_app.replace('_', ' ')}
Exec="{exec_path}"
Icon={icon_path}
Terminal=false
Categories=Development;
"""
    try:
        spinner_shortcut = TerminalSpinner(f"Criando atalho de desktop para {nome_app}")
        spinner_shortcut.start()
        with open(shortcut_path, "w") as f:
            f.write(content)
        os.chmod(shortcut_path, 0o755)
        if sudo_user:
            try:
                import pwd
                pw = pwd.getpwnam(sudo_user)
                os.chown(shortcut_path, pw.pw_uid, pw.pw_gid)
            except Exception:
                pass
        spinner_shortcut.stop(success=True, final_msg=f"Atalho de desktop criado para {nome_app}")
        return True
    except Exception as e:
        spinner_shortcut.stop(success=False, final_msg=f"Erro ao criar atalho no desktop: {e}")
        return False


def _partes_caminho_tar(caminho):
    if not caminho or "\x00" in caminho or posixpath.isabs(caminho):
        raise ValueError(f"Caminho inseguro no pacote: {caminho!r}")
    partes = [parte for parte in caminho.split("/") if parte not in ("", ".")]
    if not partes or ".." in partes:
        raise ValueError(f"Caminho inseguro no pacote: {caminho!r}")
    return partes


def preparar_membros_tar(tar):
    """Valida e adapta membros para uma extração com strip-components=1."""
    membros = tar.getmembers()
    if len(membros) > MAX_ARCHIVE_MEMBERS:
        raise ValueError("O pacote contém arquivos demais.")
    tamanho_total = sum(membro.size for membro in membros if membro.isfile())
    if tamanho_total > MAX_EXTRACTED_BYTES:
        raise ValueError("O conteúdo descompactado excede o limite permitido.")

    seguros = []
    caminhos_links = set()
    for membro in membros:
        if membro.ischr() or membro.isblk() or membro.isfifo():
            raise ValueError(f"Tipo de arquivo não permitido no pacote: {membro.name}")
        partes = _partes_caminho_tar(membro.name)
        if len(partes) == 1:
            continue
        membro.name = "/".join(partes[1:])

        if membro.issym():
            alvo = membro.linkname
            if not alvo or posixpath.isabs(alvo):
                raise ValueError(f"Link simbólico inseguro no pacote: {membro.name}")
            resolvido = posixpath.normpath(posixpath.join(posixpath.dirname(membro.name), alvo))
            if resolvido == ".." or resolvido.startswith("../"):
                raise ValueError(f"Link simbólico escapa do staging: {membro.name}")
            caminhos_links.add(membro.name.rstrip("/"))
        elif membro.islnk():
            partes_alvo = _partes_caminho_tar(membro.linkname)
            if len(partes_alvo) == 1:
                raise ValueError(f"Hard link inválido no pacote: {membro.name}")
            membro.linkname = "/".join(partes_alvo[1:])
        seguros.append(membro)

    for membro in seguros:
        partes = membro.name.split("/")
        pais = {"/".join(partes[:indice]) for indice in range(1, len(partes))}
        if pais & caminhos_links:
            raise ValueError(f"Arquivo seria extraído através de um link: {membro.name}")
    return seguros


def extrair_pacote_seguro(arquivo_tar, destino):
    """Extrai um pacote validado para um diretório vazio de staging."""
    if os.listdir(destino):
        raise ValueError("O diretório de staging precisa estar vazio.")
    with tarfile.open(arquivo_tar, "r:gz") as tar:
        membros = preparar_membros_tar(tar)
        kwargs = {}
        if "filter" in inspect.signature(tar.extractall).parameters:
            kwargs["filter"] = "data"
        tar.extractall(path=destino, members=membros, **kwargs)


def validar_instalacao_extraida(nome_app, staging):
    executavel = "antigravity" if nome_app == "Antigravity" else "antigravity-ide"
    caminho = os.path.join(staging, executavel)
    if not os.path.isfile(caminho):
        raise ValueError(f"Executável esperado não encontrado: {executavel}")
    if not os.access(caminho, os.X_OK):
        raise ValueError(f"Executável sem permissão de execução: {executavel}")
    return caminho


def normalizar_permissoes_staging(staging):
    """Remove bits privilegiados e torna a raiz da versão atravessável."""
    os.chmod(staging, 0o755)
    for raiz, diretorios, arquivos in os.walk(staging, followlinks=False):
        for nome in diretorios + arquivos:
            caminho = os.path.join(raiz, nome)
            if os.path.islink(caminho):
                continue
            modo = stat.S_IMODE(os.lstat(caminho).st_mode)
            if modo & 0o6000:
                os.chmod(caminho, modo & ~0o6000)


def preparar_versao_em_staging(nome_app, versao, arquivo_tar, url, sha256, checksum_verificado):
    pasta_versoes = os.path.join(DIRETORIO_BASE, f"{nome_app}_VERSOES")
    os.makedirs(pasta_versoes, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=f".{nome_app}-{versao}-", dir=pasta_versoes)
    destino = os.path.join(pasta_versoes, f"{nome_app}-{versao}")
    if os.path.lexists(destino):
        destino = f"{destino}-reinstall-{time.time_ns()}"
    try:
        extrair_pacote_seguro(arquivo_tar, staging)
        validar_instalacao_extraida(nome_app, staging)
        normalizar_permissoes_staging(staging)
        with open(os.path.join(staging, "version.txt"), "w", encoding="utf-8") as arquivo:
            arquivo.write(f"{versao}\n")
        manifesto = {
            "app": nome_app,
            "version": versao,
            "source_url": url,
            "sha256": sha256,
            "checksum_verified": checksum_verificado,
            "installed_at": datetime.now().astimezone().isoformat(),
        }
        with open(os.path.join(staging, ".install-manifest.json"), "w", encoding="utf-8") as arquivo:
            json.dump(manifesto, arquivo, ensure_ascii=False, indent=2)
            arquivo.write("\n")

        os.replace(staging, destino)
        return destino
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def pasta_versoes(nome_app):
    return os.path.join(DIRETORIO_BASE, f"{nome_app}_VERSOES")


def caminho_estado(nome_app):
    return os.path.join(DIRETORIO_BASE, f".{nome_app}-state")


def caminho_relativo_versao(nome_app, caminho):
    raiz = os.path.realpath(pasta_versoes(nome_app))
    resolvido = os.path.realpath(caminho)
    if resolvido == raiz or os.path.commonpath((raiz, resolvido)) != raiz or not os.path.isdir(resolvido):
        raise ValueError("A versão não pertence ao histórico gerenciado.")
    return os.path.relpath(resolvido, DIRETORIO_BASE)


def ler_estado(nome_app):
    estado = {}
    try:
        with open(caminho_estado(nome_app), "r", encoding="utf-8") as arquivo:
            for linha in arquivo:
                chave, separador, valor = linha.rstrip("\n").partition("=")
                if separador and chave in ("active", "previous") and valor:
                    candidato = os.path.join(DIRETORIO_BASE, valor)
                    caminho_relativo_versao(nome_app, candidato)
                    estado[chave] = os.path.realpath(candidato)
    except (OSError, ValueError):
        return {}
    return estado


def gravar_estado(nome_app, ativo, anterior=None):
    destino = caminho_estado(nome_app)
    temporario = f"{destino}.tmp-{os.getpid()}"
    linhas = [f"active={caminho_relativo_versao(nome_app, ativo)}\n"]
    if anterior and os.path.realpath(anterior) != os.path.realpath(ativo):
        linhas.append(f"previous={caminho_relativo_versao(nome_app, anterior)}\n")
    with open(temporario, "w", encoding="utf-8") as arquivo:
        arquivo.writelines(linhas)
        arquivo.flush()
        os.fsync(arquivo.fileno())
    os.chmod(temporario, 0o600)
    os.replace(temporario, destino)


def obter_versao_ativa(nome_app):
    link = os.path.join(DIRETORIO_BASE, nome_app)
    if not os.path.islink(link):
        return None
    try:
        caminho_relativo_versao(nome_app, link)
    except ValueError:
        return None
    return os.path.realpath(link)


def ler_numero_versao(caminho):
    try:
        with open(os.path.join(caminho, "version.txt"), "r", encoding="utf-8") as arquivo:
            return arquivo.read().strip()
    except OSError:
        return os.path.basename(caminho).split("-", 1)[-1]


def chave_versao(valor):
    numeros = re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)$", valor)
    if not numeros:
        return (0, 0, 0, valor)
    return tuple(int(item) for item in numeros.groups()[:3]) + (numeros.group(4),)


def listar_versoes(nome_app):
    raiz = pasta_versoes(nome_app)
    ativa = obter_versao_ativa(nome_app)
    if not os.path.isdir(raiz):
        return []
    versoes = []
    for entrada in os.scandir(raiz):
        if entrada.name.startswith(".") or not entrada.is_dir(follow_symlinks=False):
            continue
        caminho = entrada.path
        versoes.append({
            "version": ler_numero_versao(caminho),
            "path": caminho,
            "active": ativa == os.path.realpath(caminho),
            "installed_at": entrada.stat(follow_symlinks=False).st_mtime,
        })
    return sorted(
        versoes,
        key=lambda item: (chave_versao(item["version"]), item["installed_at"]),
        reverse=True,
    )


def resolver_versao(nome_app, versao):
    encontradas = [item["path"] for item in listar_versoes(nome_app) if item["version"] == versao]
    if not encontradas:
        raise ValueError(f"Versão não encontrada para {nome_app}: {versao}")
    return encontradas[0]


def testar_saude_versao(nome_app, caminho):
    executavel = validar_instalacao_extraida(nome_app, caminho)
    ambiente = os.environ.copy()
    ambiente["ELECTRON_RUN_AS_NODE"] = "1"
    try:
        resultado = subprocess.run(
            [executavel, "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=HEALTHCHECK_TIMEOUT,
            env=ambiente,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as erro:
        raise RuntimeError(f"Health check não pôde ser executado: {erro}") from erro
    if resultado.returncode != 0 or not resultado.stdout.strip():
        detalhe = resultado.stderr.strip().splitlines()[-1] if resultado.stderr.strip() else "sem resposta"
        raise RuntimeError(f"Health check falhou ({resultado.returncode}): {detalhe}")
    return resultado.stdout.strip().splitlines()[0]


def _trocar_link_atomico(nome_app, destino):
    link = os.path.join(DIRETORIO_BASE, nome_app)
    if os.path.lexists(link) and not os.path.islink(link):
        raise RuntimeError(f"O caminho ativo não é um link simbólico gerenciado: {link}")
    relativo = caminho_relativo_versao(nome_app, destino)
    temporario = os.path.join(DIRETORIO_BASE, f".{nome_app}.link-{os.getpid()}-{time.time_ns()}")
    os.symlink(relativo, temporario)
    try:
        os.replace(temporario, link)
    finally:
        if os.path.lexists(temporario):
            os.unlink(temporario)


def ativar_versao_atomica(nome_app, destino):
    destino = os.path.realpath(destino)
    anterior = obter_versao_ativa(nome_app)
    estado_anterior = ler_estado(nome_app)
    versao_reportada = testar_saude_versao(nome_app, destino)
    _trocar_link_atomico(nome_app, destino)
    try:
        testar_saude_versao(nome_app, os.path.join(DIRETORIO_BASE, nome_app))
        candidato_anterior = anterior
        if anterior and anterior == destino:
            candidato_anterior = estado_anterior.get("previous")
        gravar_estado(nome_app, destino, candidato_anterior)
    except Exception:
        if anterior:
            _trocar_link_atomico(nome_app, anterior)
        else:
            os.unlink(os.path.join(DIRETORIO_BASE, nome_app))
        raise
    return versao_reportada


def rollback_aplicativo(nome_app, versao=None):
    ativa = obter_versao_ativa(nome_app)
    if versao:
        destino = resolver_versao(nome_app, versao)
    else:
        estado = ler_estado(nome_app)
        destino = estado.get("previous")
        if not destino or destino == ativa or not os.path.isdir(destino):
            destino = next((item["path"] for item in listar_versoes(nome_app) if not item["active"]), None)
    if not destino:
        raise ValueError(f"Não existe versão anterior disponível para {nome_app}.")
    if ativa and os.path.realpath(destino) == ativa:
        raise ValueError("A versão solicitada já está ativa.")
    resultado = ativar_versao_atomica(nome_app, destino)
    return ler_numero_versao(destino), resultado


def podar_versoes(nome_app, manter=2):
    if manter < 1:
        raise ValueError("A retenção precisa ser pelo menos 1.")
    versoes = listar_versoes(nome_app)
    protegidas = set()
    ativa = obter_versao_ativa(nome_app)
    if ativa:
        protegidas.add(ativa)
    anterior = ler_estado(nome_app).get("previous")
    if anterior and os.path.isdir(anterior):
        protegidas.add(os.path.realpath(anterior))
    for item in versoes:
        if len(protegidas) >= manter:
            break
        protegidas.add(os.path.realpath(item["path"]))

    removidas = []
    for item in versoes:
        caminho = os.path.realpath(item["path"])
        if caminho not in protegidas:
            shutil.rmtree(caminho)
            removidas.append(item["version"])
    return removidas


def exibir_estado_aplicativos(nomes, detalhado=False):
    for nome_app in nomes:
        versoes = listar_versoes(nome_app)
        ativa = next((item for item in versoes if item["active"]), None)
        if not detalhado:
            valor = ativa["version"] if ativa else "não instalada"
            print(f"{nome_app}: {valor}")
            continue
        print(f"\n{nome_app}:")
        if not versoes:
            print("  Nenhuma versão instalada.")
        for item in versoes:
            marcador = "*" if item["active"] else " "
            data = datetime.fromtimestamp(item["installed_at"]).strftime("%d/%m/%Y %H:%M:%S")
            print(f"  {marcador} {item['version']}  ({data})")


def selecionar_aplicativos(argumentos):
    hub = any(item in ("hub", "antigravity") for item in argumentos)
    ide = any(item in ("ide", "antigravity-ide") for item in argumentos)
    if hub and not ide:
        return ["Antigravity"]
    if ide and not hub:
        return ["Antigravity_IDE"]
    return ["Antigravity", "Antigravity_IDE"]


# Função interna para processar cada um dos aplicativos
def atualizar_aplicativo(nome_app, padrao_url, aba_changelog, forcar=False):
    print(f"\n{CLR_BLUE}⚡ Analisando: {nome_app} ({padrao_url}) {CLR_RESET}")
    print(f"  {CLR_GRAY}----------------------------------------{CLR_RESET}")

    # 1. Extrai todas as URLs que terminam em .tar.gz
    urls = re.findall(r'https://[^\s"]+\.tar\.gz', conteudo_total)
    
    url_download = None
    for url in urls:
        if padrao_url in url and ARCH_ALVO in url:
            url_download = url
            break

    if not url_download:
        print(f"  {CLR_WARNING}⚠ Link de download não disponível para {nome_app} ({ARCH_ALVO}).{CLR_RESET}")
        return False

    try:
        validar_url_download(url_download)
    except ValueError as erro:
        print(f"  {CLR_FAIL}URL de download rejeitada: {erro}{CLR_RESET}")
        return False

    # 2. Extrair a versão a partir do link de download
    match_versao = re.search(r'/([0-9]+\.[0-9]+\.[0-9]+[^/]*)', url_download)
    if not match_versao:
        print(f"  {CLR_WARNING}⚠ Não foi possível extrair a versão de {nome_app} do link.{CLR_RESET}")
        return False
    versao_web = match_versao.group(1)

    # 3. Verificar versão local atual e data de instalação
    pasta_app = os.path.join(DIRETORIO_BASE, nome_app)
    arquivo_versao_local = os.path.join(pasta_app, "version.txt")

    if os.path.exists(arquivo_versao_local):
        try:
            with open(arquivo_versao_local, "r") as f:
                versao_local = f.read().strip()
            mtime = os.path.getmtime(arquivo_versao_local)
            dt_local = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M:%S")
            str_data_local = f" (Instalado em: {dt_local})"
        except Exception:
            versao_local = "Desconhecida"
            str_data_local = ""
    else:
        versao_local = "Nenhuma (Instalação Nova)"
        str_data_local = ""

    # 4. Obter data do arquivo no servidor
    data_servidor = obter_data_servidor(url_download)
    str_data_web = f" (Lançado em: {data_servidor})" if data_servidor else ""

    print(f"  {CLR_WHITE}Versão na Web: {CLR_CYAN}{versao_web}{CLR_RESET}{CLR_GRAY}{str_data_web}{CLR_RESET}")
    print(f"  {CLR_WHITE}Versão Local:  {CLR_GRAY}{versao_local}{str_data_local}{CLR_RESET}")
    exibir_notas_versao(nome_app, aba_changelog, versao_web)

    # 5. Tomada de Decisão e Atualização
    if versao_local != versao_web or forcar:
        if versao_local == versao_web and forcar:
            print(f"  {CLR_WARNING}➜ Versões coincidem, mas a reinstalação foi forçada! Inicializando download...{CLR_RESET}")
        else:
            print(f"  {CLR_WARNING}➜ Nova versão disponível! Inicializando download...{CLR_RESET}")
        arquivo_tar = os.path.join(PASTA_TMP, f"{nome_app}.tar.gz")

        checksum_esperado = obter_checksum_remoto(url_download)
        if checksum_esperado:
            print(f"  {CLR_BLUE}SHA-256 oficial encontrado; o pacote será verificado.{CLR_RESET}")
        else:
            print(f"  {CLR_WARNING}Checksum oficial não publicado; o SHA-256 local será registrado.{CLR_RESET}")

        # Download do arquivo com progresso e publicação somente após validação.
        if not download_com_progresso(url_download, arquivo_tar, nome_app, checksum_esperado):
            return False

        if not os.path.exists(arquivo_tar) or os.path.getsize(arquivo_tar) == 0:
            print(f"  {CLR_FAIL}Erro: Arquivo baixado está vazio.{CLR_RESET}")
            return False

        spinner_extrai = TerminalSpinner(f"Extraindo arquivos para {nome_app}-{versao_web}")
        spinner_extrai.start()

        try:
            digest = calcular_sha256(arquivo_tar)
            pasta_nova_versao = preparar_versao_em_staging(
                nome_app,
                versao_web,
                arquivo_tar,
                url_download,
                digest,
                checksum_esperado is not None,
            )
        except Exception as e:
            spinner_extrai.stop(success=False, final_msg=f"Falha ao extrair {nome_app}: {e}")
            return False

        spinner_extrai.stop(success=True, final_msg=f"Extraído com sucesso para: {nome_app}-{versao_web}")

        spinner_link = TerminalSpinner("Testando e ativando a nova versão atomicamente")
        spinner_link.start()
        try:
            versao_runtime = ativar_versao_atomica(nome_app, pasta_nova_versao)
        except Exception as e:
            spinner_link.stop(success=False, final_msg=f"Falha ao ativar {nome_app}; versão anterior preservada: {e}")
            return False

        spinner_link.stop(success=True, final_msg=f"Versão ativada e saudável ({versao_runtime})")
        criar_atalho(nome_app)
        print(f"  {CLR_GREEN}✓ {nome_app} atualizado com sucesso!{CLR_RESET}")
        return True
    else:
        criar_atalho(nome_app)
        print(f"  {CLR_GREEN}✓ {nome_app} já está atualizado na versão mais recente.{CLR_RESET}")
        return True

if __name__ == "__main__":
    verificar_privilegios()
    try:
        adquirir_bloqueio()
    except (OSError, RuntimeError) as erro:
        print(f"{CLR_FAIL}{erro}{CLR_RESET}")
        sys.exit(1)
    atexit.register(liberar_recursos)
    preparar_diretorios()

    # Exibe diagnósticos
    exibir_diagnosticos()
    
    # Determina a opção e flags a partir de argumentos de linha de comando para automações
    opcao = None
    forcar_reinstalacao = False

    args = [arg.lower().strip("-") for arg in sys.argv[1:]]
    if "force" in args or "f" in args:
        forcar_reinstalacao = True
        args = [a for a in args if a not in ("force", "f")]

    comandos_gerenciamento = ("current", "list", "rollback", "prune")
    comando = next((item for item in args if item in comandos_gerenciamento), None)
    if comando:
        nomes = selecionar_aplicativos(args)
        try:
            if comando == "current":
                exibir_estado_aplicativos(nomes)
            elif comando == "list":
                exibir_estado_aplicativos(nomes, detalhado=True)
            elif comando == "rollback":
                indice = args.index("rollback")
                versao = args[indice + 1] if indice + 1 < len(args) and args[indice + 1] not in (
                    "hub", "antigravity", "ide", "antigravity-ide"
                ) else None
                if versao and len(nomes) != 1:
                    raise ValueError("Informe --hub ou --ide ao solicitar uma versão específica.")
                for nome_app in nomes:
                    nova_versao, runtime = rollback_aplicativo(nome_app, versao)
                    print(f"{CLR_GREEN}✓ {nome_app} revertido para {nova_versao} ({runtime}).{CLR_RESET}")
            elif comando == "prune":
                indice = args.index("prune")
                manter = 2
                if indice + 1 < len(args) and args[indice + 1].isdigit():
                    manter = int(args[indice + 1])
                for nome_app in nomes:
                    removidas = podar_versoes(nome_app, manter)
                    resumo = ", ".join(removidas) if removidas else "nenhuma"
                    print(f"{nome_app}: versões removidas: {resumo}")
        except (OSError, ValueError, RuntimeError) as erro:
            print(f"{CLR_FAIL}Erro: {erro}{CLR_RESET}")
            sys.exit(1)
        sys.exit(0)

    if len(args) > 0:
        arg = args[0]
        if arg in ("1", "both", "all"):
            opcao = "1"
        elif arg in ("2", "hub", "antigravity"):
            opcao = "2"
        elif arg in ("3", "ide", "antigravity-ide"):
            opcao = "3"
        elif arg in ("4", "reinstall"):
            opcao = "4"
        elif arg in ("5", "changelog", "changes", "release-notes"):
            opcao = "5"
        elif arg in ("6", "exit", "quit"):
            opcao = "6"
        elif arg in ("7",):
            opcao = "7"
        elif arg in ("8",):
            opcao = "8"
        elif arg in ("9",):
            opcao = "9"
        elif arg in ("10",):
            opcao = "10"
            
    if opcao is None:
        # Exibe menu de seleção se nenhum argumento válido for fornecido
        opcao = menu_selecao()
        
    if opcao == "4":
        opcao = "1"
        forcar_reinstalacao = True
    elif opcao == "6":
        print(f"\n{CLR_BLUE}Saindo sem realizar alterações.{CLR_RESET}\n")
        sys.exit(0)

    if opcao in ("7", "8", "9", "10"):
        nomes = ["Antigravity", "Antigravity_IDE"]
        try:
            if opcao == "7":
                exibir_estado_aplicativos(nomes)
            elif opcao == "8":
                exibir_estado_aplicativos(nomes, detalhado=True)
            elif opcao == "9":
                for nome_app in nomes:
                    versao, runtime = rollback_aplicativo(nome_app)
                    print(f"{CLR_GREEN}✓ {nome_app} revertido para {versao} ({runtime}).{CLR_RESET}")
            else:
                for nome_app in nomes:
                    removidas = podar_versoes(nome_app, 2)
                    resumo = ", ".join(removidas) if removidas else "nenhuma"
                    print(f"{nome_app}: versões removidas: {resumo}")
        except (OSError, ValueError, RuntimeError) as erro:
            print(f"{CLR_FAIL}Erro: {erro}{CLR_RESET}")
            sys.exit(1)
        sys.exit(0)

    if opcao == "5":
        spinner_changelog = TerminalSpinner("Buscando changelog oficial")
        spinner_changelog.start()
        conteudo_changelog = fetch_url(URL_CHANGELOG)
        if not conteudo_changelog:
            spinner_changelog.stop(success=False, final_msg="Falha ao buscar o changelog oficial")
            print(f"{CLR_BLUE}Consulte: {obter_url_changelog('hub')}{CLR_RESET}")
            sys.exit(1)
        spinner_changelog.stop(success=True, final_msg="Changelog oficial carregado com sucesso!")
        sys.exit(0 if consultar_changelog() else 1)
        
    # Inicializa busca (scraping) apenas se o usuário for atualizar algo
    spinner_busca = TerminalSpinner("Buscando versões e mapeando dependências dinâmicas")
    spinner_busca.start()

    # Baixa a página principal
    html_content = fetch_url("https://antigravity.google/download")
    if not html_content:
        spinner_busca.stop(success=False, final_msg="Falha ao buscar a página de downloads")
        sys.exit(1)

    # Extrai os links dos arquivos JavaScript
    js_files = re.findall(r'(?:src|href)="([^"]+\.js)"', html_content)
    conteudo_total = html_content

    for js in js_files:
        if js.startswith(("http://", "https://")):
            js_url = js
        else:
            js_url = f"https://antigravity.google/{js.lstrip('/')}"
        conteudo_total += "\n" + fetch_url(js_url)

    # O changelog é independente da página de downloads. Uma falha aqui não
    # deve impedir a instalação; exibir_notas_versao oferece o link oficial.
    conteudo_changelog = fetch_url(URL_CHANGELOG)

    spinner_busca.stop(success=True, final_msg="Versões, links e changelog carregados com sucesso!")

    # Executa a ação escolhida
    sucesso = True
    if opcao == "1":
        s1 = atualizar_aplicativo("Antigravity", "antigravity-hub", "hub", forcar=forcar_reinstalacao)
        s2 = atualizar_aplicativo("Antigravity_IDE", "stable", "ide", forcar=forcar_reinstalacao)
        sucesso = s1 and s2
    elif opcao == "2":
        sucesso = atualizar_aplicativo("Antigravity", "antigravity-hub", "hub", forcar=forcar_reinstalacao)
    elif opcao == "3":
        sucesso = atualizar_aplicativo("Antigravity_IDE", "stable", "ide", forcar=forcar_reinstalacao)
        
    if sucesso:
        print(f"\n{CLR_HEADER}======================================================={CLR_RESET}")
        print(f"{CLR_GREEN}  Processo concluído com sucesso!                      {CLR_RESET}")
        print(f"{CLR_HEADER}======================================================={CLR_RESET}")
    else:
        print(f"\n{CLR_FAIL}Processo concluído com falhas.{CLR_RESET}")

    sys.exit(codigo_saida(sucesso))
