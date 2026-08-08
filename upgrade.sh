#!/usr/bin/env bash

# Cores ANSI para a interface
CLR_RESET="\033[0m"
CLR_HEADER="\033[95m"
CLR_BLUE="\033[94m"
CLR_CYAN="\033[96m"
CLR_GREEN="\033[92m"
CLR_WARNING="\033[93m"
CLR_FAIL="\033[91m"
CLR_GRAY="\033[90m"
CLR_WHITE="\033[37m"

# Diretório base de instalação
DIRETORIO_BASE="/opt/antigravity_apps"
PASTA_TMP="/tmp/antigravity_upgrade"
URL_CHANGELOG="https://antigravity.google/changelog"

# Verificar privilégios de administrador (root)
if [ "$EUID" -ne 0 ]; then
    echo -e "${CLR_FAIL}Erro: Este script precisa ser executado com privilégios de administrador (root/sudo).${CLR_RESET}"
    echo -e "${CLR_WARNING}Por favor, execute novamente usando: sudo \$0${CLR_RESET}\n"
    exit 1
fi

# Detecta automaticamente a arquitetura do Ubuntu do usuário
ARCH_ATUAL=$(uname -m)
if [ "$ARCH_ATUAL" = "x86_64" ]; then
    ARCH_ALVO="linux-x64"
elif [ "$ARCH_ATUAL" = "aarch64" ] || [ "$ARCH_ATUAL" = "arm64" ]; then
    ARCH_ALVO="linux-arm"
else
    echo -e "${CLR_FAIL}Arquitetura não suportada: $ARCH_ATUAL${CLR_RESET}"
    exit 1
fi

# Criar os diretórios necessários
mkdir -p "$DIRETORIO_BASE"
mkdir -p "$PASTA_TMP"

# Função para spinner em segundo plano
iniciar_spinner() {
    local MSG="$1"
    (
        local chars="⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        while true; do
            for ((i=0; i<${#chars}; i++)); do
                echo -ne "\r${CLR_CYAN}${chars:$i:1} $MSG...${CLR_RESET}"
                sleep 0.08
            done
        done
    ) &
    SPINNER_PID=$!
}

parar_spinner() {
    local SUCESSO=$1
    local MSG="$2"
    kill "$SPINNER_PID" 2>/dev/null
    wait "$SPINNER_PID" 2>/dev/null
    echo -ne "\r\033[2K"
    if [ "$SUCESSO" = "0" ]; then
        echo -e "${CLR_GREEN}✓ $MSG${CLR_RESET}"
    else
        echo -e "${CLR_FAIL}✗ $MSG${CLR_RESET}"
    fi
}

# Detecta pt_BR.UTF-8 como "pt" e cria um link traduzido quando necessário.
obter_idioma_sistema() {
    local VALOR="${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}"
    VALOR="${VALOR%%.*}"
    VALOR="${VALOR%%_*}"
    VALOR="${VALOR%%-*}"
    VALOR=$(printf '%s' "$VALOR" | tr '[:upper:]' '[:lower:]')
    if [[ "$VALOR" =~ ^[a-z]{2,3}$ ]] && [ "$VALOR" != "posix" ]; then
        printf '%s' "$VALOR"
    else
        printf 'en'
    fi
}

obter_url_changelog() {
    local ABA="$1"
    local TRADUZIR="${2:-0}"
    local IDIOMA
    IDIOMA=$(obter_idioma_sistema)
    if [ "$TRADUZIR" -eq 1 ] && [ "$IDIOMA" != "en" ]; then
        printf 'https://translate.google.com/translate?sl=en&tl=%s&u=https%%3A%%2F%%2Fantigravity.google%%2Fchangelog%%3Ftab%%3D%s' "$IDIOMA" "$ABA"
    else
        printf '%s?tab=%s' "$URL_CHANGELOG" "$ABA"
    fi
}

exibir_notas_versao() {
    local NOME_APP="$1"
    local ABA="$2"
    local VERSAO="$3"
    local MARCADOR="href=\"/releases?tab=${ABA}&amp;version=${VERSAO}\""
    local NOTAS=""

    if [ -s "$PAGINA_CHANGELOG" ]; then
        # Cada registro começa em uma versão. Apenas o registro cujo link
        # contém simultaneamente a aba e a versão desejadas é processado.
        NOTAS=$(awk -v RS='<div class="section-row-wrapper"' -v marcador="$MARCADOR" '
            index($0, marcador) { print; exit }
        ' "$PAGINA_CHANGELOG" | sed \
            -e 's#<h3#\n<h3#g' -e 's#</h3>#</h3>\n#g' \
            -e 's#<div class="changes"#\n<div class="changes"#g' \
            -e 's#<p#\n<p#g' -e 's#</p>#</p>\n#g' \
            -e 's#<summary#\n<summary#g' -e 's#</summary>#</summary>\n#g' \
            -e 's#<li#\n<li#g' -e 's#</li>#</li>\n#g' | awk '
            function limpar(s) {
                gsub(/<[^>]*>/, "", s)
                gsub(/&amp;/, "\\&", s)
                gsub(/&quot;/, "\"", s)
                gsub(/&#39;|&#x27;/, "\047", s)
                gsub(/&lt;/, "<", s)
                gsub(/&gt;/, ">", s)
                gsub(/&nbsp;/, " ", s)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", s)
                return s
            }
            /<h3[ >]/ { texto=limpar($0); if (texto != "") print "T\t" texto }
            /<div class="changes"/ { em_resumo=1; next }
            em_resumo && /<p[ >]/ { texto=limpar($0); if (texto != "") print "R\t" texto; em_resumo=0 }
            /<summary[ >]/ { texto=limpar($0); if (texto != "") print "G\t" texto }
            /<li[ >]/ { texto=limpar($0); if (texto != "") print "I\t" texto }
        ')
    fi

    echo -e "\n  ${CLR_HEADER}Notas da versão $VERSAO — $NOME_APP${CLR_RESET}"
    if [ -n "$NOTAS" ]; then
        while IFS=$'\t' read -r TIPO TEXTO; do
            case "$TIPO" in
                T) echo -e "  ${CLR_WHITE}${TEXTO}${CLR_RESET}" ;;
                R) echo -e "  ${CLR_GRAY}${TEXTO}${CLR_RESET}" ;;
                G) echo -e "  ${CLR_CYAN}${TEXTO}:${CLR_RESET}" ;;
                I) echo -e "    ${CLR_WHITE}• ${TEXTO}${CLR_RESET}" ;;
            esac
        done <<< "$NOTAS"
    else
        echo -e "  ${CLR_WARNING}⚠ Não foram encontradas notas específicas para esta versão.${CLR_RESET}"
    fi

    echo -e "  ${CLR_BLUE}Changelog oficial: $(obter_url_changelog "$ABA")${CLR_RESET}"
    if [ "$(obter_idioma_sistema)" != "en" ]; then
        echo -e "  ${CLR_BLUE}Versão traduzida:  $(obter_url_changelog "$ABA" 1)${CLR_RESET}"
    fi
}

obter_versao_mais_recente() {
    local ABA="$1"
    [ -s "$PAGINA_CHANGELOG" ] || return 1
    grep -oE "href=\"/releases\?tab=${ABA}&amp;version=[^\"]+\"" "$PAGINA_CHANGELOG" |
        head -n 1 |
        sed -E 's/.*version=([^"&]+).*/\1/'
}

consultar_changelog() {
    local ENCONTRADOS=0
    local VERSAO

    echo -e "\n${CLR_HEADER}CHANGELOG OFICIAL — VERSÕES MAIS RECENTES${CLR_RESET}"
    VERSAO=$(obter_versao_mais_recente "hub")
    if [ -n "$VERSAO" ]; then
        exibir_notas_versao "Antigravity" "hub" "$VERSAO"
        ENCONTRADOS=1
    else
        echo -e "\n  ${CLR_WARNING}⚠ Não foi possível identificar a versão mais recente de Antigravity.${CLR_RESET}"
        echo -e "  ${CLR_BLUE}Changelog oficial: $(obter_url_changelog "hub")${CLR_RESET}"
    fi

    VERSAO=$(obter_versao_mais_recente "ide")
    if [ -n "$VERSAO" ]; then
        exibir_notas_versao "Antigravity_IDE" "ide" "$VERSAO"
        ENCONTRADOS=1
    else
        echo -e "\n  ${CLR_WARNING}⚠ Não foi possível identificar a versão mais recente de Antigravity_IDE.${CLR_RESET}"
        echo -e "  ${CLR_BLUE}Changelog oficial: $(obter_url_changelog "ide")${CLR_RESET}"
    fi

    [ "$ENCONTRADOS" -eq 1 ]
}

# Exibe diagnósticos de hardware e do sistema
exibir_diagnosticos() {
    # Coleta de dados
    local OS_INFO="$(uname -sr)"
    local ARCH_INFO="${ARCH_ALVO}"
    local CPU_MODEL=$(grep -m1 "model name" /proc/cpuinfo | cut -d: -f2 | xargs 2>/dev/null)
    local CORES=$(nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo 2>/dev/null)
    local CPU_INFO="$CPU_MODEL ($CORES threads)"

    local MEM_INFO="N/A"
    if [ -f /proc/meminfo ]; then
        local MEM_TOTAL=$(grep "MemTotal" /proc/meminfo | awk '{print $2}')
        local MEM_FREE=$(grep "MemAvailable" /proc/meminfo | awk '{print $2}')
        local MEM_TOTAL_MB=$((MEM_TOTAL / 1024))
        local MEM_USED_MB=$(((MEM_TOTAL - MEM_FREE) / 1024))
        MEM_INFO="Uso: ${MEM_USED_MB}MB / Total: ${MEM_TOTAL_MB}MB"
    fi

    local DISCO_LIVRE=$(df -h "$DIRETORIO_BASE" | tail -n 1 | awk '{print $4}')
    local DISCO_TOTAL=$(df -h "$DIRETORIO_BASE" | tail -n 1 | awk '{print $2}')
    local DISK_INFO="Disponível: $DISCO_LIVRE / Total: $DISCO_TOTAL"

    # Configuração de largura
    local LARGURA_TOTAL=78
    
    local LINHA_BORDAS=$(printf '═%.0s' {1..78})
    echo -e "\n${CLR_HEADER}╔${LINHA_BORDAS}╗${CLR_RESET}"
    
    local TITULO="DIAGNÓSTICOS DO SISTEMA"
    local ESPACO_TITULO=$(( (LARGURA_TOTAL - ${#TITULO}) / 2 ))
    local REM_TITULO=$(( LARGURA_TOTAL - ${#TITULO} - ESPACO_TITULO ))
    local PADDING_ESQ=$(printf ' %.0s' $(seq 1 $ESPACO_TITULO))
    local PADDING_DIR=$(printf ' %.0s' $(seq 1 $REM_TITULO))
    echo -e "${CLR_HEADER}║${CLR_RESET}${PADDING_ESQ}${TITULO}${PADDING_DIR}${CLR_HEADER}║${CLR_RESET}"
    echo -e "${CLR_HEADER}╠${LINHA_BORDAS}╣${CLR_RESET}"

    print_linha_tabela() {
        local LABEL="$1"
        local VALOR="$2"
        local CLR_VALOR="${3:-$CLR_WHITE}"

        local LABEL_STR=" ${LABEL}:"
        local COL1_LEN=24
        
        local MAX_VAL_LEN=$(( LARGURA_TOTAL - COL1_LEN - 2 ))
        if [ ${#VALOR} -gt $MAX_VAL_LEN ]; then
            VALOR="${VALOR:0:$((MAX_VAL_LEN-3))}..."
        fi

        local ESPACOS_RESTANTES=$(( LARGURA_TOTAL - COL1_LEN - ${#VALOR} ))
        
        local ESPACOS_COL1=$(( COL1_LEN - ${#LABEL_STR} ))
        local PADDING_COL1=""
        if [ $ESPACOS_COL1 -gt 0 ]; then
            PADDING_COL1=$(printf ' %.0s' $(seq 1 $ESPACOS_COL1))
        fi
        
        local PADDING_RESTANTE=""
        if [ $ESPACOS_RESTANTES -gt 0 ]; then
            PADDING_RESTANTE=$(printf ' %.0s' $(seq 1 $ESPACOS_RESTANTES))
        fi

        echo -e "${CLR_HEADER}║${CLR_RESET} ${CLR_GRAY}${LABEL}:${CLR_RESET}${PADDING_COL1}${CLR_VALOR}${VALOR}${CLR_RESET}${PADDING_RESTANTE}${CLR_HEADER}║${CLR_RESET}"
    }

    print_linha_tabela "Sistema Operacional" "$OS_INFO"
    print_linha_tabela "Arquitetura Alvo" "$ARCH_INFO" "$CLR_BLUE"
    print_linha_tabela "Processador (CPU)" "$CPU_INFO"
    print_linha_tabela "Memória RAM" "$MEM_INFO"
    print_linha_tabela "Espaço em Disco" "$DISK_INFO"

    echo -e "${CLR_HEADER}╚${LINHA_BORDAS}╝${CLR_RESET}\n"
}

# Menu de seleção
menu_selecao() {
    local LARGURA_TOTAL=78
    local LINHA_BORDAS=$(printf '═%.0s' {1..78})
    
    echo -e "${CLR_HEADER}╔${LINHA_BORDAS}╗${CLR_RESET}"
    local TITULO="MENU DE OPÇÕES DE ATUALIZAÇÃO"
    local ESPACO_TITULO=$(( (LARGURA_TOTAL - ${#TITULO}) / 2 ))
    local REM_TITULO=$(( LARGURA_TOTAL - ${#TITULO} - ESPACO_TITULO ))
    local PADDING_ESQ=$(printf ' %.0s' $(seq 1 $ESPACO_TITULO))
    local PADDING_DIR=$(printf ' %.0s' $(seq 1 $REM_TITULO))
    echo -e "${CLR_HEADER}║${CLR_RESET}${PADDING_ESQ}${TITULO}${PADDING_DIR}${CLR_HEADER}║${CLR_RESET}"
    echo -e "${CLR_HEADER}╠${LINHA_BORDAS}╣${CLR_RESET}"

    print_opcao() {
        local NUM="$1"
        local DESC="$2"
        # Sem cores isso tem largura: 2 (espaço) + 3 ("[%d]" % num) + 1 (espaço) + len(desc) = 6 + len(desc)
        local ESPACOS=$(( LARGURA_TOTAL - 6 - ${#DESC} ))
        local PADDING_RESTANTE=$(printf ' %.0s' $(seq 1 $ESPACOS))
        echo -e "${CLR_HEADER}║${CLR_RESET}  ${CLR_CYAN}[${NUM}]${CLR_WHITE} ${DESC}${CLR_RESET}${PADDING_RESTANTE}${CLR_HEADER}║${CLR_RESET}"
    }

    print_opcao 1 "Instalar/Atualizar Ambos (Antigravity & Antigravity IDE)"
    print_opcao 2 "Instalar/Atualizar Apenas Antigravity (Hub)"
    print_opcao 3 "Instalar/Atualizar Apenas Antigravity IDE"
    print_opcao 4 "Forçar Reinstalação de Ambos (Mesmo na mesma versão)"
    print_opcao 5 "Consultar Changelog Oficial (com tradução)"
    print_opcao 6 "Sair"
    echo -e "${CLR_HEADER}╚${LINHA_BORDAS}╝${CLR_RESET}"

    while true; do
        read -p "Digite sua escolha (1-6): " ESCOLHA
        case "$ESCOLHA" in
            1|2|3|4|5|6)
                OPCAO_SELECIONADA="$ESCOLHA"
                return
                ;;
            *)
                echo -e "${CLR_FAIL}Opção inválida! Escolha um número de 1 a 6.${CLR_RESET}"
                ;;
        esac
    done
}

# Cria atalho no Desktop do usuário
criar_atalho() {
    local NOME_APP="$1"
    
    local DESKTOP_DIR
    if [ -n "$SUDO_USER" ]; then
        DESKTOP_DIR=$(sudo -u "$SUDO_USER" xdg-user-dir DESKTOP 2>/dev/null || echo "/home/$SUDO_USER/Desktop")
    else
        DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
    fi
    
    if [ ! -d "$DESKTOP_DIR" ]; then
        return 1
    fi
    
    local SHORTCUT_PATH="$DESKTOP_DIR/${NOME_APP}.desktop"
    local EXEC_PATH
    local ICON_PATH
    
    local FALLBACK_ICON
    if [ "$NOME_APP" = "Antigravity" ]; then
        EXEC_PATH="$DIRETORIO_BASE/Antigravity/antigravity"
        ICON_PATH="$DIRETORIO_BASE/Antigravity/antigravity-logo.png"
        FALLBACK_ICON="$DIRETORIO_BASE/Antigravity_IDE/resources/app/out/vs/platform/browserOnboarding/static/antigravity.svg"
    else
        EXEC_PATH="$DIRETORIO_BASE/Antigravity_IDE/antigravity-ide"
        ICON_PATH="$DIRETORIO_BASE/Antigravity_IDE/antigravity-logo.png"
        FALLBACK_ICON="$DIRETORIO_BASE/Antigravity_IDE/resources/app/out/media/code-icon.svg"
    fi
    
    if [ ! -f "$ICON_PATH" ]; then
        # Baixa a imagem oficial do logo
        curl -sL "https://antigravity.google/assets/image/antigravity-logo.png" -o "$ICON_PATH"
        if [ $? -ne 0 ] || [ ! -s "$ICON_PATH" ]; then
            if [ -f "$FALLBACK_ICON" ]; then
                ICON_PATH="$FALLBACK_ICON"
            else
                ICON_PATH="system-run"
            fi
        fi
    fi
    
    iniciar_spinner "Criando atalho de desktop para $NOME_APP"
    
    cat <<EOF > "$SHORTCUT_PATH"
[Desktop Entry]
Version=1.0
Type=Application
Name=${NOME_APP//_/ }
Comment=Executar ${NOME_APP//_/ }
Exec="$EXEC_PATH"
Icon=$ICON_PATH
Terminal=false
Categories=Development;
EOF
    
    chmod +x "$SHORTCUT_PATH"
    if [ -n "$SUDO_USER" ]; then
        chown "$SUDO_USER:$SUDO_USER" "$SHORTCUT_PATH" 2>/dev/null
    fi
    
    if [ $? -eq 0 ]; then
        parar_spinner 0 "Atalho de desktop criado para $NOME_APP"
    else
        parar_spinner 1 "Erro ao criar atalho no desktop"
    fi
}

# Função interna para processar cada um dos aplicativos
atualizar_aplicativo() {
    local NOME_APP=$1
    local PADRAO_URL=$2
    local ABA_CHANGELOG=$3
    local FORCAR=${4:-0}

    echo -e "\n${CLR_BLUE}⚡ Analisando: $NOME_APP ($PADRAO_URL) ${CLR_RESET}"
    echo -e "  ${CLR_GRAY}----------------------------------------${CLR_RESET}"
    
    # 1. Extrai a URL exata
    URL_DOWNLOAD=$(grep -oE 'https://[^"]+\.tar\.gz' "$PAGINA_HTML" | grep "$PADRAO_URL" | grep "$ARCH_ALVO" | head -n 1)
    URL_DOWNLOAD=$(echo "$URL_DOWNLOAD" | sed 's/\\//g')

    if [ -z "$URL_DOWNLOAD" ]; then
        echo -e "  ${CLR_WARNING}⚠ Link de download não disponível para $NOME_APP ($ARCH_ALVO).${CLR_RESET}"
        return 1
    fi

    # 2. Extrair a versão
    VERSAO_WEB=$(echo "$URL_DOWNLOAD" | grep -oE '/[0-9]+\.[0-9]+\.[0-9]+[^/]*' | head -n 1 | tr -d '/')

    if [ -z "$VERSAO_WEB" ]; then
        echo -e "  ${CLR_WARNING}⚠ Não foi possível extrair a versão de $NOME_APP do link.${CLR_RESET}"
        return 1
    fi

    # Obter data/hora do arquivo no servidor remoto via HTTP HEAD
    LAST_MOD=$(curl -sI -A "Mozilla/5.0" "$URL_DOWNLOAD" | grep -i "^last-modified:" | cut -d':' -f2- | xargs 2>/dev/null)
    STR_DATA_WEB=""
    if [ -n "$LAST_MOD" ]; then
        DATA_SERVIDOR_FMT=$(date -d "$LAST_MOD" +"%d/%m/%Y %H:%M:%S" 2>/dev/null || echo "$LAST_MOD")
        STR_DATA_WEB=" (Lançado em: $DATA_SERVIDOR_FMT)"
    fi

    # 3. Verificar versão local atual e data de instalação
    PASTA_APP="$DIRETORIO_BASE/$NOME_APP"
    ARQUIVO_VERSAO_LOCAL="$PASTA_APP/version.txt"
    STR_DATA_LOCAL=""
    
    if [ -f "$ARQUIVO_VERSAO_LOCAL" ]; then
        VERSAO_LOCAL=$(cat "$ARQUIVO_VERSAO_LOCAL")
        DATA_LOCAL_FMT=$(date -r "$ARQUIVO_VERSAO_LOCAL" +"%d/%m/%Y %H:%M:%S" 2>/dev/null)
        if [ -n "$DATA_LOCAL_FMT" ]; then
            STR_DATA_LOCAL=" (Instalado em: $DATA_LOCAL_FMT)"
        fi
    else
        VERSAO_LOCAL="Nenhuma (Instalação Nova)"
    fi

    echo -e "  ${CLR_WHITE}Versão na Web: ${CLR_CYAN}$VERSAO_WEB${CLR_RESET}${CLR_GRAY}$STR_DATA_WEB${CLR_RESET}"
    echo -e "  ${CLR_WHITE}Versão Local:  ${CLR_GRAY}$VERSAO_LOCAL$STR_DATA_LOCAL${CLR_RESET}"
    exibir_notas_versao "$NOME_APP" "$ABA_CHANGELOG" "$VERSAO_WEB"

    # 4. Tomada de Decisão e Atualização
    if [ "$VERSAO_LOCAL" != "$VERSAO_WEB" ] || [ "$FORCAR" -eq 1 ]; then
        if [ "$VERSAO_LOCAL" = "$VERSAO_WEB" ] && [ "$FORCAR" -eq 1 ]; then
            echo -e "  ${CLR_WARNING}➜ Versões coincidem, mas a reinstalação foi forçada! Inicializando download...${CLR_RESET}"
        else
            echo -e "  ${CLR_WARNING}➜ Nova versão disponível! Inicializando download...${CLR_RESET}"
        fi
        
        ARQUIVO_TAR="$PASTA_TMP/$NOME_APP.tar.gz"
        echo -e "  ${CLR_BLUE}Baixando $NOME_APP...${CLR_RESET}"
        curl -L --progress-bar "$URL_DOWNLOAD" -o "$ARQUIVO_TAR"

        if [ $? -ne 0 ] || [ ! -s "$ARQUIVO_TAR" ]; then
            echo -e "  ${CLR_FAIL}Erro: Falha ao baixar o arquivo de $NOME_APP.${CLR_RESET}"
            return 1
        fi

        # Cria pasta específica da versão
        PASTA_NOVA_VERSAO="$DIRETORIO_BASE/${NOME_APP}_VERSOES/${NOME_APP}-$VERSAO_WEB"
        mkdir -p "$PASTA_NOVA_VERSAO"

        iniciar_spinner "Extraindo arquivos para ${NOME_APP}-$VERSAO_WEB"
        tar -xf "$ARQUIVO_TAR" -C "$PASTA_NOVA_VERSAO" --strip-components=1
        if [ $? -eq 0 ]; then
            parar_spinner 0 "Extraído com sucesso para: ${NOME_APP}-$VERSAO_WEB"
        else
            parar_spinner 1 "Falha ao extrair $NOME_APP"
            rm -rf "$PASTA_NOVA_VERSAO"
            return 1
        fi

        # Escreve a nova versão local
        echo "$VERSAO_WEB" > "$PASTA_NOVA_VERSAO/version.txt"

        # Atualiza o Link Simbólico principal (usando caminho relativo para evitar problemas de montagem/codificação)
        iniciar_spinner "Atualizando link simbólico do sistema"
        rm -rf "$PASTA_APP"
        
        # O link simbólico deve ser relativo à pasta onde está contido (DIRETORIO_BASE)
        local RELATIVE_TARGET="${NOME_APP}_VERSOES/${NOME_APP}-$VERSAO_WEB"
        ln -s "$RELATIVE_TARGET" "$PASTA_APP"
        if [ $? -eq 0 ]; then
            parar_spinner 0 "Link simbólico atualizado: $NOME_APP -> $RELATIVE_TARGET"
        else
            parar_spinner 1 "Erro ao criar link simbólico"
            return 1
        fi

        criar_atalho "$NOME_APP"
        echo -e "  ${CLR_GREEN}✓ $NOME_APP atualizado com sucesso!${CLR_RESET}"
    else
        criar_atalho "$NOME_APP"
        echo -e "  ${CLR_GREEN}✓ $NOME_APP já está atualizado na versão mais recente.${CLR_RESET}"
    fi
}

# --- Execução Principal ---

# Exibe diagnóstico do sistema
exibir_diagnosticos

# Determina a opção e flags a partir de argumentos de linha de comando para automações
OPCAO_SELECIONADA=""
FORCAR_REINSTALACAO=0

for arg in "$@"; do
    ARG_CLEAN=$(echo "$arg" | tr '[:upper:]' '[:lower:]' | sed 's/^-*//')
    if [ "$ARG_CLEAN" = "force" ] || [ "$ARG_CLEAN" = "f" ]; then
        FORCAR_REINSTALACAO=1
    elif [ -z "$OPCAO_SELECIONADA" ]; then
        case "$ARG_CLEAN" in
            1|both|all)
                OPCAO_SELECIONADA="1"
                ;;
            2|hub|antigravity)
                OPCAO_SELECIONADA="2"
                ;;
            3|ide|antigravity-ide)
                OPCAO_SELECIONADA="3"
                ;;
            4|reinstall)
                OPCAO_SELECIONADA="4"
                ;;
            5|changelog|changes|release-notes)
                OPCAO_SELECIONADA="5"
                ;;
            6|exit|quit)
                OPCAO_SELECIONADA="6"
                ;;
        esac
    fi
done

if [ -z "$OPCAO_SELECIONADA" ]; then
    # Exibe menu de escolhas se nenhum argumento válido for fornecido
    menu_selecao
fi

if [ "$OPCAO_SELECIONADA" = "4" ]; then
    OPCAO_SELECIONADA="1"
    FORCAR_REINSTALACAO=1
elif [ "$OPCAO_SELECIONADA" = "6" ]; then
    echo -e "\n${CLR_BLUE}Saindo sem realizar alterações.${CLR_RESET}\n"
    exit 0
fi

if [ "$OPCAO_SELECIONADA" = "5" ]; then
    iniciar_spinner "Buscando changelog oficial"
    PAGINA_CHANGELOG="$PASTA_TMP/changelog.html"
    curl -sL --compressed "$URL_CHANGELOG" -o "$PAGINA_CHANGELOG" 2>/dev/null
    if [ ! -s "$PAGINA_CHANGELOG" ]; then
        parar_spinner 1 "Falha ao buscar o changelog oficial"
        echo -e "${CLR_BLUE}Consulte: $(obter_url_changelog "hub")${CLR_RESET}"
        exit 1
    fi
    parar_spinner 0 "Changelog oficial carregado com sucesso!"
    consultar_changelog
    STATUS_CHANGELOG=$?
    rm -f "$PAGINA_CHANGELOG"
    exit "$STATUS_CHANGELOG"
fi

# Inicializa busca (scraping)
iniciar_spinner "Buscando versões e mapeando dependências dinâmicas"

PAGINA_RAW="$PASTA_TMP/download_raw.html"
PAGINA_HTML="$PASTA_TMP/download.html"
PAGINA_CHANGELOG="$PASTA_TMP/changelog.html"
curl -sL --compressed "https://antigravity.google/download" -o "$PAGINA_RAW"

if [ ! -s "$PAGINA_RAW" ]; then
    parar_spinner 1 "Falha ao buscar a página de downloads"
    exit 1
fi

# Extrai os links de arquivos JavaScript e junta todo o conteúdo em PAGINA_HTML
JS_FILES=$(grep -oE '(src|href)="[^"]+\.js"' "$PAGINA_RAW" | cut -d'"' -f2)
cat "$PAGINA_RAW" > "$PAGINA_HTML"
for js in $JS_FILES; do
    if [[ "$js" =~ ^https?:// ]]; then
        js_url="$js"
    else
        js_url="https://antigravity.google/${js#/}"
    fi
    curl -sL --compressed "$js_url" >> "$PAGINA_HTML" 2>/dev/null
done

# A ausência do changelog não bloqueia a instalação; a função de exibição
# mantém o link oficial como alternativa.
curl -sL --compressed "$URL_CHANGELOG" -o "$PAGINA_CHANGELOG" 2>/dev/null

parar_spinner 0 "Versões, links e changelog carregados com sucesso!"

# Processa a opção escolhida
SUCESSO=0
if [ "$OPCAO_SELECIONADA" = "1" ]; then
    atualizar_aplicativo "Antigravity" "antigravity-hub" "hub" "$FORCAR_REINSTALACAO"
    s1=$?
    atualizar_aplicativo "Antigravity_IDE" "stable" "ide" "$FORCAR_REINSTALACAO"
    s2=$?
    if [ $s1 -eq 0 ] && [ $s2 -eq 0 ]; then
        SUCESSO=0
    else
        SUCESSO=1
    fi
elif [ "$OPCAO_SELECIONADA" = "2" ]; then
    atualizar_aplicativo "Antigravity" "antigravity-hub" "hub" "$FORCAR_REINSTALACAO"
    SUCESSO=$?
elif [ "$OPCAO_SELECIONADA" = "3" ]; then
    atualizar_aplicativo "Antigravity_IDE" "stable" "ide" "$FORCAR_REINSTALACAO"
    SUCESSO=$?
fi

# Limpeza dos arquivos temporários
rm -f "$PAGINA_RAW" "$PAGINA_HTML" "$PAGINA_CHANGELOG"

if [ $SUCESSO -eq 0 ]; then
    echo -e "\n${CLR_HEADER}=======================================================${CLR_RESET}"
    echo -e "${CLR_GREEN}  Processo concluído com sucesso!                      ${CLR_RESET}"
    echo -e "${CLR_HEADER}=======================================================${CLR_RESET}"
fi
