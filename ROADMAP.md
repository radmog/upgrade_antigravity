# Roadmap

O projeto evoluirá em marcos pequenos, mantendo compatibilidade com a interface
existente até que uma migração seja documentada.

## M1 — Qualidade e comportamento básico (0.2.0)

- [x] Testes de caracterização para arquitetura, idioma, changelog e privilégios.
- [x] Fixtures locais independentes da internet.
- [x] Códigos de saída confiáveis para automação.
- [x] Configuração de pytest, Ruff, mypy, ShellCheck e shfmt.
- [x] CI e documentação inicial de arquitetura e segurança.
- [x] Exemplos de systemd compatíveis com a exigência atual de root.

## M2 — Segurança e staging (0.3.0)

- [x] Diretório temporário privado e lock de execução.
- [x] Download resiliente com arquivo parcial e validação de integridade.
- [x] Extração segura em staging e validação do pacote.

## M3 — Atualização transacional (0.4.0)

- [x] Ativação atômica, teste de saúde e rollback.
- [x] Listagem, seleção e retenção de versões.

## M4 — CLI e implementação canônica (0.5.0)

- [x] CLI estruturada e consultas sem root.
- [x] Módulos internos coesos e Bash como wrapper de compatibilidade.

## M5 — Integração com Linux (0.6.0)

- [x] Instalação por usuário, desinstalação, launchers e systemd gerenciado.

## M6 — Políticas e observabilidade (0.7.0)

- [x] Canais, política de versões, configuração, logs, notificações e cache.

## M7 — Consolidação (1.0.0)

- [x] Matriz de compatibilidade, documentação operacional e release estável.
