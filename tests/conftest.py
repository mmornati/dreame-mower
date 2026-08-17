"""Pytest configuration and shared fixtures for the integration's
regression tests.

This conftest is intentionally minimal: it provides the lightweight
``homeassistant`` stubs and AST-parsing helpers used by every test
file under ``tests/``. Test files that need to actually ``import``
config_flow.py (the e2e tests) install richer mocks themselves.

Why AST-based tests rather than real integration tests?
The integration pulls in heavy native deps (numpy, PIL, paho-mqtt,
miio, Crypto, py_mini_racer, cryptography) and the Home Assistant
core (libffi, aiohttp, snappy). Bootstrapping that on a contributor
machine or in CI is slow and fragile. AST tests verify the same
structural contracts (function signatures, dict contents, source
patterns) at a fraction of the cost and run anywhere pytest does.
"""

from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INTEGRATION_ROOT = PROJECT_ROOT / "custom_components" / "dreame_mower"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Lightweight homeassistant stubs.
#
# Enough for test COLLECTION (no NameError when pytest introspects test
# modules that import homeassistant.const) and enough for AST-only tests
# that never actually instantiate HA objects.
#
# Test files that need to import config_flow.py (the e2e tests) replace
# these with richer mocks that support class-level keyword arguments like
# ConfigFlow(domain=...).
# ---------------------------------------------------------------------------


def _install_light_homeassistant() -> None:
    if "homeassistant" in sys.modules:
        return

    ha = types.ModuleType("homeassistant")
    ha.__path__ = []
    sys.modules["homeassistant"] = ha

    const = types.ModuleType("homeassistant.const")
    const.CONF_NAME = "name"
    const.CONF_HOST = "host"
    const.CONF_TOKEN = "token"
    const.CONF_PASSWORD = "password"
    const.CONF_USERNAME = "username"
    sys.modules["homeassistant.const"] = const

    core = types.ModuleType("homeassistant.core")
    core.callback = lambda f: f

    class _HomeAssistant:
        pass

    core.HomeAssistant = _HomeAssistant
    sys.modules["homeassistant.core"] = core

    ce = types.ModuleType("homeassistant.config_entries")

    class _ConfigEntry:
        pass

    class _ConfigFlow:
        pass

    class _OptionsFlow:
        config_entry = None

        @staticmethod
        async def async_create_entry(title, data):
            return {"type": "create_entry", "title": title, "data": data}

    ce.ConfigEntry = _ConfigEntry
    ce.ConfigFlow = _ConfigFlow
    ce.OptionsFlow = _OptionsFlow
    sys.modules["homeassistant.config_entries"] = ce


_install_light_homeassistant()


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Fixtures: per-module AST parsing, cached for the test session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def integration_root() -> Path:
    return INTEGRATION_ROOT


@pytest.fixture(scope="session")
def config_flow_source() -> str:
    return (INTEGRATION_ROOT / "config_flow.py").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def config_flow_ast():
    return _parse(INTEGRATION_ROOT / "config_flow.py")