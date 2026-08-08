# Arquitetura

## Estado na versão 0.5.0 (M4)

O repositório oferece duas entradas compatíveis para uma única implementação:

- `upgrade.py`: entrada histórica para a CLI Python canônica.
- `upgrade.sh`: wrapper Bash que preserva os comandos antigos.

O motor Python descobre URLs na página oficial, baixa o pacote para uma sessão
privada, valida sua integridade e conteúdo e extrai em staging. A versão
validada passa por health check antes e depois da troca atômica do link em
`/opt/antigravity_apps`; se a verificação posterior falhar, o link anterior é
restaurado automaticamente.

O pacote `antigravity_updater` separa a análise e política da CLI (`cli.py`) do
motor operacional (`core.py`). O módulo pode ser importado sem verificar
privilégios ou criar diretórios. A CLI classifica os comandos antes de provocar
efeitos: `current`, `list` e `changelog` são consultas sem root; `update`,
`rollback` e `prune` exigem root e lock exclusivo.

## Compatibilidade da CLI

A forma canônica usa subcomandos (`update`, `changelog`, `current`, `list`,
`rollback` e `prune`). A camada de normalização aceita as opções históricas,
incluindo `--both`, `--hub`, `--ide`, `--reinstall` e as opções numéricas do
menu. Tanto `upgrade.py` quanto `upgrade.sh` chegam ao mesmo parser e ao mesmo
motor, evitando divergência de segurança e comportamento entre linguagens.

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

Cada aplicativo possui um arquivo de estado privado em `/opt/antigravity_apps`,
além do `version.txt` e manifesto de cada versão. `current` e `list` consultam
esse catálogo; `rollback` ativa uma versão já validada usando a mesma transação.
`prune` preserva sempre a versão ativa e a anterior, mesmo quando o limite
solicitado for menor que dois.
