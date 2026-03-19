"""Pytest configuration for headless Qt testing."""

import os

import pytest
from beans.store import Store

# Set headless mode before any Qt imports
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def tmp_beans_dir(tmp_path):
    """Create a temporary .beans directory with initialized DB."""
    beans_dir = tmp_path / ".beans"
    beans_dir.mkdir()
    db_path = beans_dir / "beans.db"
    store = Store.from_path(str(db_path))
    store.close()
    return beans_dir


@pytest.fixture
def store(tmp_beans_dir):
    """Provide an open Store connected to a temporary beans DB."""
    db_path = tmp_beans_dir / "beans.db"
    s = Store.from_path(str(db_path))
    yield s
    s.close()
