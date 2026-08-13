# Guia operacional

## Instalação da ferramenta

O projeto pode ser executado diretamente de um clone estável:

```bash
git clone https://github.com/radmog/upgrade_antigravity.git
cd upgrade_antigravity
./upgrade.py --version
```

Também pode ser instalado a partir do wheel:

```bash
python3 -m pip install antigravity_updater-1.1.0-py3-none-any.whl
antigravity-upgrade --version
```

Mantenha o executável no mesmo caminho depois de instalar unidades systemd,
pois o serviço registra a entrada absoluta usada durante a instalação.

## Escolha de escopo

- `--user`: não exige root e usa diretórios XDG do usuário.
- `--system`: padrão compatível, grava em `/opt`, `/etc` e `/var/lib` e exige
  root para mutações.

Para abrir o menu no escopo de usuário:

```bash
./upgrade.py --user
```

Sem argumentos, o diagnóstico de sistema e hardware é exibido antes do menu,
incluindo sistema operacional, arquitetura, CPU, memória RAM e disco. O menu usa
o escopo de sistema. A opção **Sair** é sempre a
última da lista. A desinstalação pelo menu exige a confirmação literal
`REMOVER`.

## Rotina recomendada

```bash
# Consultar sem modificar
./upgrade.py check --both --user
./upgrade.py current --user

# Atualizar e inspecionar
./upgrade.py update --both --user
./upgrade.py list --user
./upgrade.py logs --tail 50 --user

# Recuperar a versão anterior
./upgrade.py rollback --both --user
```

Para automação, instale o timer no mesmo escopo da instalação:

```bash
./upgrade.py systemd install --user
./upgrade.py systemd status --user
```

## Diagnóstico e recuperação

### Outra atualização está em execução

Verifique o processo cujo PID está no arquivo de lock. Não apague o lock de um
processo ativo. Um arquivo remanescente não bloqueia por si só: o lock real é
mantido pelo kernel e será adquirido na próxima execução quando não houver
processo concorrente.

### Configuração inválida

```bash
./upgrade.py config path --user
./upgrade.py config reset --user
```

`reset` remove apenas a configuração; catálogo, cache e logs são preservados.

### Falha de rede

Consulte `logs` e `cache status`. Metadados expirados podem sustentar consultas
quando a rede falha, mas downloads de pacotes nunca usam o cache textual. Um
pacote interrompido permanece no subdiretório privado `downloads` do estado do
escopo (`/var/lib/antigravity-updater` no sistema ou o diretório XDG de estado
do usuário). A próxima atualização da mesma URL solicita somente os bytes
restantes; se o servidor não oferecer HTTP `Range`, o download recomeça de modo
seguro.

### Falha na ativação

O link anterior é restaurado automaticamente. Se a nova versão já tiver sido
publicada no histórico, ela permanecerá disponível para diagnóstico e poderá
ser removida posteriormente por `prune`.

### Timer reinstalando um aplicativo removido

Use `systemd remove` no mesmo escopo. `uninstall --both` remove automaticamente
um timer gerenciado, salvo quando `--keep-systemd` é informado.

## Backup e auditoria

Para preservar o estado operacional, copie o catálogo do escopo, o arquivo de
configuração e o diretório de estado. Não restaure symlinks ou arquivos de
estado apontando para fora do catálogo; a ferramenta os recusará.

Os manifestos `.install-manifest.json` registram origem, hash, versão e horário
de instalação. Logs são JSON Lines, giram em 1 MiB e mantêm três backups.
