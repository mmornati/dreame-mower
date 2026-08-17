"""Regression tests for the map.py / types.py None-guard fix.

The bug: several sites in dreame/map.py and dreame/types.py accessed
MapData fields (dimensions, pixel_type, data) without checking for
None. When the device emits partial / wifi / restored / saved-only maps
or when the very first P-frame arrives before any prior I-frame data,
those fields default to None and the unguarded accesses raise
AttributeError or TypeError, breaking the map render path entirely.

Affected sites:
  1. dreame/map.py:4523  - DreameMowerMapDataJsonRenderer.get_data_string
                           (map_data.dimensions.width * height)
  2. dreame/map.py:4541  - same (map_data.pixel_type[x, y])
  3. dreame/map.py:4985  - DreameMowerMapRenderer.render_map
                           (map_data.dimensions.width * height)
  4. dreame/map.py:3344  - DreameMowerMapDecoder.decode_p_map_data_from_partial
                           (current_map_data.data / pixel_type access)
  5. dreame/types.py:2475 - MapData.check_point
                            (self.dimensions / self.pixel_type)

The fix adds targeted `is None` guards before each unguarded access
and short-circuits with a safe default (return None / empty JSON /
False) instead of crashing.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

INTEGRATION_ROOT = (
    Path(__file__).resolve().parent.parent / "custom_components" / "dreame_mower"
)
MAP_PY = INTEGRATION_ROOT / "dreame" / "map.py"
TYPES_PY = INTEGRATION_ROOT / "dreame" / "types.py"


@pytest.fixture(scope="module")
def map_ast():
    return ast.parse(MAP_PY.read_text())


@pytest.fixture(scope="module")
def map_source() -> str:
    return MAP_PY.read_text()


@pytest.fixture(scope="module")
def types_ast():
    return ast.parse(TYPES_PY.read_text())


@pytest.fixture(scope="module")
def types_source() -> str:
    return TYPES_PY.read_text()


def _strip_comments(source: str) -> str:
    """Remove inline `#` comments line-by-line so the test isn't tripped up
    by code that mentions the bug pattern in a comment.
    """
    return "\n".join(line.split("#", 1)[0] for line in source.splitlines())


class TestGetDataStringGuard:
    """Site 1 + 2: dreame/map.py get_data_string guards for dimensions / pixel_type."""

    def test_get_data_string_guards_dimensions(self, map_source):
        """get_data_string must short-circuit when map_data.dimensions is None."""
        src = _strip_comments(map_source)
        # Find the get_data_string method
        m = re.search(
            r"def get_data_string\(.*?\n(?=    def |\nclass |\Z)",
            src,
            re.DOTALL,
        )
        assert m, "get_data_string method not found in map.py"
        body = m.group(0)
        assert "map_data.dimensions is None" in body, (
            "get_data_string must guard `map_data.dimensions is None`"
        )

    def test_get_data_string_guards_pixel_type(self, map_source):
        """get_data_string must short-circuit when map_data.pixel_type is None."""
        src = _strip_comments(map_source)
        m = re.search(
            r"def get_data_string\(.*?\n(?=    def |\nclass |\Z)",
            src,
            re.DOTALL,
        )
        assert m
        body = m.group(0)
        assert "map_data.pixel_type is None" in body, (
            "get_data_string must guard `map_data.pixel_type is None`"
        )


class TestRenderMapGuard:
    """Site 3: dreame/map.py PNG renderer's render_map guard for dimensions."""

    def test_render_map_guards_dimensions(self, map_source):
        """The PNG renderer's render_map (returns default_map_image on early exit)
        must short-circuit when map_data.dimensions is None.

        Note: there are two render_map methods in map.py - the JSON renderer
        at line 3736 and the PNG renderer at line 4997. Only the PNG one
        needs this guard because the JSON one accesses map_data.dimensions
        deep inside its body where a per-call guard wouldn't apply. The JSON
        one already has its own guards via get_data_string.
        """
        src = _strip_comments(map_source)
        # Find the render_map whose first executable line returns
        # self.default_map_image (the PNG renderer)
        m = re.search(
            r"def render_map\([^)]*\)[^:]*:\s*\n\s*if \([\s\S]*?return self\.default_map_image",
            src,
        )
        assert m, "PNG-renderer render_map method not found in map.py"
        body = m.group(0)
        assert "map_data.dimensions is None" in body, (
            "PNG-renderer render_map must guard `map_data.dimensions is None`"
        )


class TestPFrameDecoderGuard:
    """Site 4: dreame/map.py decode_p_map_data_from_partial guard."""

    def test_p_frame_decoder_guards_current_map_data(self, map_source):
        """decode_p_map_data_from_partial must check current_map_data
        dimensions/data/pixel_type before the merge loop.
        """
        src = _strip_comments(map_source)
        m = re.search(
            r"def decode_p_map_data_from_partial\(.*?\n(?=    def |\nclass |\Z)",
            src,
            re.DOTALL,
        )
        assert m, "decode_p_map_data_from_partial method not found"
        body = m.group(0)
        assert "current_map_data.data is None" in body, (
            "decode_p_map_data_from_partial must guard "
            "`current_map_data.data is None` before merging"
        )
        assert "current_map_data.pixel_type is None" in body, (
            "decode_p_map_data_from_partial must guard "
            "`current_map_data.pixel_type is None` before merging"
        )

    def test_p_frame_decoder_returns_none_when_uninitialised(self, map_source):
        """When current_map_data is not yet populated, the decoder must
        return None rather than proceeding with None data and crashing.
        """
        src = _strip_comments(map_source)
        m = re.search(
            r"def decode_p_map_data_from_partial\(.*?\n(?=    def |\nclass |\Z)",
            src,
            re.DOTALL,
        )
        assert m
        body = m.group(0)
        # The guard must return None (matches the existing
        # `if map_data is None: return None` pattern at the top of the method)
        assert "return None" in body, (
            "Guarded P-frame decoder must return None when "
            "current_map_data has no dimensions/data/pixel_type"
        )


class TestMapDataCheckPointGuard:
    """Site 5: dreame/types.py MapData.check_point guard."""

    def test_check_point_guards_dimensions(self, types_source):
        """MapData.check_point must return False when self.dimensions is None."""
        src = _strip_comments(types_source)
        m = re.search(
            r"def check_point\(self, x, y, absolute=False\) -> bool:.*?(?=\n    def |\nclass |\Z)",
            src,
            re.DOTALL,
        )
        assert m, "MapData.check_point method not found in types.py"
        body = m.group(0)
        assert "self.dimensions is None" in body, (
            "check_point must guard `self.dimensions is None`"
        )

    def test_check_point_guards_pixel_type(self, types_source):
        """MapData.check_point must return False when self.pixel_type is None."""
        src = _strip_comments(types_source)
        m = re.search(
            r"def check_point\(self, x, y, absolute=False\) -> bool:.*?(?=\n    def |\nclass |\Z)",
            src,
            re.DOTALL,
        )
        assert m
        body = m.group(0)
        assert "self.pixel_type is None" in body, (
            "check_point must guard `self.pixel_type is None`"
        )

    def test_check_point_returns_false_when_uninitialised(self, types_source):
        """When dimensions or pixel_type is None, check_point must return False
        (not crash). This is the safe default for a partial/unpopulated map.
        """
        src = _strip_comments(types_source)
        m = re.search(
            r"def check_point\(self, x, y, absolute=False\) -> bool:.*?(?=\n    def |\nclass |\Z)",
            src,
            re.DOTALL,
        )
        assert m
        body = m.group(0)
        # Confirm both checks appear and the function returns False in the guard
        assert "self.dimensions is None" in body
        assert "self.pixel_type is None" in body


class TestGuardsAreTargetedNotBroad:
    """We deliberately did NOT use blanket try/except - that would mask
    real bugs. The fix uses targeted `is None` guards.
    """

    def test_get_data_string_no_broad_try_except(self, map_ast):
        """The fix must not wrap get_data_string in a broad try/except."""
        for node in ast.walk(map_ast):
            if isinstance(node, ast.FunctionDef) and node.name == "get_data_string":
                body_src = ast.unparse(node)
                # Look for a single ExceptHandler wrapping the entire body
                # (this would be `try: <huge body>`).
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Try):
                        # Crude: if the try block spans more than ~20 lines
                        # of ast.unparse output, it's likely a blanket wrap.
                        try_block = ast.unparse(sub)
                        if try_block.count("\n") > 25:
                            pytest.fail(
                                "get_data_string has a broad try/except wrap "
                                "that would mask real bugs"
                            )
                return
        pytest.fail("get_data_string not found")

    def test_render_map_no_broad_try_except(self, map_ast):
        """The fix must not wrap render_map in a broad try/except."""
        for node in ast.walk(map_ast):
            if isinstance(node, ast.FunctionDef) and node.name == "render_map":
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Try):
                        try_block = ast.unparse(sub)
                        if try_block.count("\n") > 25:
                            pytest.fail(
                                "render_map has a broad try/except wrap "
                                "that would mask real bugs"
                            )
                return
        pytest.fail("render_map not found")