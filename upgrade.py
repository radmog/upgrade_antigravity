#!/usr/bin/env python3
import os
import sys
import platform
import urllib.request
import urllib.error
import urllib.parse
import gzip
import re
import shutil
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
PASTA_TMP = "/tmp/antigravity_upgrade"
URL_CHANGELOG = "https://antigravity.google/changelog"

# Verificar privilégios de administrador (root)
if os.geteuid() != 0:
    print(f"{CLR_FAIL}Erro: Este script precisa ser executado com privilégios de administrador (root/sudo).{CLR_RESET}")
    print(f"{CLR_WARNING}Por favor, execute novamente usando: sudo {sys.executable or 'python3'} {os.path.abspath(sys.argv[0])}{CLR_RESET}\n")
    sys.exit(1)

# Variável para acumular o conteúdo HTML + JS raspado da web
conteudo_total = ""
conteudo_changelog = ""

# Detecta automaticamente a arquitetura do Ubuntu do usuário
arch_atual = platform.machine()
if arch_atual == "x86_64":
    ARCH_ALVO = "linux-x64"
elif arch_atual in ("aarch64", "arm64"):
    ARCH_ALVO = "linux-arm"
else:
    print(f"{CLR_FAIL}Arquitetura não suportada: {arch_atual}{CLR_RESET}")
    sys.exit(1)

# Criar os diretórios necessários
os.makedirs(DIRETORIO_BASE, exist_ok=True)
os.makedirs(PASTA_TMP, exist_ok=True)

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
        # Visualmente o texto tem: "  [num] desc"
        # Sem cores isso tem largura: 2 (espaço) + 3 ("[%d]" % num) + 1 (espaço) + len(desc) = 6 + len(desc)
        espacos = largura_total - 6 - len(desc)
        print(f"{CLR_HEADER}║{CLR_RESET}  {CLR_CYAN}[{num}]{CLR_WHITE} {desc}{CLR_RESET}{' ' * espacos}{CLR_HEADER}║{CLR_RESET}")
        
    print_opcao(1, "Instalar/Atualizar Ambos (Antigravity & Antigravity IDE)")
    print_opcao(2, "Instalar/Atualizar Apenas Antigravity (Hub)")
    print_opcao(3, "Instalar/Atualizar Apenas Antigravity IDE")
    print_opcao(4, "Forçar Reinstalação de Ambos (Mesmo na mesma versão)")
    print_opcao(5, "Consultar Changelog Oficial (com tradução)")
    print_opcao(6, "Sair")
    print(f"{CLR_HEADER}╚{'═' * largura_total}╝{CLR_RESET}")
    
    while True:
        try:
            opcao = input(f"\n{CLR_WHITE}Digite sua escolha (1-6): {CLR_RESET}").strip()
            if opcao in ("1", "2", "3", "4", "5", "6"):
                return opcao
            print(f"{CLR_FAIL}Opção inválida! Escolha um número de 1 a 6.{CLR_RESET}")
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
        with urllib.request.urlopen(req) as response:
            last_modified = response.info().get("Last-Modified")
            if last_modified:
                dt = email.utils.parsedate_to_datetime(last_modified)
                return dt.astimezone().strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        pass
    return None

# Função para requisições HTTP
def fetch_url(url):
    req = urllib.request.Request(
        url,
        headers={"Accept-Encoding": "gzip", "User-Agent": "Mozilla/5.0"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            content = response.read()
            if response.info().get("Content-Encoding") == "gzip":
                content = gzip.decompress(content)
            return content.decode("utf-8", errors="ignore")
    except Exception:
        return ""

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
def download_com_progresso(url, dest_path, app_name):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req) as response:
            total_size = int(response.info().get("Content-Length", 0))
            bloco_size = 1024 * 64
            downloaded = 0
            
            with open(dest_path, "wb") as out_file:
                while True:
                    buffer = response.read(bloco_size)
                    if not buffer:
                        break
                    out_file.write(buffer)
                    downloaded += len(buffer)
                    
                    if total_size > 0:
                        percent = int(100 * downloaded / total_size)
                        num_hashes = percent // 2
                        bar_str = "#" * num_hashes + "." * (50 - num_hashes)
                        sys.stdout.write(
                            f"\r  {CLR_BLUE}Baixando {app_name}: [{bar_str}] {percent}% "
                            f"({downloaded/1024/1024:.1f}MB / {total_size/1024/1024:.1f}MB){CLR_RESET}"
                        )
                        sys.stdout.flush()
            sys.stdout.write("\n")
            return True
    except Exception as e:
        sys.stdout.write("\n")
        print(f"  {CLR_FAIL}Erro ao fazer o download: {e}{CLR_RESET}")
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

        # Download do arquivo com progresso
        if not download_com_progresso(url_download, arquivo_tar, nome_app):
            return False

        if not os.path.exists(arquivo_tar) or os.path.getsize(arquivo_tar) == 0:
            print(f"  {CLR_FAIL}Erro: Arquivo baixado está vazio.{CLR_RESET}")
            return False

        # Cria pasta específica da versão
        pasta_nova_versao = os.path.join(DIRETORIO_BASE, f"{nome_app}_VERSOES", f"{nome_app}-{versao_web}")
        os.makedirs(pasta_nova_versao, exist_ok=True)

        spinner_extrai = TerminalSpinner(f"Extraindo arquivos para {nome_app}-{versao_web}")
        spinner_extrai.start()

        try:
            # Extração equivalente a --strip-components=1
            with tarfile.open(arquivo_tar, "r:gz") as tar:
                members = []
                for member in tar.getmembers():
                    parts = member.name.split("/", 1)
                    if len(parts) > 1 and parts[1]:  # Garante que não é um diretório raiz vazio
                        member.name = parts[1]
                        members.append(member)
                
                # Suporte à segurança de filtros no python 3.12+
                kwargs = {}
                if "filter" in inspect.signature(tar.extractall).parameters:
                    kwargs["filter"] = "fully_trusted"
                tar.extractall(path=pasta_nova_versao, members=members, **kwargs)
        except Exception as e:
            spinner_extrai.stop(success=False, final_msg=f"Falha ao extrair {nome_app}: {e}")
            if os.path.exists(pasta_nova_versao):
                shutil.rmtree(pasta_nova_versao)
            return False

        # Escreve a nova versão local
        try:
            with open(os.path.join(pasta_nova_versao, "version.txt"), "w") as f:
                f.write(versao_web + "\n")
        except Exception:
            pass

        spinner_extrai.stop(success=True, final_msg=f"Extraído com sucesso para: {nome_app}-{versao_web}")

        # Atualiza o Link Simbólico principal (usando caminho relativo para evitar problemas de montagem/codificação)
        spinner_link = TerminalSpinner("Atualizando link simbólico do sistema")
        spinner_link.start()

        if os.path.islink(pasta_app) or os.path.exists(pasta_app):
            try:
                if os.path.isdir(pasta_app) and not os.path.islink(pasta_app):
                    shutil.rmtree(pasta_app)
                else:
                    os.unlink(pasta_app)
            except Exception as e:
                spinner_link.stop(success=False, final_msg=f"Erro ao remover link antigo: {e}")
                return False

        try:
            relative_target = os.path.join(f"{nome_app}_VERSOES", f"{nome_app}-{versao_web}")
            os.symlink(relative_target, pasta_app)
        except Exception as e:
            spinner_link.stop(success=False, final_msg=f"Erro ao criar link simbólico: {e}")
            return False

        spinner_link.stop(success=True, final_msg=f"Link simbólico atualizado: {nome_app} -> {relative_target}")
        criar_atalho(nome_app)
        print(f"  {CLR_GREEN}✓ {nome_app} atualizado com sucesso!{CLR_RESET}")
        return True
    else:
        criar_atalho(nome_app)
        print(f"  {CLR_GREEN}✓ {nome_app} já está atualizado na versão mais recente.{CLR_RESET}")
        return True

if __name__ == "__main__":
    # Exibe diagnósticos
    exibir_diagnosticos()
    
    # Determina a opção e flags a partir de argumentos de linha de comando para automações
    opcao = None
    forcar_reinstalacao = False

    args = [arg.lower().strip("-") for arg in sys.argv[1:]]
    if "force" in args or "f" in args:
        forcar_reinstalacao = True
        args = [a for a in args if a not in ("force", "f")]

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
            
    if opcao is None:
        # Exibe menu de seleção se nenhum argumento válido for fornecido
        opcao = menu_selecao()
        
    if opcao == "4":
        opcao = "1"
        forcar_reinstalacao = True
    elif opcao == "6":
        print(f"\n{CLR_BLUE}Saindo sem realizar alterações.{CLR_RESET}\n")
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
