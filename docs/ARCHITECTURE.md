# Arquitetura

## Estado no M1

O repositório oferece duas interfaces compatíveis:

- `upgrade.py`: implementação principal em Python e alvo da modularização.
- `upgrade.sh`: implementação Bash mantida para compatibilidade temporária.

Ambas descobrem URLs na página oficial, baixam o pacote para uma sessão privada,
validam sua integridade e conteúdo, extraem em staging e atualizam um link
simbólico em `/opt/antigravity_apps`. A ativação do link ainda não é transacional;
esse limite será tratado no M3.

O módulo Python pode ser importado sem verificar privilégios ou criar diretórios.
Esses efeitos ficam restritos à execução do programa, permitindo testes locais
das funções de descoberta e apresentação.

## Direção planejada

A implementação Python será separada em componentes de CLI, descoberta remota,
download, validação, armazenamento de versões e integração com o sistema. Após
testes de paridade, `upgrade.sh` será reduzido a um wrapper da CLI canônica.

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
