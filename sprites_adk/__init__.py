"""Google ADK integration for Sprites (https://sprites.dev).

Gives ADK agents a persistent, stateful Linux sandbox with checkpoint and
restore, backed by Fly.io's Sprites.
"""

from .plugin import SpritesPlugin
from .tools import (
    CreateCheckpointTool,
    ExecuteCodeTool,
    ExecuteCommandTool,
    ListCheckpointsTool,
    ReadFileTool,
    RestoreCheckpointTool,
    WriteFileTool,
)

__version__ = "0.1.1"

__all__ = [
    "SpritesPlugin",
    "ExecuteCommandTool",
    "ExecuteCodeTool",
    "WriteFileTool",
    "ReadFileTool",
    "CreateCheckpointTool",
    "ListCheckpointsTool",
    "RestoreCheckpointTool",
    "__version__",
]
