"""Regression tests for the model_map + config_flow try/except fix.

These tests were originally added to the camera fix branch because
testing the camera requires a working config flow - the original
config_flow.py crashed with KeyError('dreame.mower.g2568d') when
the user tried to configure the integration.

The fix has two parts:
1. model_map now includes 'dreame.mower.g2568d' (A2) and
   'dreame.mower.g2540d' (A1 Pro), and the lookup uses .get() with
   a fallback so unknown model IDs don't raise KeyError.
2. async_step_dreame wraps cloud.login() + get_devices() + the
   dict-subscript block in a single try/except Exception that maps
   failures to the existing 'cannot_connect' translation key.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CONFIG_FLOW_PY = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "dreame_mower"
    / "config_flow.py"
)


@pytest.fixture(scope="module")
def config_flow_ast():
    return ast.parse(CONFIG_FLOW_PY.read_text())


class TestModelMapContent:
    def test_g2568d_present(self, config_flow_ast):
        """The user's model (dreame.mower.g2568d) must be in model_map."""
        for node in ast.walk(config_flow_ast):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "model_map"
                and isinstance(node.value, ast.Dict)
            ):
                keys = [
                    k.value for k in node.value.keys
                    if isinstance(k, ast.Constant)
                ]
                assert "dreame.mower.g2568d" in keys, (
                    "model_map must contain 'dreame.mower.g2568d' - "
                    "the user's actual mower model. Without this, the "
                    "config flow crashes with KeyError."
                )
                return
        pytest.fail("model_map assignment not found")

    def test_g2540d_present(self, config_flow_ast):
        """The g2540d model must also be in model_map."""
        for node in ast.walk(config_flow_ast):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "model_map"
                and isinstance(node.value, ast.Dict)
            ):
                keys = [
                    k.value for k in node.value.keys
                    if isinstance(k, ast.Constant)
                ]
                assert "dreame.mower.g2540d" in keys
                return
        pytest.fail("model_map assignment not found")


class TestModelLookupFallback:
    def test_no_hard_subscript(self, config_flow_ast):
        """config_flow must NOT use model_map[device[...]] hard subscript."""
        src = ast.unparse(config_flow_ast)
        assert "model_map[device[" not in src, (
            "Hard subscript model_map[device[...]] still present - "
            "this crashes with KeyError on any model not in model_map."
        )

    def test_get_with_default_present(self, config_flow_ast):
        """The fixed .get(..., default) form must be in the source."""
        src = ast.unparse(config_flow_ast)
        assert "model_map.get(" in src


class TestCloudLoginExceptionHandler:
    def test_login_wrapped_in_try(self, config_flow_ast):
        """async_step_dreame wraps cloud.login() in try/except."""
        klass = next(
            node
            for node in ast.walk(config_flow_ast)
            if isinstance(node, ast.ClassDef)
            and node.name == "DreameMowerFlowHandler"
        )
        for sub in klass.body:
            if (
                isinstance(sub, (ast.AsyncFunctionDef, ast.FunctionDef))
                and sub.name == "async_step_dreame"
            ):
                src = ast.unparse(sub)
                try_with_login = (
                    "try:" in src
                    and "self.protocol.cloud.login" in src
                )
                # The try must come before the login call.
                try_idx = src.find("try:")
                login_idx = src.find("self.protocol.cloud.login")
                assert try_idx != -1 and login_idx != -1
                assert try_idx < login_idx, (
                    "async_step_dreame must wrap cloud.login() in try:"
                )
                return
        pytest.fail("async_step_dreame not found")

    def test_except_sets_cannot_connect(self, config_flow_ast):
        """The except clause sets errors['base'] = 'cannot_connect'."""
        klass = next(
            node
            for node in ast.walk(config_flow_ast)
            if isinstance(node, ast.ClassDef)
            and node.name == "DreameMowerFlowHandler"
        )
        for sub in klass.body:
            if (
                isinstance(sub, (ast.AsyncFunctionDef, ast.FunctionDef))
                and sub.name == "async_step_dreame"
            ):
                for node in ast.walk(sub):
                    if isinstance(node, ast.ExceptHandler):
                        body_src = ast.unparse(node)
                        assert (
                            'errors["base"] = "cannot_connect"' in body_src
                            or "errors['base'] = 'cannot_connect'" in body_src
                        ), (
                            "except clause in async_step_dreame must set "
                            "errors['base'] = 'cannot_connect'"
                        )
                        # Must not catch CancelledError directly
                        assert "CancelledError" not in body_src
                        return
        pytest.fail("async_step_dreame or its except clause not found")