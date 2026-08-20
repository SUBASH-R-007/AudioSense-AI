"""Test-suite defaults.

The app requires a login unless anonymous access is explicitly permitted. The
suite is testing clinical behaviour, not access control, so it opts out here —
`test_auth.py` overrides this per-test to exercise the locked and protected
modes.
"""
import os

import pytest


@pytest.fixture(autouse=True)
def _anonymous_by_default(monkeypatch):
    monkeypatch.setenv("AUDIOSENSE_ALLOW_ANONYMOUS", "1")
    monkeypatch.delenv("AUDIOSENSE_USERS", raising=False)
