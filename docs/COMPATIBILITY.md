# Matriz de compatibilidade

## Plataformas suportadas

| Componente | Suporte em 1.0.0 | Verificação |
| --- | --- | --- |
| Linux x86_64 | Suportado | Testes automatizados e uso do identificador `linux-x64` |
| Linux arm64/aarch64 | Suportado | Testes de detecção e uso do identificador `linux-arm` |
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

Os pacotes oficiais precisam estar disponíveis como `.tar.gz` e conter o
executável esperado na raiz após a remoção do primeiro componente do arquivo.

## Níveis de verificação

- **Suportado:** contrato coberto pelo CI ou por testes automatizados específicos.
- **Compatível:** validado no desenvolvimento, mas não incluído na matriz mínima.
- **Não suportado:** fora do contrato da versão 1.0.0.
