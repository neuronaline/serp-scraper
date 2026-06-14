"""Shared test fixtures following TEST_GOVERNANCE.md principles."""

import os
import tempfile
import shutil
import pytest

from serp.cache import reset_cache
from serp.google_news import reset_default_client as reset_google_news_client


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global state before each test to ensure test isolation."""
    original_env = {
        "SERP_CACHE_ENABLED": os.environ.get("SERP_CACHE_ENABLED"),
        "SERP_CACHE_DIR": os.environ.get("SERP_CACHE_DIR"),
        "SERP_CACHE_TTL": os.environ.get("SERP_CACHE_TTL"),
    }

    os.environ["SERP_CACHE_ENABLED"] = "true"
    os.environ["SERP_CACHE_DIR"] = ""
    os.environ["SERP_CACHE_TTL"] = ""

    reset_cache()
    reset_google_news_client()

    yield

    for key, value in original_env.items():
        if value is not None:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)

    reset_cache()


@pytest.fixture
def cache_dir():
    """Create a temporary directory for cache files."""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)
