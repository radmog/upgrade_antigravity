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
- **Integração com o Desktop**: Cria automaticamente arquivos `.desktop` no Desktop do usuário com o ícone oficial (baixado sob demanda) ou ícones de fallback locais, permitindo iniciar as aplicações diretamente pelo menu do sistema operacional.

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
> Como o diretório base de instalação é `/opt/antigravity_apps`, `update`,
> `rollback` e `prune` exigem privilégios administrativos. As consultas
> `current`, `list` e `changelog` podem ser executadas sem `sudo`.

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

---

## 🔄 Atualização Automática via Systemd (`systemctl`)

Para manter o Antigravity e o Antigravity IDE atualizados em segundo plano no Linux sem intervenção manual, você pode configurar um serviço de sistema no Systemd utilizando um **timer** ou uma **execução na inicialização**.

### Modos Possíveis de Configuração

#### Modo 1: Execução Periódica (Agendada via Systemd Timer)
Neste modo, o Systemd executa o script de atualização de forma recorrente (ex: diariamente ou semanalmente) em um horário específico ou após um intervalo de tempo regular.

1. **Criar o arquivo de serviço** (`/etc/systemd/system/antigravity-upgrade.service`):
   ```ini
   [Unit]
   Description=Serviço de Atualização Automática do Antigravity
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=oneshot
   # Ajuste o caminho para o local do seu script e selecione python3 ou bash
   ExecStart=/usr/bin/python3 /opt/antigravity_apps/upgrade.py update --both
   # O instalador atual grava em /opt e exige privilégios administrativos.
   User=root
   ```

2. **Criar o arquivo de timer** (`/etc/systemd/system/antigravity-upgrade.timer`):
   ```ini
   [Unit]
   Description=Timer para Atualização Automática do Antigravity

   [Timer]
   # Executa todos os dias às 02:00 da manhã
   OnCalendar=*-*-* 02:00:00
   # Garante que o serviço rodará mesmo se o computador estiver desligado no horário programado (roda logo após ligar)
   Persistent=true

   [Install]
   WantedBy=timers.target
   ```

3. **Habilitar e iniciar o timer**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now antigravity-upgrade.timer
   ```

#### Modo 2: Execução na Inicialização (Startup)
Neste modo, o script verifica se há atualizações disponíveis toda vez que o sistema operacional é inicializado e o acesso à rede está pronto.

1. **Criar o arquivo de serviço** (`/etc/systemd/system/antigravity-upgrade-startup.service`):
   ```ini
   [Unit]
   Description=Verificação de Atualização do Antigravity na Inicialização
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=oneshot
   ExecStart=/usr/bin/python3 /opt/antigravity_apps/upgrade.py update --both
   # O instalador atual grava em /opt e exige privilégios administrativos.
   User=root

   [Install]
   WantedBy=multi-user.target
   ```

2. **Habilitar o serviço**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable antigravity-upgrade-startup.service
   ```

---

### 📊 Monitoramento e Logs
Para verificar o status das execuções automáticas e acompanhar o andamento dos logs, use os comandos do `systemctl` e `journalctl`:

- **Verificar status do Timer/Serviço**:
  ```bash
  systemctl status antigravity-upgrade.timer
  systemctl status antigravity-upgrade.service
  ```
- **Visualizar os logs da última execução**:
  ```bash
  journalctl -u antigravity-upgrade.service -n 50
  ```

---

## 📁 Estrutura de Diretórios Gerada Localmente

Quando os scripts são executados, eles geram uma estrutura de arquivos local para organizar as versões instaladas. 

- `Antigravity/` - Link simbólico para a versão ativa do Antigravity Hub.
- `Antigravity_IDE/` - Link simbólico para a versão ativa do Antigravity IDE.
- `Antigravity_VERSOES/` - Pasta com as diferentes versões baixadas do Antigravity Hub.
- `Antigravity_IDE_VERSOES/` - Pasta com as diferentes versões baixadas do Antigravity IDE.

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
