"""Regression tests for the config_flow.py cloud-login error handling.

The bug: ``async_step_dreame`` and ``async_step_mova`` called
``await self.hass.async_add_executor_job(self.protocol.cloud.login)``
without a try/except wrapper. While ``DreameMowerDreameHomeCloudProtocol.login()``
catches ``requests.exceptions.Timeout`` and broad ``Exception`` *inside* its
own try-block, several failure modes still propagate:

- The ``_strings`` zlib-decompression at protocol.py:281-287 runs **outside**
  the try block (can raise zlib.error, binascii.Error, json.JSONDecodeError,
  UnicodeDecodeError).
- The refresh-token retry at protocol.py:329-331 (``return self.login()``)
  can cause a RecursionError if it loops indefinitely.

Additionally, downstream of a successful login, several dict subscripts
were unguarded:

- ``devices["page"]["records"]`` (config_flow.py:450, 537)
- ``device["customName"]`` (config_flow.py:457, 544)
- ``device["deviceInfo"]["displayName"]`` (config_flow.py:460, 547)

Any of these KeyError/TypeError exceptions bubble to HA, which surfaces
the user-facing "unknown error" message - the same symptom as the
``model_map[device["model"]]`` bug this integration has historically
suffered from.

The fix wraps the entire cloud-login-and-device-listing block in a
single ``try/except Exception`` mirroring ``async_step_connect``'s
pattern at config_flow.py:218-249, mapping any unhandled exception
to ``errors["base"] = "cannot_connect"``.

The asyncio.CancelledError subclass relationship means it subclasses
BaseException in modern Python (PEP 492 + Python 3.8+), so it is NOT
caught by ``except Exception`` and properly propagates.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

CONFIG_FLOW_PY = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "dreame_mower"
    / "config_flow.py"
)


@pytest.fixture(scope="module")
def config_flow_source() -> str:
    return CONFIG_FLOW_PY.read_text()


@pytest.fixture(scope="module")
def config_flow_ast():
    return ast.parse(CONFIG_FLOW_PY.read_text())


def _strip_comments(source: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in source.splitlines())


def _extract_async_method(klass: ast.ClassDef, name: str) -> ast.AsyncFunctionDef | None:
    for node in klass.body:
        if (
            isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name == name
        ):
            return node
    return None


class TestAsyncStepDreame:
    """async_step_dreame must wrap cloud.login() in try/except."""

    def test_method_exists(self, config_flow_ast):
        klass = next(
            node
            for node in ast.walk(config_flow_ast)
            if isinstance(node, ast.ClassDef)
            and node.name == "DreameMowerFlowHandler"
        )
        method = _extract_async_method(klass, "async_step_dreame")
        assert method is not None, "async_step_dreame not found"

    def test_login_wrapped_in_try(self, config_flow_ast):
        """The async_step_dreame method must wrap cloud.login() in try/except."""
        klass = next(
            node
            for node in ast.walk(config_flow_ast)
            if isinstance(node, ast.ClassDef)
            and node.name == "DreameMowerFlowHandler"
        )
        method = _extract_async_method(klass, "async_step_dreame")
        src = ast.unparse(method)

        # Must have a try block that contains cloud.login()
        try_with_login = re.search(
            r"try:\s*\n\s*await self\.hass\.async_add_executor_job"
            r"\(self\.protocol\.cloud\.login\)",
            src,
        )
        assert try_with_login, (
            "async_step_dreame must wrap cloud.login() in a try block"
        )

    def test_login_except_sets_cannot_connect(self, config_flow_ast):
        """The except clause must set errors['base'] = 'cannot_connect'."""
        klass = next(
            node
            for node in ast.walk(config_flow_ast)
            if isinstance(node, ast.ClassDef)
            and node.name == "DreameMowerFlowHandler"
        )
        method = _extract_async_method(klass, "async_step_dreame")
        for node in ast.walk(method):
            if isinstance(node, ast.ExceptHandler):
                body_src = ast.unparse(node)
                # ast.unparse uses single quotes by default; match both
                assert (
                    'errors["base"] = "cannot_connect"' in body_src
                    or "errors['base'] = 'cannot_connect'" in body_src
                ), (
                    "except clause in async_step_dreame must set "
                    "errors['base'] = 'cannot_connect'"
                )
                # Must NOT catch CancelledError directly (which is a
                # BaseException, not Exception, and should always propagate).
                assert "CancelledError" not in body_src, (
                    "except clause must NOT catch asyncio.CancelledError - "
                    "it subclasses BaseException and should propagate"
                )
                return
        pytest.fail("No except clause found in async_step_dreame")

    def test_model_map_get_fallback_used(self, config_flow_ast):
        """async_step_dreame must use model_map.get(..., default) to avoid
        KeyError on unknown model strings (defence in depth alongside the
        try/except wrap).
        """
        klass = next(
            node
            for node in ast.walk(config_flow_ast)
            if isinstance(node, ast.ClassDef)
            and node.name == "DreameMowerFlowHandler"
        )
        method = _extract_async_method(klass, "async_step_dreame")
        src = ast.unparse(method)
        assert "model_map.get(" in src, (
            "async_step_dreame must use model_map.get() with a default fallback"
        )


class TestAsyncStepMova:
    """async_step_mova must wrap cloud.login() in try/except."""

    def test_login_wrapped_in_try(self, config_flow_ast):
        klass = next(
            node
            for node in ast.walk(config_flow_ast)
            if isinstance(node, ast.ClassDef)
            and node.name == "DreameMowerFlowHandler"
        )
        method = _extract_async_method(klass, "async_step_mova")
        assert method is not None, "async_step_mova not found"
        src = ast.unparse(method)

        try_with_login = re.search(
            r"try:\s*\n\s*await self\.hass\.async_add_executor_job"
            r"\(self\.protocol\.cloud\.login\)",
            src,
        )
        assert try_with_login, (
            "async_step_mova must wrap cloud.login() in a try block"
        )

    def test_login_except_sets_cannot_connect(self, config_flow_ast):
        klass = next(
            node
            for node in ast.walk(config_flow_ast)
            if isinstance(node, ast.ClassDef)
            and node.name == "DreameMowerFlowHandler"
        )
        method = _extract_async_method(klass, "async_step_mova")
        for node in ast.walk(method):
            if isinstance(node, ast.ExceptHandler):
                body_src = ast.unparse(node)
                assert (
                    'errors["base"] = "cannot_connect"' in body_src
                    or "errors['base'] = 'cannot_connect'" in body_src
                ), (
                    "except clause in async_step_mova must set "
                    "errors['base'] = 'cannot_connect'"
                )
                return
        pytest.fail("No except clause found in async_step_mova")

    def test_model_map_get_fallback_used(self, config_flow_ast):
        """async_step_mova must use model_map.get(..., default) for consistency
        with async_step_dreame. Previously mova used `model = device["model"]`
        which left the raw model ID (e.g. 'dreame.mower.g2568d') instead of
        the friendly label ('A2') shown to the user.
        """
        klass = next(
            node
            for node in ast.walk(config_flow_ast)
            if isinstance(node, ast.ClassDef)
            and node.name == "DreameMowerFlowHandler"
        )
        method = _extract_async_method(klass, "async_step_mova")
        src = ast.unparse(method)
        assert "model_map.get(" in src, (
            "async_step_mova must use model_map.get() with a default fallback "
            "to match async_step_dreame's behaviour and avoid KeyError"
        )


class TestExistingPatternPreserved:
    """Confirm async_step_connect's pattern is unchanged."""

    def test_async_step_connect_still_has_try_except(self, config_flow_ast):
        """The reference pattern at async_step_connect must be unchanged."""
        klass = next(
            node
            for node in ast.walk(config_flow_ast)
            if isinstance(node, ast.ClassDef)
            and node.name == "DreameMowerFlowHandler"
        )
        method = _extract_async_method(klass, "async_step_connect")
        assert method is not None
        src = ast.unparse(method)
        assert "try:" in src
        assert (
            'errors["base"] = "cannot_connect"' in src
            or "errors['base'] = 'cannot_connect'" in src
        )


class TestErrorKeyReuse:
    """Both 'cannot_connect' and 'no_devices' are existing translation keys.

    All 13 translation files already include them (verified during
    investigation). The fix must NOT introduce new error keys.
    """

    def test_no_new_error_keys(self, config_flow_source):
        """The fix uses only pre-existing error keys."""
        src = _strip_comments(config_flow_source)
        # Find any keys like errors["base"] = "<key>"  (single or double quotes)
        new_keys = set(re.findall(r"errors\[[\"']base[\"']\]\s*=\s*[\"']([^\"']+)[\"']", src))
        existing_keys = {
            "cannot_connect",
            "no_devices",
            "login_error",
            "credentials_incomplete",
            "2fa_required",
            "wrong_token",
            "unsupported",
        }
        unknown = new_keys - existing_keys
        assert not unknown, (
            f"New error keys introduced: {unknown}. "
            "All 13 translation files already include the existing keys - "
            "reusing them keeps the diff minimal."
        )