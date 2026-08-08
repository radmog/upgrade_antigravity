import importlib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def updater_module():
    from antigravity_updater import core

    return importlib.reload(core)


@pytest.fixture
def fixture_dir():
    return Path(__file__).parent / "fixtures"
