import re
from pathlib import Path

from antigravity_updater import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_versao_estavel_sincronizada():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_version = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)

    assert project_version is not None
    assert __version__ == project_version.group(1) == "1.0.1"


def test_ci_cobre_matriz_python_suportada():
    workflow = (ROOT / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8")

    assert 'python-version: ["3.9", "3.10", "3.11", "3.12", "3.13"]' in workflow
    assert "python -m pip wheel" in workflow


def test_documentacao_da_release_estavel_existe():
    for relative in (
        "CHANGELOG.md",
        "docs/COMPATIBILITY.md",
        "docs/OPERATIONS.md",
        "docs/RELEASING.md",
    ):
        assert (ROOT / relative).is_file()


def test_readme_documenta_sair_como_ultima_opcao():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "6. Sair" not in readme
    assert "17. **Sair**" in readme
