"""SpritesPlugin: Google ADK plugin for Sprites stateful sandboxes."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import uuid
from typing import Any, Dict, List, Optional

from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from sprites import NotFoundError, Sprite, SpritesClient

from .tools import (
    CreateCheckpointTool,
    ExecuteCodeTool,
    ExecuteCommandTool,
    ListCheckpointsTool,
    ReadFileTool,
    RestoreCheckpointTool,
    WriteFileTool,
)

logger = logging.getLogger("sprites_adk")

_DEFAULT_BASE_URL = "https://api.sprites.dev"


class SpritesPlugin(BasePlugin):
    """Manages a Sprite sandbox and exposes it to an ADK agent as tools.

    A Sprite is a persistent, stateful Linux microVM. Unlike ephemeral
    sandboxes, a named Sprite keeps its filesystem, installed packages, and
    running state between agent sessions, and automatically suspends when
    idle (you only pay while it is doing work).

    Two usage modes:

    * ``SpritesPlugin(sprite_name="my-project")`` - get-or-create a named,
      persistent Sprite. The environment survives across sessions and is
      never destroyed automatically.
    * ``SpritesPlugin()`` - auto-generate an ``adk-`` prefixed Sprite for
      this plugin instance and destroy it when the plugin is closed.

    The Sprite is created lazily on first tool use, so constructing the
    plugin (and your agent) does not require network access.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        sprite_name: Optional[str] = None,
        *,
        plugin_name: str = "sprites_plugin",
        base_url: str = _DEFAULT_BASE_URL,
        destroy_on_close: Optional[bool] = None,
        client_timeout: float = 600.0,
    ):
        """Initialize the plugin.

        Args:
            token: Sprites API token. Falls back to the ``SPRITES_TOKEN``
                environment variable.
            sprite_name: Name of the Sprite to use. If it exists it is
                reused (with all of its state); otherwise it is created.
                When omitted, a random ``adk-`` prefixed name is generated.
            plugin_name: ADK plugin identifier.
            base_url: Sprites API base URL.
            destroy_on_close: Whether ``close()`` destroys the Sprite.
                Defaults to True for auto-generated names and False for
                user-supplied names (persistent environments).
            client_timeout: HTTP timeout in seconds for Sprites API calls.
                Long-running exec calls stream, so keep this generous.
        """
        super().__init__(name=plugin_name)
        token = token or os.environ.get("SPRITES_TOKEN", "")
        if not token:
            raise ValueError(
                "A Sprites API token is required. Pass token=... or set the "
                "SPRITES_TOKEN environment variable. Create one with: "
                "`sprite tokens create` (https://docs.sprites.dev)."
            )

        if sprite_name:
            self.sprite_name = sprite_name
            self._destroy_on_close = bool(destroy_on_close) if destroy_on_close is not None else False
        else:
            self.sprite_name = f"adk-{uuid.uuid4().hex[:8]}"
            self._destroy_on_close = True if destroy_on_close is None else bool(destroy_on_close)

        self._client = SpritesClient(token=token, base_url=base_url, timeout=client_timeout)
        self._sprite: Optional[Sprite] = None
        self._lock = threading.Lock()
        self._tools = [
            ExecuteCommandTool(self),
            ExecuteCodeTool(self),
            WriteFileTool(self),
            ReadFileTool(self),
            CreateCheckpointTool(self),
            ListCheckpointsTool(self),
            RestoreCheckpointTool(self),
        ]

    # -- Sprite lifecycle ---------------------------------------------------

    def get_sprite(self) -> Sprite:
        """Return the managed Sprite, creating it on first use.

        Reuses the existing Sprite when one with ``sprite_name`` already
        exists; otherwise creates it. Thread-safe (tool calls run in worker
        threads).
        """
        with self._lock:
            if self._sprite is None:
                try:
                    self._sprite = self._client.get_sprite(self.sprite_name)
                    logger.info("Reusing existing sprite %r", self.sprite_name)
                except NotFoundError:
                    logger.info("Creating sprite %r", self.sprite_name)
                    self._sprite = self._client.create_sprite(self.sprite_name)
            return self._sprite

    def destroy_sprite(self) -> None:
        """Destroy the managed Sprite and all of its state. Irreversible."""
        with self._lock:
            try:
                self._client.destroy_sprite(self.sprite_name)
                logger.info("Destroyed sprite %r", self.sprite_name)
            except NotFoundError:
                pass
            self._sprite = None

    async def close(self) -> None:
        """Release resources; destroys the Sprite if ``destroy_on_close``."""
        if self._destroy_on_close:
            await asyncio.to_thread(self.destroy_sprite)
        await asyncio.to_thread(self._client.close)

    # -- ADK surface ----------------------------------------------------------

    def get_tools(self) -> List[BaseTool]:
        """Return the Sprites tools to pass to an ADK ``Agent``."""
        return list(self._tools)

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: Dict[str, Any],
        tool_context: ToolContext,
    ) -> Optional[Dict[str, Any]]:
        if self._is_ours(tool):
            logger.debug("Sprite tool %s args=%s", tool.name, tool_args)
        return None

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: Dict[str, Any],
        tool_context: ToolContext,
        result: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if self._is_ours(tool) and isinstance(result, dict) and result.get("error"):
            logger.warning("Sprite tool %s returned error: %s", tool.name, result["error"])
        return None

    async def on_tool_error_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: Dict[str, Any],
        tool_context: ToolContext,
        error: Exception,
    ) -> Optional[Dict[str, Any]]:
        if not self._is_ours(tool):
            return None
        logger.error("Sprite tool %s raised: %s", tool.name, error)
        # Surface the failure to the model as a structured result so the
        # agent can adapt instead of the run aborting.
        return {"success": False, "error": str(error)}

    def _is_ours(self, tool: BaseTool) -> bool:
        return any(t.name == tool.name for t in self._tools)
