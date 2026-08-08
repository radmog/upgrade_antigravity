# Política de segurança

## Como reportar

Não publique detalhes de uma vulnerabilidade ainda não corrigida em uma issue
pública. Envie o relato ao mantenedor por um canal privado do perfil do projeto,
incluindo versão afetada, impacto e passos mínimos para reprodução.

## Escopo atual

As operações de instalação e gerenciamento alteram executáveis e devem ser
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

Desde a versão 0.6.0, operações com `--user` gravam somente nos diretórios XDG
do usuário e usam um lock privado em `XDG_STATE_HOME`, sem elevar privilégios.
O escopo `--system` preserva os caminhos globais e continua exigindo root para
alterações. A desinstalação valida previamente links, histórico, estado e
launcher e recusa caminhos que não pertençam ao catálogo gerenciado.

Launchers são publicados atomicamente em `applications/` com modo `0644`. As
unidades systemd também são escritas atomicamente, rejeitam quebras de linha no
calendário e executam a mesma CLI com `NoNewPrivileges=true` e `UMask=0077`.
Timers de usuário registram os caminhos XDG resolvidos para não mudar o local de
instalação entre a sessão interativa e a execução agendada.

Desde a versão 0.7.0, a configuração passa por esquema fechado e validação de
tipos, limites e valores antes de influenciar uma atualização. Arquivos do
usuário usam modo `0600`; a configuração global, que não admite segredos, usa
`0644` para preservar consultas sem root. Pins não aceitam componentes de
caminho.

O cache usa nomes derivados de SHA-256 da URL, diretório `0700`, arquivos
`0600` e publicação por rename. Entradas só são aceitas quando corpo e metadados
regulares correspondem à URL solicitada. Conteúdo expirado é usado como fallback
somente quando uma nova busca falha. Logs JSONL são privados, rotativos e
recusam symlinks. Notificações usam `notify-send` com vetor de argumentos, sem
shell, têm timeout e nunca alteram o código de saída da operação principal.

Ainda não existe uma assinatura criptográfica independente: quando o servidor
não oferece checksum, o hash calculado serve para auditoria e detecção posterior,
mas não autentica a origem.
