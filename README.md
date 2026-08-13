# Antigravity Updater & Installer

Este repositório contém uma ferramenta para gerenciar, instalar e atualizar o **Antigravity** (Hub) e o **Antigravity IDE** em sistemas Linux. A implementação canônica usa **Python 3**; `upgrade.py` é a entrada principal e `upgrade.sh` é um wrapper de compatibilidade que encaminha os mesmos argumentos para a CLI Python.

A versão `1.0.1` é a release estável atual; `1.0.0` foi a primeira release estável. Consulte a
[matriz de compatibilidade](docs/COMPATIBILITY.md), o
[guia operacional](docs/OPERATIONS.md), o [processo de release](docs/RELEASING.md)
e o [changelog](CHANGELOG.md). O runtime suporta Python 3.9 a 3.13.

## ⚡ Funcionalidades Principais

- **Detecção Automática de Arquitetura**: Suporte para arquiteturas de 64 bits (`linux-x64`) e ARM (`linux-arm`).
- **Diagnóstico do Sistema**: Coleta e exibe especificações de hardware (sistema operacional, processador, threads da CPU, memória RAM em uso/total e espaço em disco disponível) em uma tabela visual elegante no terminal.
- **Web Scraping Dinâmico**: Realiza buscas automáticas na página oficial de downloads (`https://antigravity.google/download`) e rastreia scripts JavaScript referenciados para identificar as URLs e versões estáveis mais recentes.
- **Exibição de Datas e Horários**: Exibe a data/hora do lançamento da versão no servidor remoto (obtida via cabeçalho HTTP `Last-Modified`) e a data/hora de instalação da versão local presente na máquina.
- **Notas de Versão**: Busca o changelog oficial e exibe no terminal o resumo, as melhorias, as correções e os patches correspondentes exatamente à versão disponível de cada aplicativo.
- **Acesso Traduzido ao Changelog**: Detecta o idioma configurado no sistema e, quando ele não é inglês, disponibiliza um link do Google Tradutor para a aba oficial do produto no idioma local. Uma falha ao obter o changelog não bloqueia a instalação.
- **Forçar Reinstalação**: Permite forçar o re-download e a reinstalação dos aplicativos mesmo quando as versões local e remota coincidirem.
- **Instalação Protegida**: Usa uma sessão temporária privada, impede execuções concorrentes e nunca publica downloads parciais.
- **Retomada de Downloads**: Preserva pacotes interrompidos no estado privado do escopo e continua do último byte com HTTP `Range`, inclusive em uma execução posterior.
- **Integridade e Staging**: Calcula SHA-256, valida o checksum oficial quando disponível e extrai pacotes somente após inspeção de segurança.
- **Ativação Transacional**: Testa o executável, troca o link ativo atomicamente e restaura a versão anterior se o teste posterior falhar.
- **Rollback e Retenção**: Lista o histórico, permite selecionar uma versão anterior e remove versões antigas sem apagar a ativa ou a anterior.
- **Gerenciamento de Versões**: Mantém um histórico de versões instaladas dentro de subpastas específicas (ex: `Antigravity_VERSOES/Antigravity-X.Y.Z`).
- **Links Simbólicos Dinâmicos**: Atualiza um link simbólico que aponta sempre para a versão ativa/mais recente, garantindo que atalhos e referências ao executável nunca fiquem obsoletos.
- **Feedback Visual Avançado**: Inclui barras de progresso animadas para downloads e indicadores de carregamento (spinners) para operações de extração e linkagem.
- **Instalação por Usuário**: Usa diretórios XDG com `--user`, sem exigir root ou gravar em `/opt`.
- **Desinstalação Segura**: Remove apenas links, históricos, estados e launchers previamente validados como gerenciados.
- **Launchers XDG**: Publica atalhos no menu de aplicativos para o escopo selecionado.
- **Systemd Gerenciado**: Instala, consulta e remove serviço/timer pelo próprio comando.
- **Canais e Políticas**: Seleciona versões estáveis ou preview, permite pins e verificações sem instalação.
- **Configuração por Escopo**: Mantém preferências independentes para usuário e sistema.
- **Cache Resiliente**: Reutiliza metadados HTTP dentro do TTL e oferece fallback expirado quando a rede falha.
- **Observabilidade**: Registra eventos JSON rotativos e pode emitir notificações desktop.

---

## 🛠️ Arquivos do Repositório

### 1. [upgrade.py](upgrade.py)
Entrada compatível da CLI estruturada. A implementação está organizada no pacote [`antigravity_updater`](antigravity_updater), usando apenas a biblioteca padrão do Python em tempo de execução.

### 2. [upgrade.sh](upgrade.sh)
Wrapper Bash para automações existentes. Ele preserva os argumentos históricos, mas requer Python 3 e não duplica download, extração ou ativação.

---

## 🚀 Como Executar

Dê permissão de execução aos scripts antes do primeiro uso:

```bash
chmod +x upgrade.py upgrade.sh
```

As duas entradas requerem Python 3; nenhuma dependência Python externa é
necessária em tempo de execução.

> [!IMPORTANT]
> O escopo padrão é `--system`, que usa `/opt/antigravity_apps`; suas operações
> de escrita exigem privilégios administrativos. O escopo `--user` grava nos
> diretórios XDG do usuário e não exige `sudo`. `current`, `list`, `changelog` e
> `systemd status` são consultas e não elevam privilégios.

### Modo interativo

Sem argumentos, o menu usa o escopo de sistema. Use somente `--user` para abrir
o mesmo menu no escopo do usuário:

```bash
sudo ./upgrade.py
./upgrade.py --user
```

Antes de apresentar o menu, a ferramenta exibe o diagnóstico do sistema com
sistema operacional, arquitetura, processador, threads da CPU, uso e total de
memória RAM e espaço disponível e total em disco.

**Opções do menu:**

1. Instalar/Atualizar Ambos (Antigravity & Antigravity IDE)
2. Instalar/Atualizar Apenas Antigravity (Hub)
3. Instalar/Atualizar Apenas Antigravity IDE
4. Forçar Reinstalação de Ambos
5. Consultar Changelog Oficial (com tradução)
6. Verificar atualizações sem instalar
7. Mostrar versões ativas
8. Listar histórico de versões
9. Rollback de ambos para a versão anterior
10. Limpar histórico antigo
11. Mostrar configuração efetiva
12. Mostrar estado do cache
13. Mostrar logs recentes
14. Instalar/reconciliar launchers
15. Mostrar estado do timer systemd
16. Desinstalar ambos
17. **Sair**

`Sair` é sempre a última opção. A desinstalação pelo menu exige a confirmação
literal `REMOVER` antes de qualquer alteração.

### Modo Não Interativo / Automação (CLI)
A sintaxe canônica usa subcomandos:

```bash
# Para atualizar ambos
sudo ./upgrade.py update --both
sudo ./upgrade.sh update --both

# Instalar ambos somente para o usuário atual, sem sudo
./upgrade.py update --both --user

# Para atualizar apenas o Antigravity (Hub)
sudo ./upgrade.py update --hub

# Para atualizar apenas o Antigravity IDE
sudo ./upgrade.py update --ide

# Para forçar reinstalação de ambos (mesmo na mesma versão)
sudo ./upgrade.py update --both --force

# Para consultar as notas mais recentes sem instalar/atualizar
./upgrade.py changelog

# Verificar atualizações sem modificar a instalação
./upgrade.py check --both --user
```

As formas históricas (`--both`, `--hub`, `--ide`, `--reinstall`, `both` e
`force`) continuam aceitas pelas duas entradas. As opções numéricas seguem o
menu atual; por isso, `6` agora verifica atualizações e `17` encerra. Os aliases
textuais `exit` e `quit` continuam encerrando diretamente.

### Gerenciamento das versões instaladas

Os comandos abaixo não acessam a rede:

```bash
# Mostrar apenas as versões ativas
./upgrade.py current
./upgrade.sh current

# Listar todo o histórico; use --hub ou --ide para filtrar
./upgrade.py list --hub
./upgrade.sh list --ide

# Consultar a instalação do usuário em vez da instalação global
./upgrade.py current --user

# Voltar para a versão anterior registrada
sudo ./upgrade.py rollback --hub
sudo ./upgrade.sh rollback --hub

# Selecionar explicitamente uma versão
sudo ./upgrade.py rollback 2.5.0-5471848641724416 --hub

# Manter pelo menos duas versões por aplicativo
sudo ./upgrade.py prune 2
```

`prune` sempre preserva a versão ativa e a anterior disponível para rollback;
portanto, `--prune 1` ainda poderá conservar duas versões.

### Desinstalação e launchers

```bash
# Remover apenas a instalação do usuário
./upgrade.py uninstall --both --user

# Remover a instalação global
sudo ./upgrade.py uninstall --both --system

# Recriar ou remover launchers do menu de aplicativos
./upgrade.py launcher install --both --user
./upgrade.py launcher remove --both --user
```

Ao desinstalar ambos os aplicativos, um timer gerenciado no mesmo escopo também
é removido para evitar reinstalação automática. Use `--keep-systemd` para
preservá-lo.

---

## 🔄 Automação gerenciada com systemd

A própria CLI instala o serviço oneshot e o timer persistente. Mantenha o
repositório ou a instalação da CLI no mesmo caminho depois de criar as unidades.

```bash
# Timer diário do usuário, sem sudo
./upgrade.py systemd install --user

# Timer global; exige root
sudo ./upgrade.py systemd install --system

# Usar outra expressão OnCalendar
./upgrade.py systemd install --user --calendar "Mon..Fri 02:00"

# Consultar o timer
./upgrade.py systemd status --user
systemctl --user list-timers antigravity-upgrade.timer

# Remover serviço e timer
./upgrade.py systemd remove --user
```

No escopo de usuário, as unidades ficam em
`$XDG_CONFIG_HOME/systemd/user` (por padrão, `~/.config/systemd/user`) e executam
`systemctl --user`. No escopo global, ficam em `/etc/systemd/system`. O timer
preserva os caminhos XDG resolvidos durante a instalação e executa
`update --both` no mesmo escopo.

---

## ⚙️ Políticas, configuração e observabilidade

Cada escopo possui configuração independente. Para o usuário, o arquivo fica em
`$XDG_CONFIG_HOME/antigravity-updater/config.json`; para o sistema, em
`/etc/antigravity-updater/config.json`.

```bash
# Mostrar configuração efetiva e o caminho do arquivo
./upgrade.py config show --user
./upgrade.py config path --user

# Selecionar previews e apenas notificar, sem instalar
./upgrade.py config set channel preview --user
./upgrade.py config set policy notify-only --user

# Fixar uma versão do Hub; "none" remove o pin
./upgrade.py config set pin_hub 2.6.0-4603467860410368 --user
./upgrade.py config set pin_hub none --user

# Retenção, cache, logs e notificações
./upgrade.py config set retention 3 --user
./upgrade.py config set cache_ttl 3600 --user
./upgrade.py config set log_level INFO --user
./upgrade.py config set notifications auto --user

# Restaurar os padrões
./upgrade.py config reset --user
```

Chaves disponíveis:

| Chave | Valores | Padrão |
| --- | --- | --- |
| `channel` | `stable`, `preview` | `stable` |
| `policy` | `latest`, `notify-only` | `latest` |
| `retention` | 1 a 100 | 2 |
| `cache_ttl` | 0 a 604800 segundos | 3600 |
| `notifications` | `off`, `auto`, `desktop` | `off` |
| `log_level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `pin_hub`, `pin_ide` | versão exata ou `none` | `none` |

O canal `stable` ignora versões com marcadores de pré-lançamento. `preview`
também considera previews anunciados no catálogo oficial descoberto; ele não
inventa URLs nem troca para endpoints não publicados. A política `notify-only`
analisa e apresenta a versão candidata, mas termina antes de download, launcher
ou alteração local. O comando `check` sempre usa esse comportamento.

```bash
# Inspecionar e limpar o cache do usuário
./upgrade.py cache status --user
./upgrade.py cache clear --user

# Mostrar os 50 eventos JSON mais recentes
./upgrade.py logs --tail 50 --user
```

O cache e os logs do usuário ficam sob `$XDG_STATE_HOME/antigravity-updater`.
No escopo global, ficam em `/var/lib/antigravity-updater`. Metadados expirados
só são reutilizados quando uma nova busca falha; pacotes `.tar.gz` nunca entram
nesse cache. Defina `cache_ttl` como `0` para desabilitar leitura e escrita do
cache. Os logs giram em 1 MiB e mantêm três backups.

---

## 📁 Estrutura de diretórios

No escopo de sistema, o catálogo permanece em `/opt/antigravity_apps`. No
escopo de usuário, fica em
`$XDG_DATA_HOME/antigravity-updater/apps` (por padrão,
`~/.local/share/antigravity-updater/apps`). Dentro dele:

- `Antigravity/` — link simbólico para a versão ativa do Hub.
- `Antigravity_IDE/` — link simbólico para a versão ativa do IDE.
- `Antigravity_VERSOES/` — histórico validado do Hub.
- `Antigravity_IDE_VERSOES/` — histórico validado do IDE.

Os launchers globais ficam em `/usr/local/share/applications`; os launchers do
usuário ficam em `$XDG_DATA_HOME/applications`.

---

## 🧪 Desenvolvimento e Qualidade

O plano de evolução está documentado em [ROADMAP.md](ROADMAP.md), com os limites
de segurança atuais em [SECURITY.md](SECURITY.md) e a direção técnica em
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Procedimentos de produção estão em
[docs/OPERATIONS.md](docs/OPERATIONS.md).

Para executar as verificações Python em um ambiente virtual:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/pytest
.venv/bin/ruff check upgrade.py antigravity_updater tests
.venv/bin/mypy upgrade.py antigravity_updater
```

O wrapper Bash é verificado na integração contínua com `bash -n`, ShellCheck e
shfmt. O mesmo conjunto é executado automaticamente pelo workflow de qualidade.

---

## 📄 Licença

Este projeto está licenciado sob a licença MIT.
