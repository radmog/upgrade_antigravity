# Changelog

Todas as mudanças relevantes do projeto são registradas neste arquivo.

## 1.1.1

- Renomeia Hub para App em rótulos, menu, flags (`--app`) e configuração
  (`pin_app`); `--hub`, `hub` e `pin_hub` continuam aceitos.
- Adiciona o Antigravity CLI (`--cli`, `pin_cli`), instalado pelo manifesto
  oficial com verificação SHA-512, sem launcher.
- `--all` (App, IDE e CLI) passa a ser o alvo padrão; `--both` continua sendo
  App e IDE. Novos timers systemd executam `update --all`.
- Corrige as notas de versão: o changelog oficial migrou para `/docs/changelog`
  com novo HTML, e o parser agora lê `<article id="rel-<aba>-<versão>">`,
  aceitando versões com o build numérico anexado pelo download.
- Menu: a opção 17 instala apenas o CLI e **Sair** passa a ser a 18.
- Documenta a retomada de downloads, o formato HTML esperado pelo parser de
  notas e o comportamento de pins do CLI em arm64.

## 1.1.0

- Adiciona retomada de downloads interrompidos com HTTP `Range`, persistência
  privada entre execuções e validação de respostas truncadas.

## 1.0.1

- Restaura o diagnóstico de sistema e hardware antes do menu interativo.
- Mantém a saída de automações sem o diagnóstico adicional.

## 1.0.0

- Consolidação da interface interativa, com **Sair** como última opção.
- Matriz de CI para Python 3.9, 3.10, 3.11, 3.12 e 3.13.
- Documentação de compatibilidade, operação e recuperação.
- Metadados de pacote classificados como estáveis.

## 0.7.0

- Canais stable/preview, política notify-only e pins de versão.
- Configuração por escopo, cache HTTP, logs JSON e notificações desktop.

## 0.6.0

- Instalação por usuário, desinstalação segura e launchers XDG.
- Gerenciamento de serviço e timer systemd.

## 0.5.0

- CLI estruturada, consultas sem root e implementação Python canônica.
- Bash reduzido a wrapper de compatibilidade.

## 0.4.0

- Ativação transacional, health check, rollback e retenção de versões.
