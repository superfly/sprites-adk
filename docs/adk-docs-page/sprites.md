---
catalog_title: Sprites
catalog_description: Persistent, stateful Linux sandboxes with checkpoint/restore for agent code execution, by Fly.io
catalog_icon: /integrations/assets/sprites.png
---

# Sprites

[Sprites](https://sprites.dev) are persistent, stateful Linux sandboxes from [Fly.io](https://fly.io). Unlike ephemeral sandboxes, a Sprite keeps its filesystem, installed packages, and services between sessions — it suspends when idle and resumes in milliseconds. The `sprites-adk` plugin gives ADK agents a full Linux environment with a capability most sandboxes don't have: **checkpoint and restore**, so an agent can snapshot the environment before a risky change and roll back if it goes wrong.

Supported in ADK Python.

## Use cases

- **Persistent development environments**: a named Sprite is reused across agent sessions — packages installed yesterday are still there today, so long-running projects don't rebuild the world every session.
- **Secure code execution**: run Python, JavaScript, or bash produced by the model in an isolated microVM instead of the host machine.
- **Fearless experimentation**: checkpoint the entire environment before package upgrades, migrations, or bulk edits; restore if the experiment breaks it.
- **File workflows**: write scripts and data into the sandbox, run them, and read results back.

## Prerequisites

- A [Sprites account and API token](https://docs.sprites.dev/quickstart/) (`sprite tokens create`), exported as `SPRITES_TOKEN`.
- A Google API key for the Gemini model used by your agent.

## Installation

```sh
pip install sprites-adk
```

## Use with agent

```python
from google.adk.agents import Agent
from sprites_adk import SpritesPlugin

# SpritesPlugin() creates an ephemeral sandbox, destroyed on plugin.close().
# SpritesPlugin(sprite_name="my-project") attaches to a persistent environment
# that keeps all state between sessions and is never destroyed automatically.
plugin = SpritesPlugin()

root_agent = Agent(
    model="gemini-flash-latest",
    name="sprite_agent",
    instruction=(
        "Run code and commands inside the Sprite sandbox, not locally. "
        "Create a checkpoint before risky operations."
    ),
    tools=plugin.get_tools(),
)
```

For lifecycle callbacks and structured tool-error handling, also register the plugin with your runner:

```python
from google.adk.runners import InMemoryRunner

runner = InMemoryRunner(agent=root_agent, plugins=[plugin])
```

The Sprite is created lazily on first tool use. Named Sprites are get-or-create: if a Sprite with that name already exists, the agent attaches to it with all of its state intact.

## Available tools

| Tool | Description |
| --- | --- |
| `execute_command_in_sprite` | Run a shell command with optional working directory and timeout. |
| `execute_code_in_sprite` | Run a Python, JavaScript, or bash snippet. |
| `write_file_to_sprite` | Write a text file (parent directories auto-created). |
| `read_file_from_sprite` | Read a text file from the sandbox. |
| `create_sprite_checkpoint` | Snapshot the entire environment (filesystem, packages, processes). |
| `list_sprite_checkpoints` | List checkpoints, newest first. |
| `restore_sprite_checkpoint` | Roll back to a checkpoint. Destructive — discards newer state and requires explicit `confirm=true`. |

## Resources

- [sprites-adk on PyPI](https://pypi.org/project/sprites-adk/)
- [Source code and examples](https://github.com/fly-apps/sprites-adk)
- [Sprites documentation](https://docs.sprites.dev)
