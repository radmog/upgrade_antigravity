# Arquitetura

## Estado na versão 1.0.0 (M7)

O repositório oferece duas entradas compatíveis para uma única implementação:

- `upgrade.py`: entrada histórica para a CLI Python canônica.
- `upgrade.sh`: wrapper Bash que preserva os comandos antigos.

O motor Python descobre URLs na página oficial, baixa o pacote para uma sessão
privada, valida sua integridade e conteúdo e extrai em staging. A versão
validada passa por health check antes e depois da troca atômica do link no
catálogo do escopo selecionado; se a verificação posterior falhar, o link
anterior é restaurado automaticamente.

O pacote `antigravity_updater` separa a análise e política da CLI (`cli.py`) do
motor operacional (`core.py`). `paths.py` resolve os escopos de instalação,
`settings.py` valida configuração, `cache.py` mantém metadados HTTP,
`observability.py` centraliza logs e notificações, e `systemd.py` gerencia as
unidades Linux. O pacote pode ser importado sem verificar privilégios ou criar
diretórios. A CLI
classifica os comandos antes de provocar
efeitos: `current`, `list` e `changelog` são consultas sem root; `update`,
`rollback`, `prune`, `uninstall` e `launcher` exigem root apenas no escopo de
sistema. Mutações no escopo do usuário usam um lock privado e não elevam
privilégios.

## Compatibilidade da CLI

A forma canônica usa subcomandos para atualização, consulta, histórico,
integração Linux, configuração, cache e logs. A camada de normalização aceita as opções históricas,
incluindo `--both`, `--hub`, `--ide`, `--reinstall` e as opções numéricas do
menu. Tanto `upgrade.py` quanto `upgrade.sh` chegam ao mesmo parser e ao mesmo
motor, evitando divergência de segurança e comportamento entre linguagens.

## Escopos e integração Linux do M5

O escopo `system`, padrão para compatibilidade, usa `/opt/antigravity_apps`,
`/run/lock`, `/usr/local/share/applications` e `/etc/systemd/system`. O escopo
`user` deriva dados, estado, configuração e launchers de `XDG_DATA_HOME`,
`XDG_STATE_HOME` e `XDG_CONFIG_HOME`, usando os fallbacks definidos pelo padrão
XDG sob o diretório pessoal.

Launchers apontam para o symlink ativo, portanto não precisam ser reescritos a
cada versão, embora a atualização os reconcilie automaticamente. A
desinstalação remove somente o link ativo validado, o histórico do aplicativo,
seu estado e launcher. Ao remover ambos os aplicativos, a CLI também desativa e
remove um timer gerenciado existente, salvo com `--keep-systemd`.

`systemd install` publica um serviço oneshot e um timer persistente no escopo
selecionado, executa `daemon-reload` e habilita o timer. No escopo de usuário, o
comando usa `systemctl --user` e grava no diretório de unidades XDG; no escopo
global, usa o gerenciador de sistema e requer root.

## Políticas e observabilidade do M6

Cada escopo possui configuração própria em JSON. O esquema fechado define canal
(`stable` ou `preview`), política (`latest` ou `notify-only`), retenção, TTL do
cache, notificações, nível de log e pins independentes para Hub e IDE. Opções da
CLI podem sobrescrever canal e política apenas durante uma execução.

A seleção de versão primeiro restringe aplicativo e arquitetura, depois aplica
o pin e o canal e, por fim, ordena os candidatos por versão. `stable` rejeita
marcadores de pré-lançamento; `preview` também considera esses candidatos. A
política `notify-only` encerra antes de qualquer download, launcher ou alteração
do catálogo. `check` força essa política e nunca exige root.

Páginas de download, scripts de metadados e changelog passam por um cache
textual com TTL. Hit, miss e fallback expirado são registrados no log. Pacotes
de instalação não entram nesse cache e continuam seguindo o pipeline protegido
de download e checksum.

Cada comando registra início e término em JSON Lines. Atualizações e verificações
também registram o resultado e podem emitir notificação desktop. Os arquivos de
log giram ao atingir 1 MiB, mantendo três backups; falhas de log ou notificação
não impedem a operação principal.

## Consolidação do M7

O menu interativo é derivado de uma única tabela ordenada de opções. A saída é
exclusivamente a última entrada, e cancelamentos por teclado convergem para essa
mesma ação. O escopo pode ser escolhido antes do menu com `--user` ou
`--system`; todas as ações geradas preservam essa escolha. A desinstalação
interativa exige confirmação antes de adquirir lock.

A compatibilidade Python passa a ser exercitada em matriz no CI, enquanto lint,
tipagem, verificações do wrapper e construção do wheel permanecem em um job de
qualidade separado. A release estável inclui documentação específica de
compatibilidade e operação.

## Pipeline de instalação do M2

1. O processo obtém lock exclusivo e cria uma sessão temporária com modo `0700`.
2. Metadados são buscados com timeout e retries.
3. O pacote é escrito como `.part`, limitado em tamanho e publicado apenas após
   o download completo e a verificação SHA-256, quando disponível.
4. O arquivo tar é validado e extraído em staging dentro do volume de versões.
5. O executável esperado e suas permissões são conferidos; bits privilegiados
   são removidos e um manifesto de instalação é gravado.
6. A pasta validada recebe um nome exclusivo quando já existe uma instalação da
   mesma versão, mantendo o destino ativo intacto.
7. O executável responde a `--version` com `ELECTRON_RUN_AS_NODE=1`; um symlink
   temporário é então renomeado atomicamente sobre o link ativo.
8. O health check é repetido pelo link público. Se falhar, o link anterior é
   restaurado. O estado `active`/`previous` só é registrado depois do sucesso.

## Catálogo e retenção do M3

Cada aplicativo possui um arquivo de estado privado no catálogo do escopo, além
do `version.txt` e manifesto de cada versão. `current` e `list` consultam esse
catálogo; `rollback` ativa uma versão já validada usando a mesma transação.
`prune` preserva sempre a versão ativa e a anterior, mesmo quando o limite
solicitado for menor que dois.
