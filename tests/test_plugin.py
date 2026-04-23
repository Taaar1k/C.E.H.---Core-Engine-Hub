"""Tests for the C.E.H. plugin system."""

from __future__ import annotations

import types
from typing import Any, Dict, List

import pytest

from c_e_h.plugin import PluginError, PluginLoadError, PluginManager, PluginMetadata
from c_e_h.tools import ToolDefinition

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _DummyPlugin:
    """Minimal plugin implementation for testing."""

    name = "dummy"
    version = "0.1.0"
    description = "A dummy plugin for testing"

    def __init__(self) -> None:
        self.initialized = False

    def initialize(self, config: Dict[str, Any] = None) -> None:
        self.initialized = True

    def get_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(name="dummy_tool", description="A dummy tool", func=lambda: None),
        ]

    def shutdown(self) -> None:
        self.initialized = False


class _BrokenPlugin:
    """Plugin that raises on initialize."""

    name = "broken"
    version = "0.1.0"
    description = "A broken plugin"

    def initialize(self, config: Dict[str, Any] = None) -> None:
        raise RuntimeError("init failed")

    def get_tools(self) -> List[ToolDefinition]:
        return []

    def shutdown(self) -> None:
        pass


class _LoadErrorPlugin:
    """Plugin class that raises on instantiation."""

    name = "loaderror"
    version = "0.1.0"
    description = "A plugin with load error"

    def __init__(self) -> None:
        raise ValueError("cannot instantiate")

    def initialize(self, config: Dict[str, Any] = None) -> None:
        pass

    def get_tools(self) -> List[ToolDefinition]:
        return []

    def shutdown(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Tests — PluginManager basic operations
# ---------------------------------------------------------------------------


def test_plugin_manager_discover_empty() -> None:
    """Test discovery with no plugins registered."""
    pm = PluginManager()
    # With no entry points registered, discover should return an empty list.
    discovered = pm.discover_plugins()
    assert isinstance(discovered, list)
    # The _metadata dict should be populated (may contain real or no plugins)
    assert isinstance(pm._metadata, dict)


def test_plugin_manager_load_plugin_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test loading a plugin that succeeds."""
    pm = PluginManager()

    # Create a fake entry point
    ep = types.SimpleNamespace(
        name="test_plugin",
        load=lambda: _DummyPlugin,
        dist=types.SimpleNamespace(
            metadata={"Version": "1.0.0", "Summary": "Test plugin"}
        ),
    )
    meta = PluginMetadata(
        name="test_plugin",
        version="1.0.0",
        description="Test plugin",
        entry_point=ep,
    )
    pm._metadata["test_plugin"] = meta

    plugin = pm.load_plugin("test_plugin")
    assert plugin.name == "dummy"
    assert plugin.initialized is True
    assert "test_plugin" in pm._plugins


def test_plugin_manager_load_plugin_not_found() -> None:
    """Test loading a plugin that was never discovered."""
    pm = PluginManager()
    with pytest.raises(PluginLoadError, match="not found"):
        pm.load_plugin("nonexistent")


def test_plugin_manager_load_plugin_init_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that init failure raises PluginLoadError and stores error."""
    pm = PluginManager()

    ep = types.SimpleNamespace(
        name="broken",
        load=lambda: _BrokenPlugin,
        dist=types.SimpleNamespace(
            metadata={"Version": "0.1.0", "Summary": "Broken"}
        ),
    )
    meta = PluginMetadata(
        name="broken",
        version="0.1.0",
        description="Broken",
        entry_point=ep,
    )
    pm._metadata["broken"] = meta

    with pytest.raises(PluginLoadError, match="init failed"):
        pm.load_plugin("broken")

    assert "broken" in pm._errors


def test_plugin_manager_load_plugin_class_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that class load failure raises PluginLoadError."""
    pm = PluginManager()

    def _bad_load() -> None:
        raise ImportError("module not found")

    ep = types.SimpleNamespace(
        name="bad_load",
        load=_bad_load,
        dist=None,
    )
    meta = PluginMetadata(
        name="bad_load",
        version="",
        description="",
        entry_point=ep,
    )
    pm._metadata["bad_load"] = meta

    with pytest.raises(PluginLoadError, match="Failed to load plugin class"):
        pm.load_plugin("bad_load")


def test_plugin_manager_load_all_plugins_graceful(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that load_all_plugins skips broken plugins."""
    pm = PluginManager()

    # Add good plugin
    ep_good = types.SimpleNamespace(
        name="good",
        load=lambda: _DummyPlugin,
        dist=types.SimpleNamespace(
            metadata={"Version": "1.0.0", "Summary": "Good"}
        ),
    )
    pm._metadata["good"] = PluginMetadata(
        name="good",
        version="1.0.0",
        description="Good",
        entry_point=ep_good,
    )

    # Add broken plugin
    ep_bad = types.SimpleNamespace(
        name="bad",
        load=lambda: _BrokenPlugin,
        dist=types.SimpleNamespace(
            metadata={"Version": "0.1.0", "Summary": "Bad"}
        ),
    )
    pm._metadata["bad"] = PluginMetadata(
        name="bad",
        version="0.1.0",
        description="Bad",
        entry_point=ep_bad,
    )

    loaded = pm.load_all_plugins()
    assert len(loaded) == 1
    assert loaded[0].name == "dummy"
    assert "bad" in pm._errors


def test_plugin_manager_get_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test collecting tools from loaded plugins."""
    pm = PluginManager()

    ep = types.SimpleNamespace(
        name="tool_plugin",
        load=lambda: _DummyPlugin,
        dist=types.SimpleNamespace(
            metadata={"Version": "1.0.0", "Summary": "Tool plugin"}
        ),
    )
    pm._metadata["tool_plugin"] = PluginMetadata(
        name="tool_plugin",
        version="1.0.0",
        description="Tool plugin",
        entry_point=ep,
    )

    pm.load_plugin("tool_plugin")
    tools = pm.get_tools()
    assert len(tools) == 1
    assert tools[0].name == "dummy_tool"


def test_plugin_manager_list_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test listing plugin summaries."""
    pm = PluginManager()

    ep = types.SimpleNamespace(
        name="listed",
        load=lambda: _DummyPlugin,
        dist=types.SimpleNamespace(
            metadata={"Version": "2.0.0", "Summary": "Listed"}
        ),
    )
    pm._metadata["listed"] = PluginMetadata(
        name="listed",
        version="2.0.0",
        description="Listed",
        entry_point=ep,
    )

    pm.load_plugin("listed")
    plugins = pm.list_plugins()
    assert len(plugins) == 1
    assert plugins[0]["name"] == "listed"
    assert plugins[0]["status"] == "loaded"


def test_plugin_manager_shutdown_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test shutdown calls shutdown() on all plugins."""
    pm = PluginManager()

    ep = types.SimpleNamespace(
        name="shutdown_test",
        load=lambda: _DummyPlugin,
        dist=types.SimpleNamespace(
            metadata={"Version": "1.0.0", "Summary": "Shutdown test"}
        ),
    )
    pm._metadata["shutdown_test"] = PluginMetadata(
        name="shutdown_test",
        version="1.0.0",
        description="Shutdown test",
        entry_point=ep,
    )

    pm.load_plugin("shutdown_test")
    pm.shutdown_all()
    assert "shutdown_test" not in pm._plugins


def test_plugin_error_hierarchy() -> None:
    """Test that PluginLoadError is a subclass of PluginError."""
    assert issubclass(PluginError, Exception)
    assert issubclass(PluginLoadError, PluginError)


def test_plugin_manager_empty_tools_from_broken_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test get_tools handles plugins that raise during get_tools()."""
    pm = PluginManager()

    class _BadToolsPlugin:
        name = "bad_tools"
        version = "1.0.0"
        description = "Bad tools"

        def initialize(self, config: Dict[str, Any] = None) -> None:
            pass

        def get_tools(self) -> List[ToolDefinition]:
            raise RuntimeError("tools failed")

        def shutdown(self) -> None:
            pass

    ep = types.SimpleNamespace(
        name="bad_tools",
        load=lambda: _BadToolsPlugin,
        dist=types.SimpleNamespace(
            metadata={"Version": "1.0.0", "Summary": "Bad tools"}
        ),
    )
    pm._metadata["bad_tools"] = PluginMetadata(
        name="bad_tools",
        version="1.0.0",
        description="Bad tools",
        entry_point=ep,
    )

    pm.load_plugin("bad_tools")
    # Should not raise; just log a warning
    tools = pm.get_tools()
    assert tools == []
