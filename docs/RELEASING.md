# Processo de release

## Checklist

1. Confirme que `pyproject.toml` e `antigravity_updater.__version__` possuem a
   mesma versão.
2. Atualize `CHANGELOG.md`, roadmap e documentação operacional.
3. Execute localmente:

   ```bash
   pytest
   ruff check upgrade.py antigravity_updater tests
   mypy upgrade.py antigravity_updater
   bash -n upgrade.sh
   shellcheck -S error upgrade.sh
   shfmt -d -i 4 -ci upgrade.sh
   python3 -m pip wheel --no-deps --wheel-dir dist .
   ```

4. Envie o commit e aguarde todos os jobs da matriz do GitHub Actions.
5. Crie uma tag anotada `vX.Y.Z` apontando para o commit validado.
6. Publique o wheel gerado pelo mesmo commit e anexe as notas do changelog.

Nunca crie ou mova uma tag estável antes da conclusão do CI. Tags publicadas não
devem ser reutilizadas para outro commit.

## Versionamento

O projeto segue versionamento semântico:

- `MAJOR`: mudanças incompatíveis no contrato documentado.
- `MINOR`: funcionalidades compatíveis.
- `PATCH`: correções compatíveis.

Aliases históricos documentados fazem parte do contrato de compatibilidade. As
opções numéricas seguem o menu atual e podem mudar quando a ordem do menu muda;
prefira subcomandos nomeados em automações.

