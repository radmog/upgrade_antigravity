# Política de segurança

## Como reportar

Não publique detalhes de uma vulnerabilidade ainda não corrigida em uma issue
pública. Envie o relato ao mantenedor por um canal privado do perfil do projeto,
incluindo versão afetada, impacto e passos mínimos para reprodução.

## Escopo atual

As operações de instalação e gerenciamento são privilegiadas e devem ser
executadas somente a partir de uma cópia confiável deste repositório. Desde a
versão 0.3.0, cada atualização usa um diretório temporário privado e um lock
exclusivo. Downloads são
feitos em arquivo parcial, possuem limites, retries e SHA-256 calculado. Quando
o servidor publica `<URL>.sha256`, o checksum é obrigatório e validado antes da
publicação da versão.

Pacotes são inspecionados antes da extração, rejeitando path traversal, caminhos
absolutos, tipos especiais e links que escapem do staging. A versão só é movida
para o histórico depois da presença e permissão do executável esperado serem
confirmadas. Bits setuid e setgid são removidos.

Desde a versão 0.4.0, o executável é carregado em modo Node e precisa responder
ao health check antes e depois da ativação. O link ativo é trocado por rename
atômico; uma falha posterior restaura automaticamente a versão anterior. O
histórico ativo e anterior nunca é removido pela política de retenção.

Desde a versão 0.5.0, `current`, `list` e `changelog` podem ser executados sem
root. Os dois primeiros fazem somente leitura do catálogo local, e o terceiro
consulta apenas o endpoint público de notas de versão. `update`, `rollback` e
`prune` continuam exigindo root e usando o lock exclusivo antes de qualquer
alteração. O wrapper Bash não possui lógica privilegiada própria: ele encaminha
os argumentos para a implementação Python canônica.

Ainda não existe uma assinatura criptográfica independente: quando o servidor
não oferece checksum, o hash calculado serve para auditoria e detecção posterior,
mas não autentica a origem.
