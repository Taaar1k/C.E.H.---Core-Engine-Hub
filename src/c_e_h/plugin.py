"""Plugin system for C.E.H.

Provides:
  - PluginError, PluginLoadError: exceptions for plugin lifecycle errors
  - Plugin: protocol defining the plugin interface (initialize, get_tools, shutdown)
  - PluginMetadata: pydantic model for plugin metadata
  - PluginManager: discovers, loads, and manages plugins via
    ``importlib.metadata.entry_points`` using the ``c_e_h.plugins`` group
"""

from __future__ import annotations

import importlib.metadata
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from c_e_h.tools import ToolDefinition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PluginError(Exception):
    """Base exception for plugin-related errors."""


class PluginLoadError(PluginError):
    """Raised when a plugin fails to load or initialize."""


# ---------------------------------------------------------------------------
# Plugin Protocol & Metadata
# ---------------------------------------------------------------------------


class Plugin(Protocol):
    """Protocol that all C.E.H. plugins must implement.

    Attributes:
        name: Plugin display name.
        version: Plugin version string.
        description: Short description of the plugin.
    """

    name: str
    version: str
    description: str

    def initialize(self, config: Dict[str, Any] = ...) -> None: ...

    def get_tools(self) -> List[ToolDefinition]: ...

    def shutdown(self) -> None: ...


@dataclass
class PluginMetadata:
    """Metadata about a discovered plugin.

    Attributes:
        name: Plugin name.
        version: Plugin version.
        description: Plugin description.
        entry_point: The ``importlib.metadata.EntryPoint`` object.
    """

    name: str
    version: str
    description: str
    entry_point: importlib.metadata.EntryPoint


# ---------------------------------------------------------------------------
# Plugin Manager
# ---------------------------------------------------------------------------


class PluginManager:
    """Discovers, loads, and manages C.E.H. plugins.

    Uses ``importlib.metadata.entry_points`` with the group ``c_e_h.plugins``
    to discover plugins installed in the current environment.

    Args:
        config: Global configuration dictionary passed to plugins on init.
    """

    ENTRY_POINT_GROUP = "c_e_h.plugins"

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialise the PluginManager.

        Args:
            config: Optional global configuration dict.
        """
        self._config: Dict[str, Any] = config or {}
        self._plugins: Dict[str, Plugin] = {}
        self._metadata: Dict[str, PluginMetadata] = {}
        self._errors: Dict[str, PluginLoadError] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_plugins(self) -> List[PluginMetadata]:
        """Discover all plugins registered under ``c_e_h.plugins``.

        Returns:
            List of ``PluginMetadata`` for every discovered entry point.
        """
        discovered: List[PluginMetadata] = []
        try:
            eps = importlib.metadata.entry_points(group=self.ENTRY_POINT_GROUP)
        except TypeError:
            # Older Python (<3.10) uses the deprecated filter API.
            eps = importlib.metadata.entry_points()
            eps = eps.get(self.ENTRY_POINT_GROUP, [])

        for ep in eps:
            meta = PluginMetadata(
                name=ep.name,
                version="",
                description="",
                entry_point=ep,
            )
            # Try to read package metadata for version / description
            try:
                dist = ep.dist
                if dist is not None:
                    meta.version = dist.metadata["Version"] or ""
                    meta.description = dist.metadata["Summary"] or ""
            except Exception:
                logger.warning("Could not read metadata for entry point %s", ep.name)
            discovered.append(meta)
            self._metadata[ep.name] = meta

        logger.info("Discovered %d plugin(s)", len(discovered))
        return discovered

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_plugin(self, name: str) -> Plugin:
        """Load and initialise a single plugin by name.

        Args:
            name: Entry-point / plugin name.

        Returns:
            The initialised ``Plugin`` instance.

        Raises:
            PluginLoadError: If the plugin cannot be loaded or initialised.
        """
        meta = self._metadata.get(name)
        if meta is None:
            raise PluginLoadError(f"Plugin '{name}' not found in discovery results")

        try:
            plugin_class = meta.entry_point.load()
        except Exception as exc:
            err = PluginLoadError(f"Failed to load plugin class for '{name}': {exc}")
            self._errors[name] = err
            logger.error("Plugin load error: %s", err)
            raise err from exc

        try:
            plugin: Plugin = plugin_class()
        except Exception as exc:
            err = PluginLoadError(f"Failed to instantiate plugin '{name}': {exc}")
            self._errors[name] = err
            logger.error("Plugin instantiation error: %s", err)
            raise err from exc

        try:
            plugin.initialize(self._config)
        except Exception as exc:
            err = PluginLoadError(f"Failed to initialise plugin '{name}': {exc}")
            self._errors[name] = err
            logger.error("Plugin initialisation error: %s", err)
            raise err from exc

        self._plugins[name] = plugin
        logger.info("Plugin loaded successfully: %s v%s", name, getattr(plugin, "version", "?"))
        return plugin

    def load_all_plugins(self) -> List[Plugin]:
        """Load every discovered plugin.

        Broken plugins are skipped gracefully — their errors are stored
        internally and do not prevent other plugins from loading.

        Returns:
            List of successfully loaded ``Plugin`` instances.
        """
        loaded: List[Plugin] = []
        for name in list(self._metadata.keys()):
            if name in self._plugins:
                loaded.append(self._plugins[name])
                continue
            try:
                plugin = self.load_plugin(name)
                loaded.append(plugin)
            except PluginLoadError:
                logger.warning("Skipping broken plugin: %s", name)
        return loaded

    # ------------------------------------------------------------------
    # Tool access
    # ------------------------------------------------------------------

    def get_tools(self) -> List[ToolDefinition]:
        """Collect tools from all loaded plugins.

        Returns:
            Flattened list of ``ToolDefinition`` from every loaded plugin.
        """
        tools: List[ToolDefinition] = []
        for plugin in self._plugins.values():
            try:
                tools.extend(plugin.get_tools())
            except Exception as exc:
                logger.warning("Plugin '%s' raised during get_tools(): %s", plugin.name, exc)
        return tools

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_plugins(self) -> List[Dict[str, Any]]:
        """Return a summary list of all discovered plugins.

        Returns:
            List of dicts with keys ``name``, ``version``, ``description``,
            ``status`` (``loaded``, ``error``, or ``unloaded``).
        """
        result: List[Dict[str, Any]] = []
        for name, meta in self._metadata.items():
            if name in self._plugins:
                status = "loaded"
            elif name in self._errors:
                status = "error"
            else:
                status = "unloaded"
            result.append({
                "name": meta.name,
                "version": meta.version,
                "description": meta.description,
                "status": status,
            })
        return result

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown_all(self) -> None:
        """Call ``shutdown()`` on every loaded plugin."""
        for name, plugin in self._plugins.items():
            try:
                plugin.shutdown()
                logger.info("Plugin shut down: %s", name)
            except Exception as exc:
                logger.error("Error shutting down plugin '%s': %s", name, exc)
        self._plugins.clear()
