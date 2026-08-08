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
PASTA_TMP=""
ARQUIVO_LOCK="/run/lock/antigravity-updater.lock"
URL_CHANGELOG="https://antigravity.google/changelog"
MAX_DOWNLOAD_BYTES=$((4 * 1024 * 1024 * 1024))
MAX_EXTRACTED_BYTES=$((12 * 1024 * 1024 * 1024))
MAX_ARCHIVE_MEMBERS=200000

# Verificar privilégios de administrador (root)
if [ "$EUID" -ne 0 ]; then
    echo -e "${CLR_FAIL}Erro: Este script precisa ser executado com privilégios de administrador (root/sudo).${CLR_RESET}"
    echo -e "${CLR_WARNING}Por favor, execute novamente usando: sudo \$0${CLR_RESET}\n"
    exit 1
fi

for comando in curl tar flock mktemp sha256sum realpath timeout; do
    if ! command -v "$comando" >/dev/null 2>&1; then
        echo -e "${CLR_FAIL}Erro: dependência obrigatória não encontrada: $comando${CLR_RESET}"
        exit 1
    fi
done

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

# Criar uma sessão privada e impedir execuções concorrentes.
umask 077
mkdir -p "$DIRETORIO_BASE"
PASTA_TMP=$(mktemp -d "${TMPDIR:-/tmp}/antigravity-upgrade.XXXXXXXX") || exit 1
chmod 700 "$PASTA_TMP"

limpar_recursos() {
    if [ -n "${SPINNER_PID:-}" ]; then
        kill "$SPINNER_PID" 2>/dev/null || true
    fi
    if [ -n "$PASTA_TMP" ] && [ -d "$PASTA_TMP" ]; then
        rm -rf -- "$PASTA_TMP"
    fi
}
trap limpar_recursos EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

exec 9>"$ARQUIVO_LOCK"
chmod 600 "$ARQUIVO_LOCK"
if ! flock -n 9; then
    echo -e "${CLR_FAIL}Outra atualização do Antigravity já está em execução.${CLR_RESET}"
    exit 1
fi
printf '%s\n' "$$" 1>&9

curl_seguro() {
    curl --fail --show-error --location --retry 3 --retry-all-errors \
        --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 1800 "$@"
}

validar_url_download() {
    local URL="$1"
    [[ "$URL" =~ ^https://[^/@[:space:]]+(/[^[:space:]]*)?\.tar\.gz$ ]]
}

validar_pacote_tar() {
    local ARQUIVO="$1"
    local LISTA="$PASTA_TMP/tar-members.txt"
    local DETALHES="$PASTA_TMP/tar-details.txt"
    tar -tzf "$ARQUIVO" >"$LISTA" || return 1
    tar --numeric-owner -tvzf "$ARQUIVO" >"$DETALHES" || return 1

    if grep -Eq '(^/|(^|/)\.\.(/|$))' "$LISTA"; then
        echo "O pacote contém caminhos absolutos ou path traversal." >&2
        return 1
    fi
    if awk 'substr($1, 1, 1) ~ /^[bcp]$/ { found=1 } END { exit !found }' "$DETALHES"; then
        echo "O pacote contém dispositivos ou pipes especiais." >&2
        return 1
    fi
    if grep -Eq -- '( -> | link to )(/|([^/]+/)*\.\.(/|$))' "$DETALHES"; then
        echo "O pacote contém links que podem escapar do staging." >&2
        return 1
    fi

    local QUANTIDADE TAMANHO
    QUANTIDADE=$(wc -l <"$LISTA")
    TAMANHO=$(awk '{ if ($3 ~ /^[0-9]+$/) total += $3 } END { print total + 0 }' "$DETALHES")
    [ "$QUANTIDADE" -le "$MAX_ARCHIVE_MEMBERS" ] || return 1
    [ "$TAMANHO" -le "$MAX_EXTRACTED_BYTES" ] || return 1
}

pasta_versoes() {
    printf '%s/%s_VERSOES' "$DIRETORIO_BASE" "$1"
}

versao_ativa() {
    local NOME_APP="$1"
    local LINK="$DIRETORIO_BASE/$NOME_APP"
    local RAIZ DESTINO
    [ -L "$LINK" ] || return 1
    RAIZ=$(realpath -m "$(pasta_versoes "$NOME_APP")")
    DESTINO=$(realpath -e "$LINK" 2>/dev/null) || return 1
    case "$DESTINO/" in
        "$RAIZ"/*/) printf '%s\n' "$DESTINO" ;;
        *) return 1 ;;
    esac
}

versao_diretorio() {
    local DIRETORIO="$1"
    if [ -s "$DIRETORIO/version.txt" ]; then
        head -n 1 "$DIRETORIO/version.txt"
    else
        basename "$DIRETORIO" | sed -E 's/^[^-]+-//'
    fi
}

ler_estado_valor() {
    local NOME_APP="$1"
    local CHAVE="$2"
    local ESTADO="$DIRETORIO_BASE/.${NOME_APP}-state"
    local RELATIVO CANDIDATO RAIZ
    [ -f "$ESTADO" ] || return 1
    RELATIVO=$(sed -n "s/^${CHAVE}=//p" "$ESTADO" | head -n 1)
    [ -n "$RELATIVO" ] || return 1
    CANDIDATO=$(realpath -e "$DIRETORIO_BASE/$RELATIVO" 2>/dev/null) || return 1
    RAIZ=$(realpath -m "$(pasta_versoes "$NOME_APP")")
    case "$CANDIDATO/" in
        "$RAIZ"/*/) printf '%s\n' "$CANDIDATO" ;;
        *) return 1 ;;
    esac
}

gravar_estado() {
    local NOME_APP="$1"
    local ATIVO="$2"
    local ANTERIOR="${3:-}"
    local ESTADO="$DIRETORIO_BASE/.${NOME_APP}-state"
    local TEMPORARIO="${ESTADO}.tmp-$$"
    local ATIVO_RELATIVO ANTERIOR_RELATIVO=""
    ATIVO_RELATIVO=$(realpath --relative-to="$DIRETORIO_BASE" "$ATIVO") || return 1
    if [ -n "$ANTERIOR" ] && [ "$ANTERIOR" != "$ATIVO" ]; then
        ANTERIOR_RELATIVO=$(realpath --relative-to="$DIRETORIO_BASE" "$ANTERIOR") || return 1
    fi
    printf 'active=%s\n' "$ATIVO_RELATIVO" >"$TEMPORARIO"
    [ -n "$ANTERIOR_RELATIVO" ] && printf 'previous=%s\n' "$ANTERIOR_RELATIVO" >>"$TEMPORARIO"
    chmod 600 "$TEMPORARIO"
    mv -Tf -- "$TEMPORARIO" "$ESTADO"
}

testar_saude_versao() {
    local NOME_APP="$1"
    local DIRETORIO="$2"
    local EXECUTAVEL SAIDA
    if [ "$NOME_APP" = "Antigravity" ]; then
        EXECUTAVEL="$DIRETORIO/antigravity"
    else
        EXECUTAVEL="$DIRETORIO/antigravity-ide"
    fi
    [ -f "$EXECUTAVEL" ] && [ -x "$EXECUTAVEL" ] || return 1
    SAIDA=$(ELECTRON_RUN_AS_NODE=1 timeout 15 "$EXECUTAVEL" --version 2>"$PASTA_TMP/healthcheck.err") || return 1
    [ -n "$SAIDA" ] || return 1
    printf '%s\n' "$SAIDA" | head -n 1
}

trocar_link_atomico() {
    local NOME_APP="$1"
    local DESTINO="$2"
    local LINK="$DIRETORIO_BASE/$NOME_APP"
    local TEMPORARIO="$DIRETORIO_BASE/.${NOME_APP}.link-$$-$RANDOM"
    local RELATIVO RAIZ DESTINO_REAL
    if [ -e "$LINK" ] && [ ! -L "$LINK" ]; then
        echo "O caminho ativo não é um link simbólico gerenciado: $LINK" >&2
        return 1
    fi
    RAIZ=$(realpath -m "$(pasta_versoes "$NOME_APP")")
    DESTINO_REAL=$(realpath -e "$DESTINO") || return 1
    case "$DESTINO_REAL/" in
        "$RAIZ"/*/) ;;
        *) return 1 ;;
    esac
    RELATIVO=$(realpath --relative-to="$DIRETORIO_BASE" "$DESTINO_REAL") || return 1
    ln -s -- "$RELATIVO" "$TEMPORARIO" || return 1
    if ! mv -Tf -- "$TEMPORARIO" "$LINK"; then
        rm -f -- "$TEMPORARIO"
        return 1
    fi
}

ativar_versao_atomica() {
    local NOME_APP="$1"
    local DESTINO
    DESTINO=$(realpath -e "$2") || return 1
    local ANTERIOR="" ANTERIOR_ESTADO="" RUNTIME
    ANTERIOR=$(versao_ativa "$NOME_APP" 2>/dev/null || true)
    ANTERIOR_ESTADO=$(ler_estado_valor "$NOME_APP" previous 2>/dev/null || true)
    RUNTIME=$(testar_saude_versao "$NOME_APP" "$DESTINO") || return 1
    trocar_link_atomico "$NOME_APP" "$DESTINO" || return 1

    if ! testar_saude_versao "$NOME_APP" "$DIRETORIO_BASE/$NOME_APP" >/dev/null; then
        if [ -n "$ANTERIOR" ]; then
            trocar_link_atomico "$NOME_APP" "$ANTERIOR" || true
        else
            rm -f -- "$DIRETORIO_BASE/$NOME_APP"
        fi
        return 1
    fi
    if [ "$ANTERIOR" = "$DESTINO" ]; then
        ANTERIOR="$ANTERIOR_ESTADO"
    fi
    if ! gravar_estado "$NOME_APP" "$DESTINO" "$ANTERIOR"; then
        if [ -n "$ANTERIOR" ]; then
            trocar_link_atomico "$NOME_APP" "$ANTERIOR" || true
        else
            rm -f -- "$DIRETORIO_BASE/$NOME_APP"
        fi
        return 1
    fi
    printf '%s\n' "$RUNTIME"
}

listar_diretorios_versao() {
    local NOME_APP="$1"
    local RAIZ
    RAIZ=$(pasta_versoes "$NOME_APP")
    [ -d "$RAIZ" ] || return 0
    find "$RAIZ" -mindepth 1 -maxdepth 1 -type d ! -name '.*' -printf '%T@ %p\n' |
        sort -rn | cut -d' ' -f2-
}

exibir_estado_aplicativo() {
    local NOME_APP="$1"
    local DETALHADO="${2:-0}"
    local ATIVA="" DIRETORIO VERSAO MARCADOR
    ATIVA=$(versao_ativa "$NOME_APP" 2>/dev/null || true)
    if [ "$DETALHADO" -eq 0 ]; then
        if [ -n "$ATIVA" ]; then
            printf '%s: %s\n' "$NOME_APP" "$(versao_diretorio "$ATIVA")"
        else
            printf '%s: não instalada\n' "$NOME_APP"
        fi
        return
    fi
    printf '\n%s:\n' "$NOME_APP"
    if [ -z "$(listar_diretorios_versao "$NOME_APP")" ]; then
        printf '  Nenhuma versão instalada.\n'
        return
    fi
    while IFS= read -r DIRETORIO; do
        [ -n "$DIRETORIO" ] || continue
        VERSAO=$(versao_diretorio "$DIRETORIO")
        MARCADOR=" "
        [ "$DIRETORIO" = "$ATIVA" ] && MARCADOR="*"
        printf '  %s %s  (%s)\n' "$MARCADOR" "$VERSAO" "$(date -r "$DIRETORIO" '+%d/%m/%Y %H:%M:%S')"
    done < <(listar_diretorios_versao "$NOME_APP")
}

resolver_versao() {
    local NOME_APP="$1"
    local VERSAO_ALVO="$2"
    local DIRETORIO
    while IFS= read -r DIRETORIO; do
        [ "$(versao_diretorio "$DIRETORIO")" = "$VERSAO_ALVO" ] && {
            printf '%s\n' "$DIRETORIO"
            return 0
        }
    done < <(listar_diretorios_versao "$NOME_APP")
    return 1
}

rollback_aplicativo() {
    local NOME_APP="$1"
    local VERSAO_ALVO="${2:-}"
    local ATIVA DESTINO="" DIRETORIO RUNTIME
    ATIVA=$(versao_ativa "$NOME_APP" 2>/dev/null || true)
    if [ -n "$VERSAO_ALVO" ]; then
        DESTINO=$(resolver_versao "$NOME_APP" "$VERSAO_ALVO") || return 1
    else
        DESTINO=$(ler_estado_valor "$NOME_APP" previous 2>/dev/null || true)
        if [ -z "$DESTINO" ] || [ "$DESTINO" = "$ATIVA" ]; then
            while IFS= read -r DIRETORIO; do
                if [ "$DIRETORIO" != "$ATIVA" ]; then
                    DESTINO="$DIRETORIO"
                    break
                fi
            done < <(listar_diretorios_versao "$NOME_APP")
        fi
    fi
    [ -n "$DESTINO" ] && [ "$DESTINO" != "$ATIVA" ] || return 1
    RUNTIME=$(ativar_versao_atomica "$NOME_APP" "$DESTINO") || return 1
    printf '%s|%s\n' "$(versao_diretorio "$DESTINO")" "$RUNTIME"
}

podar_versoes() {
    local NOME_APP="$1"
    local MANTER="$2"
    [ "$MANTER" -ge 1 ] || return 1
    local ATIVA ANTERIOR DIRETORIO CONTAGEM=0
    declare -A PROTEGIDAS=()
    ATIVA=$(versao_ativa "$NOME_APP" 2>/dev/null || true)
    ANTERIOR=$(ler_estado_valor "$NOME_APP" previous 2>/dev/null || true)
    [ -n "$ATIVA" ] && PROTEGIDAS["$ATIVA"]=1
    [ -n "$ANTERIOR" ] && PROTEGIDAS["$ANTERIOR"]=1
    CONTAGEM=${#PROTEGIDAS[@]}
    while IFS= read -r DIRETORIO; do
        [ -n "$DIRETORIO" ] || continue
        if [ "$CONTAGEM" -lt "$MANTER" ] && [ -z "${PROTEGIDAS[$DIRETORIO]:-}" ]; then
            PROTEGIDAS["$DIRETORIO"]=1
            CONTAGEM=$((CONTAGEM + 1))
        fi
    done < <(listar_diretorios_versao "$NOME_APP")
    while IFS= read -r DIRETORIO; do
        [ -n "$DIRETORIO" ] || continue
        if [ -z "${PROTEGIDAS[$DIRETORIO]:-}" ]; then
            printf '%s\n' "$(versao_diretorio "$DIRETORIO")"
            rm -rf -- "$DIRETORIO"
        fi
    done < <(listar_diretorios_versao "$NOME_APP")
}

# Função para spinner em segundo plano
iniciar_spinner() {
    local MSG="$1"
    (
        local chars="⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        while true; do
            for ((i = 0; i < ${#chars}; i++)); do
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
    SPINNER_PID=""
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
        done <<<"$NOTAS"
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
    local ESPACO_TITULO=$(((LARGURA_TOTAL - ${#TITULO}) / 2))
    local REM_TITULO=$((LARGURA_TOTAL - ${#TITULO} - ESPACO_TITULO))
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

        local MAX_VAL_LEN=$((LARGURA_TOTAL - COL1_LEN - 2))
        if [ ${#VALOR} -gt $MAX_VAL_LEN ]; then
            VALOR="${VALOR:0:$((MAX_VAL_LEN - 3))}..."
        fi

        local ESPACOS_RESTANTES=$((LARGURA_TOTAL - COL1_LEN - ${#VALOR}))

        local ESPACOS_COL1=$((COL1_LEN - ${#LABEL_STR}))
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
    local ESPACO_TITULO=$(((LARGURA_TOTAL - ${#TITULO}) / 2))
    local REM_TITULO=$((LARGURA_TOTAL - ${#TITULO} - ESPACO_TITULO))
    local PADDING_ESQ=$(printf ' %.0s' $(seq 1 $ESPACO_TITULO))
    local PADDING_DIR=$(printf ' %.0s' $(seq 1 $REM_TITULO))
    echo -e "${CLR_HEADER}║${CLR_RESET}${PADDING_ESQ}${TITULO}${PADDING_DIR}${CLR_HEADER}║${CLR_RESET}"
    echo -e "${CLR_HEADER}╠${LINHA_BORDAS}╣${CLR_RESET}"

    print_opcao() {
        local NUM="$1"
        local DESC="$2"
        local ESPACOS=$((LARGURA_TOTAL - 5 - ${#NUM} - ${#DESC}))
        local PADDING_RESTANTE=$(printf ' %.0s' $(seq 1 $ESPACOS))
        echo -e "${CLR_HEADER}║${CLR_RESET}  ${CLR_CYAN}[${NUM}]${CLR_WHITE} ${DESC}${CLR_RESET}${PADDING_RESTANTE}${CLR_HEADER}║${CLR_RESET}"
    }

    print_opcao 1 "Instalar/Atualizar Ambos (Antigravity & Antigravity IDE)"
    print_opcao 2 "Instalar/Atualizar Apenas Antigravity (Hub)"
    print_opcao 3 "Instalar/Atualizar Apenas Antigravity IDE"
    print_opcao 4 "Forçar Reinstalação de Ambos (Mesmo na mesma versão)"
    print_opcao 5 "Consultar Changelog Oficial (com tradução)"
    print_opcao 6 "Sair"
    print_opcao 7 "Mostrar Versões Ativas"
    print_opcao 8 "Listar Histórico de Versões"
    print_opcao 9 "Rollback de Ambos para a Versão Anterior"
    print_opcao 10 "Limpar Histórico Antigo (Manter 2)"
    echo -e "${CLR_HEADER}╚${LINHA_BORDAS}╝${CLR_RESET}"

    while true; do
        read -r -p "Digite sua escolha (1-10): " ESCOLHA
        case "$ESCOLHA" in
            1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10)
                OPCAO_SELECIONADA="$ESCOLHA"
                return
                ;;
            *)
                echo -e "${CLR_FAIL}Opção inválida! Escolha um número de 1 a 10.${CLR_RESET}"
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
        curl_seguro --silent "https://antigravity.google/assets/image/antigravity-logo.png" -o "$ICON_PATH"
        if [ $? -ne 0 ] || [ ! -s "$ICON_PATH" ]; then
            if [ -f "$FALLBACK_ICON" ]; then
                ICON_PATH="$FALLBACK_ICON"
            else
                ICON_PATH="system-run"
            fi
        fi
    fi

    iniciar_spinner "Criando atalho de desktop para $NOME_APP"

    cat <<EOF >"$SHORTCUT_PATH"
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

    if ! validar_url_download "$URL_DOWNLOAD"; then
        echo -e "  ${CLR_FAIL}URL de download rejeitada por não ser HTTPS ou .tar.gz.${CLR_RESET}"
        return 1
    fi

    # 2. Extrair a versão
    VERSAO_WEB=$(echo "$URL_DOWNLOAD" | grep -oE '/[0-9]+\.[0-9]+\.[0-9]+[^/]*' | head -n 1 | tr -d '/')

    if [ -z "$VERSAO_WEB" ]; then
        echo -e "  ${CLR_WARNING}⚠ Não foi possível extrair a versão de $NOME_APP do link.${CLR_RESET}"
        return 1
    fi

    # Obter data/hora do arquivo no servidor remoto via HTTP HEAD
    LAST_MOD=$(curl_seguro --silent --head -A "Mozilla/5.0" "$URL_DOWNLOAD" 2>/dev/null | grep -i "^last-modified:" | cut -d':' -f2- | xargs 2>/dev/null)
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
        ARQUIVO_PARCIAL="${ARQUIVO_TAR}.part"
        CHECKSUM_ESPERADO=$(curl_seguro --silent "${URL_DOWNLOAD}.sha256" 2>/dev/null | grep -ioE '(^|[^0-9a-f])[0-9a-f]{64}([^0-9a-f]|$)' | grep -ioE '[0-9a-f]{64}' | head -n 1 || true)
        if [ -n "$CHECKSUM_ESPERADO" ]; then
            echo -e "  ${CLR_BLUE}SHA-256 oficial encontrado; o pacote será verificado.${CLR_RESET}"
        else
            echo -e "  ${CLR_WARNING}Checksum oficial não publicado; o SHA-256 local será registrado.${CLR_RESET}"
        fi
        echo -e "  ${CLR_BLUE}Baixando $NOME_APP...${CLR_RESET}"
        rm -f -- "$ARQUIVO_PARCIAL"
        curl_seguro --progress-bar --max-filesize "$MAX_DOWNLOAD_BYTES" "$URL_DOWNLOAD" -o "$ARQUIVO_PARCIAL"

        if [ $? -ne 0 ] || [ ! -s "$ARQUIVO_PARCIAL" ]; then
            rm -f -- "$ARQUIVO_PARCIAL"
            echo -e "  ${CLR_FAIL}Erro: Falha ao baixar o arquivo de $NOME_APP.${CLR_RESET}"
            return 1
        fi

        TAMANHO_DOWNLOAD=$(stat -c %s "$ARQUIVO_PARCIAL" 2>/dev/null || echo 0)
        if [ "$TAMANHO_DOWNLOAD" -gt "$MAX_DOWNLOAD_BYTES" ]; then
            rm -f -- "$ARQUIVO_PARCIAL"
            echo -e "  ${CLR_FAIL}Erro: O pacote excede o limite máximo permitido.${CLR_RESET}"
            return 1
        fi
        SHA256_LOCAL=$(sha256sum "$ARQUIVO_PARCIAL" | awk '{print $1}')
        if [ -n "$CHECKSUM_ESPERADO" ] && [ "${SHA256_LOCAL,,}" != "${CHECKSUM_ESPERADO,,}" ]; then
            rm -f -- "$ARQUIVO_PARCIAL"
            echo -e "  ${CLR_FAIL}Erro: O SHA-256 não corresponde ao checksum publicado.${CLR_RESET}"
            return 1
        fi
        mv -f -- "$ARQUIVO_PARCIAL" "$ARQUIVO_TAR"

        # Extrai em staging privado e somente publica uma instalação validada.
        PASTA_VERSOES="$DIRETORIO_BASE/${NOME_APP}_VERSOES"
        PASTA_NOVA_VERSAO="$PASTA_VERSOES/${NOME_APP}-$VERSAO_WEB"
        mkdir -p "$PASTA_VERSOES"
        if [ -e "$PASTA_NOVA_VERSAO" ] || [ -L "$PASTA_NOVA_VERSAO" ]; then
            PASTA_NOVA_VERSAO="${PASTA_NOVA_VERSAO}-reinstall-$(date +%s%N)"
        fi
        STAGING=$(mktemp -d "$PASTA_VERSOES/.${NOME_APP}-${VERSAO_WEB}.XXXXXXXX") || return 1

        iniciar_spinner "Extraindo arquivos para ${NOME_APP}-$VERSAO_WEB"
        if ! validar_pacote_tar "$ARQUIVO_TAR" || ! (umask 022 && tar -xzf "$ARQUIVO_TAR" -C "$STAGING" \
            --strip-components=1 --no-same-owner --no-same-permissions --delay-directory-restore); then
            parar_spinner 1 "Falha ao extrair $NOME_APP"
            rm -rf -- "$STAGING"
            return 1
        fi

        if [ "$NOME_APP" = "Antigravity" ]; then
            EXECUTAVEL_ESPERADO="$STAGING/antigravity"
        else
            EXECUTAVEL_ESPERADO="$STAGING/antigravity-ide"
        fi
        if [ ! -f "$EXECUTAVEL_ESPERADO" ] || [ ! -x "$EXECUTAVEL_ESPERADO" ]; then
            parar_spinner 1 "Pacote inválido: executável esperado ausente ou sem permissão"
            rm -rf -- "$STAGING"
            return 1
        fi
        chmod 755 "$STAGING"
        find "$STAGING" -xdev -perm /6000 -exec chmod a-s {} +

        echo "$VERSAO_WEB" >"$STAGING/version.txt"
        CHECKSUM_VERIFICADO=false
        [ -n "$CHECKSUM_ESPERADO" ] && CHECKSUM_VERIFICADO=true
        DATA_INSTALACAO=$(date --iso-8601=seconds)
        printf '{\n  "app": "%s",\n  "version": "%s",\n  "source_url": "%s",\n  "sha256": "%s",\n  "checksum_verified": %s,\n  "installed_at": "%s"\n}\n' \
            "$NOME_APP" "$VERSAO_WEB" "$URL_DOWNLOAD" "$SHA256_LOCAL" "$CHECKSUM_VERIFICADO" "$DATA_INSTALACAO" \
            >"$STAGING/.install-manifest.json"

        if ! mv -- "$STAGING" "$PASTA_NOVA_VERSAO"; then
            parar_spinner 1 "Falha ao publicar a versão validada"
            return 1
        fi
        parar_spinner 0 "Extraído e validado com sucesso: ${NOME_APP}-$VERSAO_WEB"

        iniciar_spinner "Testando e ativando a nova versão atomicamente"
        local RUNTIME
        RUNTIME=$(ativar_versao_atomica "$NOME_APP" "$PASTA_NOVA_VERSAO")
        if [ $? -ne 0 ]; then
            parar_spinner 1 "Falha ao ativar $NOME_APP; versão anterior preservada"
            return 1
        fi
        parar_spinner 0 "Versão ativada e saudável ($RUNTIME)"

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
COMANDO_GERENCIAMENTO=""

for arg in "$@"; do
    ARG_CLEAN=$(echo "$arg" | tr '[:upper:]' '[:lower:]' | sed 's/^-*//')
    case "$ARG_CLEAN" in
        current | list | rollback | prune)
            COMANDO_GERENCIAMENTO="$ARG_CLEAN"
            break
            ;;
    esac
done

if [ -n "$COMANDO_GERENCIAMENTO" ]; then
    SELECIONA_HUB=0
    SELECIONA_IDE=0
    PARAMETRO=""
    PROXIMO_E_PARAMETRO=0
    for arg in "$@"; do
        ARG_CLEAN=$(echo "$arg" | tr '[:upper:]' '[:lower:]' | sed 's/^-*//')
        case "$ARG_CLEAN" in
            hub | antigravity) SELECIONA_HUB=1 ;;
            ide | antigravity-ide) SELECIONA_IDE=1 ;;
            "$COMANDO_GERENCIAMENTO") PROXIMO_E_PARAMETRO=1 ;;
            *)
                if [ "$PROXIMO_E_PARAMETRO" -eq 1 ]; then
                    PARAMETRO="$ARG_CLEAN"
                    PROXIMO_E_PARAMETRO=0
                fi
                ;;
        esac
    done
    if [ "$SELECIONA_HUB" -eq 0 ] && [ "$SELECIONA_IDE" -eq 0 ]; then
        SELECIONA_HUB=1
        SELECIONA_IDE=1
    fi
    if [ "$COMANDO_GERENCIAMENTO" = "rollback" ] && [ -n "$PARAMETRO" ] &&
        [ "$SELECIONA_HUB" -eq 1 ] && [ "$SELECIONA_IDE" -eq 1 ]; then
        echo -e "${CLR_FAIL}Informe hub ou ide ao solicitar uma versão específica.${CLR_RESET}"
        exit 1
    fi

    STATUS_GERENCIAMENTO=0
    for NOME_GERENCIADO in $([ "$SELECIONA_HUB" -eq 1 ] && printf 'Antigravity ') $([ "$SELECIONA_IDE" -eq 1 ] && printf 'Antigravity_IDE'); do
        case "$COMANDO_GERENCIAMENTO" in
            current) exibir_estado_aplicativo "$NOME_GERENCIADO" ;;
            list) exibir_estado_aplicativo "$NOME_GERENCIADO" 1 ;;
            rollback)
                RESULTADO_ROLLBACK=$(rollback_aplicativo "$NOME_GERENCIADO" "$PARAMETRO") || {
                    echo -e "${CLR_FAIL}Falha ao reverter $NOME_GERENCIADO.${CLR_RESET}"
                    STATUS_GERENCIAMENTO=1
                    continue
                }
                IFS='|' read -r VERSAO_ROLLBACK RUNTIME_ROLLBACK <<<"$RESULTADO_ROLLBACK"
                echo -e "${CLR_GREEN}✓ $NOME_GERENCIADO revertido para $VERSAO_ROLLBACK ($RUNTIME_ROLLBACK).${CLR_RESET}"
                ;;
            prune)
                MANTER="${PARAMETRO:-2}"
                if ! [[ "$MANTER" =~ ^[0-9]+$ ]] || [ "$MANTER" -lt 1 ]; then
                    echo -e "${CLR_FAIL}A retenção precisa ser um número maior ou igual a 1.${CLR_RESET}"
                    exit 1
                fi
                REMOVIDAS=$(podar_versoes "$NOME_GERENCIADO" "$MANTER") || {
                    STATUS_GERENCIAMENTO=1
                    continue
                }
                [ -n "$REMOVIDAS" ] || REMOVIDAS="nenhuma"
                echo "$NOME_GERENCIADO: versões removidas: ${REMOVIDAS//$'\n'/, }"
                ;;
        esac
    done
    exit "$STATUS_GERENCIAMENTO"
fi

for arg in "$@"; do
    ARG_CLEAN=$(echo "$arg" | tr '[:upper:]' '[:lower:]' | sed 's/^-*//')
    if [ "$ARG_CLEAN" = "force" ] || [ "$ARG_CLEAN" = "f" ]; then
        FORCAR_REINSTALACAO=1
    elif [ -z "$OPCAO_SELECIONADA" ]; then
        case "$ARG_CLEAN" in
            1 | both | all)
                OPCAO_SELECIONADA="1"
                ;;
            2 | hub | antigravity)
                OPCAO_SELECIONADA="2"
                ;;
            3 | ide | antigravity-ide)
                OPCAO_SELECIONADA="3"
                ;;
            4 | reinstall)
                OPCAO_SELECIONADA="4"
                ;;
            5 | changelog | changes | release-notes)
                OPCAO_SELECIONADA="5"
                ;;
            6 | exit | quit)
                OPCAO_SELECIONADA="6"
                ;;
            7 | 8 | 9 | 10)
                OPCAO_SELECIONADA="$ARG_CLEAN"
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

if [[ "$OPCAO_SELECIONADA" =~ ^(7|8|9|10)$ ]]; then
    STATUS_GERENCIAMENTO=0
    for NOME_GERENCIADO in Antigravity Antigravity_IDE; do
        case "$OPCAO_SELECIONADA" in
            7) exibir_estado_aplicativo "$NOME_GERENCIADO" ;;
            8) exibir_estado_aplicativo "$NOME_GERENCIADO" 1 ;;
            9)
                RESULTADO_ROLLBACK=$(rollback_aplicativo "$NOME_GERENCIADO") || {
                    echo -e "${CLR_FAIL}Falha ao reverter $NOME_GERENCIADO.${CLR_RESET}"
                    STATUS_GERENCIAMENTO=1
                    continue
                }
                IFS='|' read -r VERSAO_ROLLBACK RUNTIME_ROLLBACK <<<"$RESULTADO_ROLLBACK"
                echo -e "${CLR_GREEN}✓ $NOME_GERENCIADO revertido para $VERSAO_ROLLBACK ($RUNTIME_ROLLBACK).${CLR_RESET}"
                ;;
            10)
                REMOVIDAS=$(podar_versoes "$NOME_GERENCIADO" 2) || {
                    STATUS_GERENCIAMENTO=1
                    continue
                }
                [ -n "$REMOVIDAS" ] || REMOVIDAS="nenhuma"
                echo "$NOME_GERENCIADO: versões removidas: ${REMOVIDAS//$'\n'/, }"
                ;;
        esac
    done
    exit "$STATUS_GERENCIAMENTO"
fi

if [ "$OPCAO_SELECIONADA" = "5" ]; then
    iniciar_spinner "Buscando changelog oficial"
    PAGINA_CHANGELOG="$PASTA_TMP/changelog.html"
    curl_seguro --silent --compressed "$URL_CHANGELOG" -o "$PAGINA_CHANGELOG" 2>/dev/null
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
curl_seguro --silent --compressed "https://antigravity.google/download" -o "$PAGINA_RAW"

if [ ! -s "$PAGINA_RAW" ]; then
    parar_spinner 1 "Falha ao buscar a página de downloads"
    exit 1
fi

# Extrai os links de arquivos JavaScript e junta todo o conteúdo em PAGINA_HTML
JS_FILES=$(grep -oE '(src|href)="[^"]+\.js"' "$PAGINA_RAW" | cut -d'"' -f2)
cat "$PAGINA_RAW" >"$PAGINA_HTML"
for js in $JS_FILES; do
    if [[ "$js" =~ ^https?:// ]]; then
        js_url="$js"
    else
        js_url="https://antigravity.google/${js#/}"
    fi
    curl_seguro --silent --compressed "$js_url" >>"$PAGINA_HTML" 2>/dev/null
done

# A ausência do changelog não bloqueia a instalação; a função de exibição
# mantém o link oficial como alternativa.
curl_seguro --silent --compressed "$URL_CHANGELOG" -o "$PAGINA_CHANGELOG" 2>/dev/null

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
else
    echo -e "\n${CLR_FAIL}Processo concluído com falhas.${CLR_RESET}"
fi

exit "$SUCESSO"
