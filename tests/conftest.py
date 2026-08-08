import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def updater_module():
    spec = importlib.util.spec_from_file_location("antigravity_upgrade", ROOT / "upgrade.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fixture_dir():
    return Path(__file__).parent / "fixtures"

