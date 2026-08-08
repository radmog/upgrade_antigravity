from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bash_e_wrapper_da_implementacao_python():
    script = (ROOT / "upgrade.sh").read_text(encoding="utf-8")
    assert 'exec python3 "$SCRIPT_DIR/upgrade.py" "$@"' in script
    assert "curl " not in script
    assert "tar -" not in script
    assert "rm -rf" not in script
