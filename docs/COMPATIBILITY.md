# Matriz de compatibilidade

## Plataformas suportadas

| Componente | Suporte em 1.0.0 | Verificação |
| --- | --- | --- |
| Linux x86_64 | Suportado | Testes automatizados e uso do identificador `linux-x64` |
| Linux arm64/aarch64 | Suportado | Testes de detecção e uso do identificador `linux-arm` |
| Antigravity App e IDE | Suportado | Instalação por `.tar.gz` descoberto na página de downloads |
| Antigravity CLI, Linux x86_64 glibc | Suportado | Manifesto `linux_amd64`; instalação e health check verificados contra o serviço real |
| Antigravity CLI, Linux arm64 glibc | Compatível | Manifesto `linux_arm64` resolvido; sem execução em hardware arm64 |
| Antigravity CLI, Linux musl (x86_64/arm64) | Compatível | Detecção coberta por testes com mocks; sem execução em um sistema musl |
| Python 3.9–3.13 | Suportado | Matriz do GitHub Actions em todas as versões menores |
| Python 3.14 | Compatível | Suíte local completa; fora da matriz mínima da release |
| Bash | Wrapper compatível | `bash -n`, ShellCheck e shfmt no CI |
| systemd de sistema | Suportado | Unidades geradas e testes isolados |
| systemd de usuário | Suportado | Requer sessão com barramento de usuário ativo |
| Desktop XDG | Suportado | Launchers `.desktop` em escopo global ou do usuário |

macOS, Windows e sistemas sem `fcntl` não são suportados. O instalador depende
de semântica POSIX para lock, permissões, symlinks e ativação por rename.

## Dependências

O runtime usa apenas a biblioteca padrão do Python. `notify-send` é opcional e
necessário somente para notificações desktop. `systemctl` é necessário apenas
para o subcomando `systemd`. O wrapper `upgrade.sh` requer Bash e Python 3.

Os pacotes oficiais precisam estar disponíveis como `.tar.gz`. App e IDE contêm
o executável esperado na raiz após a remoção do primeiro componente do arquivo;
o pacote do CLI é plano e traz o executável `antigravity` diretamente na raiz.
O CLI não possui launcher por ser um aplicativo de terminal.

## Origens de rede

A ferramenta contata `antigravity.google` (página de downloads, scripts,
changelog em `/docs/changelog` e instalador do CLI), os hosts de download que a
página publica (`storage.googleapis.com` e `edgedl.me.gvt1.com` na data desta
revisão) e o serviço de manifestos do CLI, cuja base é lida do instalador. Todos
os acessos usam HTTPS; uma mudança nesses endereços pode exigir atualização.

## Níveis de verificação

- **Suportado:** contrato coberto pelo CI ou por testes automatizados específicos.
- **Compatível:** validado no desenvolvimento, mas não incluído na matriz mínima.
- **Não suportado:** fora do contrato da versão 1.0.0.
