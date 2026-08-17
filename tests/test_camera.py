"""Regression tests for the camera.py default-image-seed fix.

The bug: at startup, `DreameMowerCameraEntity.__init__` assigned
`self._image = None` and only seeded the renderer's `default_map_image`
when `map_index == 0 and not self.map_data_json`. This left
`camera.*_map_data` (where `map_data_json == True`) and every saved-map
camera (`map_index > 0`) with `_image is None` until the first successful
`_update_image` ran. For a freshly-installed, never-mapped mower, that
never happens, so HA rendered the entities as "unavailable" indefinitely.

The fix drops the guard and unconditionally seeds the default image so
every camera entity has a valid PNG from the first request. It also
fixes `_update_image`'s except branch (`LOGGER.warn` -> `LOGGER.warning`)
and adds a fallback to the default image when a render raises.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

INTEGRATION_ROOT = (
    Path(__file__).resolve().parent.parent / "custom_components" / "dreame_mower"
)


@pytest.fixture(scope="module")
def camera_ast():
    return ast.parse(
        (INTEGRATION_ROOT / "camera.py").read_text(encoding="utf-8")
    )


def _find_class(tree: ast.Module, name: str) -> ast.ClassDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _find_method(klass: ast.ClassDef, name: str):
    """Find a method (sync or async) by name in a class body."""
    for node in klass.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return node
    return None


def _class_body_source(klass: ast.ClassDef, fn_name: str) -> str | None:
    """Return the source slice for ``klass.fn_name`` or None if not found."""
    fn = _find_method(klass, fn_name)
    if fn is None:
        return None
    return ast.unparse(fn)


def _class_init_source(klass: ast.ClassDef) -> str | None:
    return _class_body_source(klass, "__init__")


class TestCameraDefaultImageSeed:
    def test_init_seeds_default_image_unconditionally(self, camera_ast):
        """The __init__ method must seed self._image from default_map_image
        without the old `map_index == 0 and not self.map_data_json` guard.
        """
        klass = _find_class(camera_ast, "DreameMowerCameraEntity")
        assert klass is not None, "DreameMowerCameraEntity class not found"

        init = _find_method(klass, "__init__")
        assert init is not None, "__init__ method not found"

        src = ast.unparse(init)
        assert "self._image = self._renderer.default_map_image" in src, (
            "Expected unconditional seed `self._image = "
            "self._renderer.default_map_image` in __init__."
        )

        # The buggy guard must NOT be present. Two patterns we explicitly
        # removed:
        bad_guarded = "self.map_index == 0 and not self.map_data_json"
        bad_partial = "self.map_index == 0 and not self.map_data_json:"
        for bad in (bad_guarded, bad_partial):
            assert bad not in src, (
                f"Old guarded default-image seed `{bad!r}` still present. "
                "This is the original bug that left *_map_data and saved-map "
                "cameras with _image=None at startup, causing 'unavailable'."
            )

    def test_init_does_not_leave_image_as_none(self, camera_ast):
        """No bare `self._image = None` followed by a guarded seed should
        remain - the only `self._image = None` should be at the top, and
        the unconditional seed must come after.
        """
        klass = _find_class(camera_ast, "DreameMowerCameraEntity")
        init = _find_method(klass, "__init__")
        src_lines = [
            line.strip() for line in ast.unparse(init).splitlines()
        ]

        # Find positions of the two relevant assignments
        none_idx = next(
            (
                i
                for i, line in enumerate(src_lines)
                if line == "self._image = None"
            ),
            None,
        )
        seed_idx = next(
            (
                i
                for i, line in enumerate(src_lines)
                if line == "self._image = self._renderer.default_map_image"
            ),
            None,
        )

        assert none_idx is not None, "self._image = None initial assignment not found"
        assert seed_idx is not None, "self._image = self._renderer.default_map_image seed not found"
        assert seed_idx > none_idx, (
            "Default image seed must come AFTER the initial `self._image = None`"
        )


class TestUpdateImageExceptionHandler:
    def test_uses_warning_not_warn(self, camera_ast):
        """`LOGGER.warn` is deprecated; the integration must use `LOGGER.warning`."""
        klass = _find_class(camera_ast, "DreameMowerCameraEntity")
        assert klass is not None

        update = _find_method(klass, "_update_image")
        assert update is not None, "_update_image method not found"

        src = ast.unparse(update)
        assert "LOGGER.warning" in src, (
            "_update_image must use LOGGER.warning (the deprecated "
            "LOGGER.warn is no longer valid in modern Python)."
        )
        assert "LOGGER.warn(" not in src, (
            "Deprecated LOGGER.warn() still present in _update_image"
        )

    def test_except_falls_back_to_default_image(self, camera_ast):
        """The except branch in _update_image must restore the default image
        so a transient render error doesn't leave the camera blank.
        """
        klass = _find_class(camera_ast, "DreameMowerCameraEntity")
        update = _find_method(klass, "_update_image")
        src = ast.unparse(update)

        assert "except Exception" in src, "Expected `except Exception` block"
        # We expect the except block to re-assign self._image to the default
        # image. Find the except clause body.
        for node in ast.walk(update):
            if isinstance(node, ast.ExceptHandler):
                body_src = ast.unparse(node)
                assert "self._image = self._renderer.default_map_image" in body_src, (
                    "except block must fall back to default_map_image to "
                    "prevent blank-camera state on render errors."
                )
                return
        raise AssertionError("No `except Exception` block found in _update_image")


class TestCameraEntityDescription:
    def test_map_data_json_entity_description_exists(self, camera_ast):
        """The JSON_MAP_DATA camera (camera.*_map_data) must be in CAMERAS."""
        # Find module-level CAMERAS tuple (either plain assign or annotated)
        for node in camera_ast.body:
            target_name = None
            value = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                if isinstance(node.targets[0], ast.Name):
                    target_name = node.targets[0].id
                    value = node.value
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    target_name = node.target.id
                    value = node.value

            if target_name == "CAMERAS" and isinstance(value, (ast.Tuple, ast.List)):
                assert len(value.elts) >= 2, (
                    f"CAMERAS should contain >=2 entries (floor_map + "
                    f"json_map_data); found {len(value.elts)}."
                )
                return
        raise AssertionError("CAMERAS tuple not found at module level")


class TestWebRTCAttributesSeeded:
    """Tests for the `_webrtc_provider` / `_supports_native_async_webrtc`
    defensive initialisation.

    Modern Home Assistant's Camera base class declares these attributes in
    its __init__. With our MRO
    `DreameMowerCameraEntity(DreameMowerEntity, Camera)` the cooperative
    super() chain skips Camera.__init__() because DreameMowerEntity's
    `super().__init__(coordinator=coordinator)` uses a kwarg signature
    that Camera.__init__() (which takes no args) cannot accept.

    Without these attributes HA's `async_refresh_providers()` raises
    AttributeError on the first read, the entity fails to register, and
    HA surfaces it as "unavailable" in the UI.
    """

    def test_webrtc_provider_seeded_in_init(self, camera_ast):
        """__init__ must explicitly assign self._webrtc_provider = None."""
        klass = _find_class(camera_ast, "DreameMowerCameraEntity")
        init = _find_method(klass, "__init__")
        src = ast.unparse(init)
        assert "self._webrtc_provider = None" in src, (
            "__init__ must assign self._webrtc_provider = None - "
            "Camera.__init__() is skipped by the cooperative super() "
            "chain so the attribute must be set explicitly to prevent "
            "AttributeError in HA's async_refresh_providers()."
        )

    def test_supports_native_async_webrtc_seeded_in_init(self, camera_ast):
        """__init__ must compute _supports_native_async_webrtc the same way
        Camera.__init__() does."""
        klass = _find_class(camera_ast, "DreameMowerCameraEntity")
        init = _find_method(klass, "__init__")
        src = ast.unparse(init)
        assert "_supports_native_async_webrtc" in src, (
            "__init__ must compute self._supports_native_async_webrtc - "
            "this attribute is read by Camera.async_refresh_providers() "
            "and must exist on every Camera subclass instance."
        )
        assert (
            "type(self).async_handle_async_webrtc_offer" in src
        ), "_supports_native_async_webrtc must mirror Camera.__init__()"


class TestStateInitialization:
    """Tests for the `_state = datetime.now()` initialisation.

    Even when the placeholder image is valid, HA shows "unavailable" if
    `self._state` is the string `STATE_UNAVAILABLE`. The `state`
    property at line 876 returns this value directly to HA.
    """

    def test_initial_state_is_not_state_unavailable(self, camera_ast):
        """__init__ must not initialise self._state to STATE_UNAVAILABLE."""
        klass = _find_class(camera_ast, "DreameMowerCameraEntity")
        init = _find_method(klass, "__init__")
        src = ast.unparse(init)
        # Should be datetime.now(), not STATE_UNAVAILABLE
        assert "self._state = datetime.now()" in src, (
            "__init__ must initialise self._state to datetime.now() so "
            "the camera entity shows a valid timestamp in HA instead of "
            "the bogus 'unavailable' string while waiting for the "
            "device's first map."
        )
        # Specifically: must NOT use STATE_UNAVAILABLE
        assert "self._state = STATE_UNAVAILABLE" not in src, (
            "__init__ must NOT set self._state = STATE_UNAVAILABLE - "
            "this is what causes the persistent 'unavailable' state "
            "even when the placeholder image is valid."
        )

    def test_handle_coordinator_update_no_longer_sets_unavailable(self, camera_ast):
        """_handle_coordinator_update's else branch must not set STATE_UNAVAILABLE."""
        klass = _find_class(camera_ast, "DreameMowerCameraEntity")
        method = _find_method(klass, "_handle_coordinator_update")
        src = ast.unparse(method)
        # The else branch should fall back to datetime.now(), not STATE_UNAVAILABLE
        for node in ast.walk(method):
            if isinstance(node, ast.ExceptHandler):
                continue
        # Simpler check: STATE_UNAVAILABLE shouldn't appear in the else branch
        # at all (we left it only in update()'s "device lost map" branch).
        # Confirm by counting - should appear at most 0 times in this method.
        count = src.count("STATE_UNAVAILABLE")
        assert count == 0, (
            f"_handle_coordinator_update must not reference STATE_UNAVAILABLE "
            f"(found {count} occurrence(s)) - a freshly-installed, never-mapped "
            f"mower would otherwise show the camera as 'unavailable' indefinitely."
        )