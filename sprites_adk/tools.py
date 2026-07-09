"""ADK tools backed by a Sprite sandbox.

Every tool shares the plugin's single Sprite. Tool bodies are synchronous
(sprites-py is a synchronous SDK) and are executed on a worker thread via
``asyncio.to_thread`` so they never block the agent's event loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

if TYPE_CHECKING:
    from .plugin import SpritesPlugin

logger = logging.getLogger("sprites_adk")

_DEFAULT_EXEC_TIMEOUT = 300.0

_LANGUAGE_RUNNERS = {
    "python": ("python3", "-c"),
    "javascript": ("node", "-e"),
    "bash": ("bash", "-c"),
}


def _decode(data: bytes, limit: int = 100_000) -> str:
    text = data.decode("utf-8", errors="replace")
    if len(text) > limit:
        return text[:limit] + f"\n... [truncated {len(text) - limit} characters]"
    return text


class _SpriteTool(BaseTool):
    """Base class wiring a tool to the plugin's shared Sprite."""

    def __init__(self, plugin: "SpritesPlugin", *, name: str, description: str):
        super().__init__(name=name, description=description)
        self._plugin = plugin

    async def run_async(self, *, args: Dict[str, Any], tool_context: ToolContext) -> Dict[str, Any]:
        try:
            return await asyncio.to_thread(self._run, args)
        except Exception as e:  # surface failures to the model, don't crash the run
            logger.error("%s failed: %s", self.name, e)
            return {"success": False, "error": str(e)}

    def _run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class ExecuteCommandTool(_SpriteTool):
    """Run a shell command inside the Sprite."""

    def __init__(self, plugin: "SpritesPlugin"):
        super().__init__(
            plugin,
            name="execute_command_in_sprite",
            description=(
                "Execute a shell command inside the persistent Sprite sandbox. "
                "The Sprite is a full Linux environment: installed packages, "
                "files, and background state persist between calls (and between "
                "sessions for named Sprites). Returns stdout, stderr, and the "
                "exit code."
            ),
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "command": types.Schema(
                        type=types.Type.STRING,
                        description="The shell command to execute (run with `sh -c`).",
                    ),
                    "cwd": types.Schema(
                        type=types.Type.STRING,
                        description="Working directory for the command. Optional.",
                    ),
                    "timeout": types.Schema(
                        type=types.Type.NUMBER,
                        description="Timeout in seconds (default 300).",
                    ),
                },
                required=["command"],
            ),
        )

    def _run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        command = args.get("command", "")
        if not command:
            return {"success": False, "error": "command is required"}
        sprite = self._plugin.get_sprite()
        result = sprite.run(
            "sh",
            "-c",
            command,
            capture_output=True,
            cwd=args.get("cwd"),
            timeout=float(args.get("timeout") or _DEFAULT_EXEC_TIMEOUT),
        )
        return {
            "success": result.exit_code == 0,
            "exit_code": result.exit_code,
            "stdout": _decode(result.stdout),
            "stderr": _decode(result.stderr),
        }


class ExecuteCodeTool(_SpriteTool):
    """Run a code snippet inside the Sprite."""

    def __init__(self, plugin: "SpritesPlugin"):
        super().__init__(
            plugin,
            name="execute_code_in_sprite",
            description=(
                "Execute a code snippet inside the persistent Sprite sandbox. "
                "Supports python (python3), javascript (node), and bash. For "
                "multi-file programs, write files with write_file_to_sprite and "
                "run them with execute_command_in_sprite instead."
            ),
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "code": types.Schema(
                        type=types.Type.STRING,
                        description="The code snippet to execute.",
                    ),
                    "language": types.Schema(
                        type=types.Type.STRING,
                        description="Language to run the snippet with (default python).",
                        enum=sorted(_LANGUAGE_RUNNERS),
                    ),
                    "timeout": types.Schema(
                        type=types.Type.NUMBER,
                        description="Timeout in seconds (default 300).",
                    ),
                },
                required=["code"],
            ),
        )

    def _run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        code = args.get("code", "")
        if not code:
            return {"success": False, "error": "code is required"}
        language = (args.get("language") or "python").lower()
        runner = _LANGUAGE_RUNNERS.get(language)
        if runner is None:
            return {
                "success": False,
                "error": f"unsupported language {language!r}; use one of {sorted(_LANGUAGE_RUNNERS)}",
            }
        sprite = self._plugin.get_sprite()
        result = sprite.run(
            *runner,
            code,
            capture_output=True,
            timeout=float(args.get("timeout") or _DEFAULT_EXEC_TIMEOUT),
        )
        return {
            "success": result.exit_code == 0,
            "language": language,
            "exit_code": result.exit_code,
            "stdout": _decode(result.stdout),
            "stderr": _decode(result.stderr),
        }


class WriteFileTool(_SpriteTool):
    """Write a file inside the Sprite."""

    def __init__(self, plugin: "SpritesPlugin"):
        super().__init__(
            plugin,
            name="write_file_to_sprite",
            description=(
                "Write text content to a file inside the Sprite sandbox. Parent "
                "directories are created automatically. Files persist for the "
                "lifetime of the Sprite."
            ),
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(
                        type=types.Type.STRING,
                        description="Absolute path of the file inside the Sprite.",
                    ),
                    "content": types.Schema(
                        type=types.Type.STRING,
                        description="Text content to write.",
                    ),
                },
                required=["path", "content"],
            ),
        )

    def _run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = args.get("path", "")
        content = args.get("content")
        if not path or content is None:
            return {"success": False, "error": "path and content are required"}
        sprite = self._plugin.get_sprite()
        sprite.filesystem("/").path(path).write_text(content, mkdir_parents=True)
        return {"success": True, "path": path, "bytes_written": len(content.encode("utf-8"))}


class ReadFileTool(_SpriteTool):
    """Read a file from the Sprite."""

    def __init__(self, plugin: "SpritesPlugin"):
        super().__init__(
            plugin,
            name="read_file_from_sprite",
            description="Read a text file from the Sprite sandbox and return its content.",
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(
                        type=types.Type.STRING,
                        description="Absolute path of the file inside the Sprite.",
                    ),
                },
                required=["path"],
            ),
        )

    def _run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = args.get("path", "")
        if not path:
            return {"success": False, "error": "path is required"}
        sprite = self._plugin.get_sprite()
        content = sprite.filesystem("/").path(path).read_text()
        return {"success": True, "path": path, "content": content}


class CreateCheckpointTool(_SpriteTool):
    """Snapshot the Sprite's full state."""

    def __init__(self, plugin: "SpritesPlugin"):
        super().__init__(
            plugin,
            name="create_sprite_checkpoint",
            description=(
                "Create a checkpoint of the Sprite's entire state (filesystem, "
                "installed packages, running processes). Use before risky "
                "operations - package upgrades, migrations, bulk edits - so the "
                "environment can be rolled back with restore_sprite_checkpoint."
            ),
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "comment": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Why this checkpoint is being taken, e.g. "
                            "'before-db-migration'. Strongly recommended."
                        ),
                    ),
                },
            ),
        )

    def _run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        comment = args.get("comment") or ""
        sprite = self._plugin.get_sprite()
        errors: List[str] = []
        for message in sprite.create_checkpoint(comment):
            if message.type == "error":
                errors.append(message.error or message.data or "unknown error")
        if errors:
            return {"success": False, "error": "; ".join(errors)}
        checkpoint_id: Optional[str] = None
        checkpoints = sprite.list_checkpoints()
        if checkpoints:
            newest = max(checkpoints, key=lambda c: c.create_time)
            checkpoint_id = newest.id
        return {"success": True, "checkpoint_id": checkpoint_id, "comment": comment}


class ListCheckpointsTool(_SpriteTool):
    """List the Sprite's checkpoints."""

    def __init__(self, plugin: "SpritesPlugin"):
        super().__init__(
            plugin,
            name="list_sprite_checkpoints",
            description=(
                "List the Sprite's checkpoints (id, creation time, comment), "
                "newest first. Use to find the checkpoint_id for a restore."
            ),
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        )

    def _run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        sprite = self._plugin.get_sprite()
        checkpoints = sorted(sprite.list_checkpoints(), key=lambda c: c.create_time, reverse=True)
        return {
            "success": True,
            "checkpoints": [
                {
                    "checkpoint_id": c.id,
                    "create_time": c.create_time.isoformat(),
                    "comment": c.comment or "",
                }
                for c in checkpoints
            ],
        }


class RestoreCheckpointTool(_SpriteTool):
    """Roll the Sprite back to a checkpoint. Destructive."""

    def __init__(self, plugin: "SpritesPlugin"):
        super().__init__(
            plugin,
            name="restore_sprite_checkpoint",
            description=(
                "Restore the Sprite to a previous checkpoint. DESTRUCTIVE: this "
                "rewinds the entire environment and permanently discards all "
                "changes made after the checkpoint. Confirm with the user "
                "before calling, and pass confirm=true only after they agree."
            ),
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "checkpoint_id": types.Schema(
                        type=types.Type.STRING,
                        description="ID of the checkpoint to restore (from list_sprite_checkpoints).",
                    ),
                    "confirm": types.Schema(
                        type=types.Type.BOOLEAN,
                        description=(
                            "Must be true. Set only after the user has explicitly "
                            "confirmed they accept discarding state newer than the "
                            "checkpoint."
                        ),
                    ),
                },
                required=["checkpoint_id", "confirm"],
            ),
        )

    def _run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        checkpoint_id = args.get("checkpoint_id", "")
        if not checkpoint_id:
            return {"success": False, "error": "checkpoint_id is required"}
        if args.get("confirm") is not True:
            return {
                "success": False,
                "error": (
                    "Restore not performed: restoring discards all changes made "
                    "after the checkpoint. Ask the user to confirm, then retry "
                    "with confirm=true."
                ),
            }
        sprite = self._plugin.get_sprite()
        errors: List[str] = []
        for message in sprite.restore_checkpoint(checkpoint_id):
            if message.type == "error":
                errors.append(message.error or message.data or "unknown error")
        if errors:
            return {"success": False, "error": "; ".join(errors)}
        return {"success": True, "checkpoint_id": checkpoint_id, "restored": True}
