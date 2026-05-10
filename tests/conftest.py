"""Shared test fixtures following TEST_GOVERNANCE.md principles."""

import os
import tempfile
import shutil
import pytest

# Set test environment before importing
os.environ["SERP_CACHE_ENABLED"] = "true"
os.environ["SERP_CACHE_DIR"] = ""
os.environ["SERP_CACHE_TTL"] = ""


@pytest.fixture
def cache_dir():
    """Create a temporary directory for cache files.

    Shared fixture to avoid duplication across test classes.
    """
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)
