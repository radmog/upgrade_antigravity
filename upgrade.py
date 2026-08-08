#!/usr/bin/env python3
"""Entrada histórica; a implementação canônica vive em antigravity_updater."""

import sys

from antigravity_updater.cli import main
from antigravity_updater.core import *  # noqa: F403 - compatibilidade com imports antigos


if __name__ == "__main__":
    sys.exit(main())
