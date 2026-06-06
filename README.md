# Antigravity Updater & Installer

Este repositório contém scripts de automação projetados para gerenciar, instalar e atualizar o **Antigravity** (Hub) e o **Antigravity IDE** em sistemas baseados em Linux. O projeto oferece duas implementações equivalentes: uma em **Python 3** (`upgrade.py`) e outra em **Bash Shell** (`upgrade.sh`), permitindo flexibilidade dependendo do ambiente e das ferramentas instaladas.

---

## ⚡ Funcionalidades Principais

- **Detecção Automática de Arquitetura**: Suporte para arquiteturas de 64 bits (`linux-x64`) e ARM (`linux-arm`).
- **Diagnóstico do Sistema**: Coleta e exibe especificações de hardware (sistema operacional, processador, threads da CPU, memória RAM em uso/total e espaço em disco disponível) em uma tabela visual elegante no terminal.
- **Web Scraping Dinâmico**: Realiza buscas automáticas na página oficial de downloads (`https://antigravity.google/download`) e rastreia scripts JavaScript referenciados para identificar as URLs e versões estáveis mais recentes.
- **Gerenciamento de Versões**: Mantém um histórico de versões instaladas dentro de subpastas específicas (ex: `Antigravity_VERSOES/Antigravity-X.Y.Z`).
- **Links Simbólicos Dinâmicos**: Atualiza um link simbólico que aponta sempre para a versão ativa/mais recente, garantindo que atalhos e referências ao executável nunca fiquem obsoletos.
- **Feedback Visual Avançado**: Inclui barras de progresso animadas para downloads e indicadores de carregamento (spinners) para operações de extração e linkagem.
- **Integração com o Desktop**: Cria automaticamente arquivos `.desktop` no Desktop do usuário com o ícone oficial (baixado sob demanda) ou ícones de fallback locais, permitindo iniciar as aplicações diretamente pelo menu do sistema operacional.

---

## 🛠️ Arquivos do Repositório

### 1. [upgrade.py](file:///opt/antigravity_apps/upgrade.py)
Script escrito em Python 3 utilizando apenas bibliotecas nativas (`urllib`, `tarfile`, `platform`, `threading`, etc.). Ideal para execução em ambientes que requerem multithreading para renderização do spinner animado ou processamento mais robusto.

### 2. [upgrade.sh](file:///opt/antigravity_apps/upgrade.sh)
Script escrito em Bash Shell. Ideal para automações em servidores, containers ou ambientes mínimos onde o Python não está disponível. Utiliza comandos utilitários como `curl` para downloads e processamento de texto tradicional para raspagem de dados.

---

## 🚀 Como Executar

Dê permissão de execução aos scripts antes do primeiro uso:

```bash
chmod +x upgrade.py upgrade.sh
```

> [!IMPORTANT]
Como o diretório base de instalação é `/opt/antigravity_apps`, os scripts **devem ser executados com privilégios de administrador (usando `sudo`)**. Os scripts possuem verificação nativa para garantir a execução correta e gerenciam automaticamente a propriedade do atalho criado na Área de Trabalho para que ele pertença ao seu usuário comum (não ao `root`).

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
4. Sair

### Modo Não Interativo / Automação (CLI)
Você pode passar a opção desejada como argumento ao invocar o comando com `sudo` para ignorar o menu interativo:

```bash
# Para atualizar ambos
sudo ./upgrade.py --both
sudo ./upgrade.sh both

# Para atualizar apenas o Antigravity (Hub)
sudo ./upgrade.py --hub
sudo ./upgrade.sh hub

# Para atualizar apenas o Antigravity IDE
sudo ./upgrade.py --ide
sudo ./upgrade.sh ide
```

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
   ExecStart=/usr/bin/python3 /opt/antigravity_apps/upgrade.py --both
   User=rguedes
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
   ExecStart=/usr/bin/python3 /opt/antigravity_apps/upgrade.py --both
   User=rguedes

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

## 📄 Licença

Este projeto está licenciado sob a licença MIT. 