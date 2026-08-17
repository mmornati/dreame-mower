"""Regression tests for the siid/piid reverse-lookup fix.

The bug: ``DreameMowerDevice._message_callback`` previously did an O(N)
linear scan over every ``DreameMowerProperty`` enum value for every
param of every incoming ``properties_changed`` MQTT message. The list
``[prop for prop in DreameMowerProperty]`` was rebuilt per param,
``break`` exited after the first match, and any param whose
``(siid, piid)`` did not appear in ``DreameMowerPropertyMapping`` was
silently dropped (no log, no exception).

The fix introduces an O(1) reverse dict ``SIID_PIID_TO_PROPERTY`` and a
helper ``property_from_siid_piid(siid, piid)`` in ``dreame/types.py``,
modeled on the existing forward helpers ``PIID()`` and ``DIID()``. The
device callback now does a single dict lookup per param.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

INTEGRATION_ROOT = (
    Path(__file__).resolve().parent.parent / "custom_components" / "dreame_mower"
)


@pytest.fixture(scope="module")
def types_ast():
    return ast.parse((INTEGRATION_ROOT / "dreame" / "types.py").read_text())


@pytest.fixture(scope="module")
def device_ast():
    return ast.parse((INTEGRATION_ROOT / "dreame" / "device.py").read_text())


@pytest.fixture(scope="module")
def types_source() -> str:
    return (INTEGRATION_ROOT / "dreame" / "types.py").read_text()


@pytest.fixture(scope="module")
def device_source() -> str:
    return (INTEGRATION_ROOT / "dreame" / "device.py").read_text()


class TestTypesHelpers:
    def test_siid_piid_to_property_constant_defined(self, types_source):
        """The O(1) reverse dict must be defined at module level."""
        assert "SIID_PIID_TO_PROPERTY" in types_source, (
            "SIID_PIID_TO_PROPERTY missing from types.py"
        )

    def test_property_from_siid_piid_helper_defined(self, types_source):
        """The reverse-lookup helper function must be defined."""
        assert "def property_from_siid_piid" in types_source, (
            "property_from_siid_piid helper missing from types.py"
        )

    def test_helper_signature(self, types_ast):
        """The helper must take siid and piid as int parameters."""
        for node in ast.walk(types_ast):
            if isinstance(node, ast.FunctionDef) and node.name == "property_from_siid_piid":
                params = [a.arg for a in node.args.args]
                assert "siid_value" in params, "Helper must accept siid_value"
                assert "piid_value" in params, "Helper must accept piid_value"
                return
        pytest.fail("property_from_siid_piid function not found")

    def test_helper_imported_in_device(self, device_source):
        """device.py must import the helper so the callback can use it."""
        assert "from .types import" in device_source
        # Find the import block - it must include the helper
        m = re.search(
            r"from \.types import \((.*?)\)", device_source, re.DOTALL
        )
        assert m, "Could not find .types import block in device.py"
        assert "property_from_siid_piid" in m.group(1), (
            "property_from_siid_piid not imported in device.py"
        )


class TestReverseLookupCorrectness:
    """Pure-logic test that doesn't require importing types.py.

    The reverse dict is built from ``DreameMowerPropertyMapping`` (which
    is not imported here to avoid the heavy dependencies in types.py),
    so we verify the structural contract: the dict comprehension uses
    the same mapping source, and the helper does a single dict.get().
    """

    def test_reverse_dict_uses_property_mapping(self, types_ast):
        """SIID_PIID_TO_PROPERTY must be derived from DreameMowerPropertyMapping."""
        for node in ast.walk(types_ast):
            if isinstance(node, ast.AnnAssign) and isinstance(
                node.target, ast.Name
            ) and node.target.id == "SIID_PIID_TO_PROPERTY":
                # Value must be a dict comprehension referencing
                # DreameMowerPropertyMapping
                assert isinstance(node.value, ast.DictComp), (
                    f"Expected dict comprehension, got {type(node.value).__name__}"
                )
                # The generators reference DreameMowerPropertyMapping
                gen_src = " ".join(
                    ast.unparse(g) for g in node.value.generators
                )
                assert "DreameMowerPropertyMapping" in gen_src
                return
        pytest.fail("SIID_PIID_TO_PROPERTY annotated assignment not found")

    def test_reverse_dict_filters_missing_siid_or_piid(self, types_ast):
        """The dict comprehension must guard against mappings that are
        missing either ``siid`` or ``piid`` (only ``aiid`` properties do).
        """
        for node in ast.walk(types_ast):
            if isinstance(node, ast.AnnAssign) and isinstance(
                node.target, ast.Name
            ) and node.target.id == "SIID_PIID_TO_PROPERTY":
                src = ast.unparse(node.value)
                assert "if siid in m and piid in m" in src or (
                    "siid in m" in src and "piid in m" in src
                ), (
                    "Reverse dict must filter out mappings missing siid/piid "
                    "(these are AI/auto-switch properties keyed by aiid, not "
                    "siid/piid)"
                )
                return
        pytest.fail("SIID_PIID_TO_PROPERTY not found")

    def test_helper_uses_dict_get(self, types_ast):
        """The helper must use a single dict.get() call (O(1) lookup)."""
        for node in ast.walk(types_ast):
            if isinstance(node, ast.FunctionDef) and node.name == "property_from_siid_piid":
                src = ast.unparse(node)
                assert ".get((" in src or ".get((" in src.replace(" ", ""), (
                    "Helper must use dict.get() for O(1) lookup"
                )
                # Must NOT have a for loop (that would be O(N))
                for sub in ast.walk(node):
                    if isinstance(sub, (ast.For, ast.While)):
                        pytest.fail(
                            "Helper must not contain a loop - "
                            "that defeats the O(1) lookup"
                        )
                return
        pytest.fail("property_from_siid_piid not found")


class TestDeviceCallback:
    def test_callback_uses_helper_not_linear_scan(self, device_source):
        """_message_callback must call property_from_siid_piid, not iterate
        over DreameMowerProperty.
        """
        assert "property_from_siid_piid" in device_source, (
            "_message_callback must call property_from_siid_piid"
        )
        # Strip out line comments (anything after `#`) so comment mentions
        # of the removed pattern don't trip the test.
        code_only = "\n".join(
            line.split("#", 1)[0] for line in device_source.splitlines()
        )
        assert "[prop for prop in DreameMowerProperty]" not in code_only, (
            "Old O(N) per-param list comprehension still present. "
            "This rebuilds the property list for every param of every "
            "properties_changed message - the original performance bug."
        )

    def test_callback_handles_unknown_siid_piid_gracefully(self, device_ast):
        """When property_from_siid_piid returns None (unknown tuple), the
        callback must log and continue, not raise KeyError.
        """
        # Find _message_callback
        for node in ast.walk(device_ast):
            if isinstance(node, ast.FunctionDef) and node.name == "_message_callback":
                src = ast.unparse(node)
                # Must have a guard for None return
                assert "if prop is None" in src or "if prop is None:" in src, (
                    "Callback must check for None return from the lookup "
                    "and skip unknown siid/piid tuples"
                )
                # Should log a debug message for unknown tuples
                assert "Unknown siid/piid" in src, (
                    "Callback should log unknown siid/piid tuples at debug "
                    "level so developers can spot firmware updates adding "
                    "new properties"
                )
                return
        pytest.fail("_message_callback not found in device.py")

    def test_callback_log_message_present(self, device_source):
        """The new debug-log for unknown siid/piid tuples must be present."""
        assert (
            "Unknown siid/piid in properties_changed" in device_source
        ), "Missing debug log for unknown siid/piid tuples"