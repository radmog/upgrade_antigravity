# Antigravity Updater & Installer

Este repositório contém uma ferramenta para gerenciar, instalar e atualizar o **Antigravity** (Hub) e o **Antigravity IDE** em sistemas Linux. A implementação canônica usa **Python 3**; `upgrade.py` é a entrada principal e `upgrade.sh` é um wrapper de compatibilidade que encaminha os mesmos argumentos para a CLI Python.

## ⚡ Funcionalidades Principais

- **Detecção Automática de Arquitetura**: Suporte para arquiteturas de 64 bits (`linux-x64`) e ARM (`linux-arm`).
- **Diagnóstico do Sistema**: Coleta e exibe especificações de hardware (sistema operacional, processador, threads da CPU, memória RAM em uso/total e espaço em disco disponível) em uma tabela visual elegante no terminal.
- **Web Scraping Dinâmico**: Realiza buscas automáticas na página oficial de downloads (`https://antigravity.google/download`) e rastreia scripts JavaScript referenciados para identificar as URLs e versões estáveis mais recentes.
- **Exibição de Datas e Horários**: Exibe a data/hora do lançamento da versão no servidor remoto (obtida via cabeçalho HTTP `Last-Modified`) e a data/hora de instalação da versão local presente na máquina.
- **Notas de Versão**: Busca o changelog oficial e exibe no terminal o resumo, as melhorias, as correções e os patches correspondentes exatamente à versão disponível de cada aplicativo.
- **Acesso Traduzido ao Changelog**: Detecta o idioma configurado no sistema e, quando ele não é inglês, disponibiliza um link do Google Tradutor para a aba oficial do produto no idioma local. Uma falha ao obter o changelog não bloqueia a instalação.
- **Forçar Reinstalação**: Permite forçar o re-download e a reinstalação dos aplicativos mesmo quando as versões local e remota coincidirem.
- **Instalação Protegida**: Usa uma sessão temporária privada, impede execuções concorrentes e nunca publica downloads parciais.
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

### Modo Interativo
Ao rodar qualquer um dos scripts sem argumentos com `sudo`, um menu de seleção interativo colorido será exibido no terminal:

```bash
sudo ./upgrade.py
# ou
sudo ./upgrade.sh
```

**Opções do Menu:**
1. Instalar/Atualizar Ambos (Antigravity & Antigravity IDE)
2. Instalar/Atualizar Apenas Antigravity (Hub)
3. Instalar/Atualizar Apenas Antigravity IDE
4. Forçar Reinstalação de Ambos (Mesmo na mesma versão)
5. Consultar Changelog Oficial (com tradução)
6. Sair
7. Mostrar versões ativas
8. Listar histórico de versões
9. Fazer rollback de ambos para a versão anterior
10. Limpar histórico antigo, preservando ativa e anterior

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
```

As formas históricas (`--both`, `--hub`, `--ide`, `--reinstall`, `both`,
`force` e opções numéricas) continuam aceitas pelas duas entradas.

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
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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
