import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.geteuid() == 0, reason="o contrato testado exige usuário sem privilégios")
@pytest.mark.parametrize(
    "command",
    [
        [sys.executable, str(ROOT / "upgrade.py"), "--both"],
        ["bash", str(ROOT / "upgrade.sh"), "both"],
    ],
)
def test_instaladores_recusam_execucao_sem_root(command):
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    assert result.returncode == 1
    assert "privilégios de administrador" in result.stdout


def test_scripts_possuem_sintaxe_valida():
    python_result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROOT / "upgrade.py")],
        capture_output=True,
        check=False,
    )
    bash_result = subprocess.run(
        ["bash", "-n", str(ROOT / "upgrade.sh")],
        capture_output=True,
        check=False,
    )
    assert python_result.returncode == 0, python_result.stderr.decode()
    assert bash_result.returncode == 0, bash_result.stderr.decode()

