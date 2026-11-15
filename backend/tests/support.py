"""Helpers shared by the tests (imported, unlike the fixtures in conftest.py)."""

import os

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError


def skip_or_fail(reason: str) -> None:
    """Skip the test locally, but fail it in CI.

    In CI a skip would hide a broken setup behind a green run.
    """
    if os.environ.get("CI"):
        pytest.fail(f"{reason} (in CI this must not happen: check the workflow)")
    pytest.skip(reason)


def require_database(engine: Engine) -> None:
    """Stop the test when the database behind `engine` is not reachable."""
    try:
        with engine.connect():
            pass
    except OperationalError:
        skip_or_fail("Test database not reachable (start the development database)")
