# sprites-adk

Google [ADK](https://google.github.io/adk-docs/) integration for [Sprites](https://sprites.dev) — persistent, stateful Linux sandboxes for AI agents, with checkpoint/restore, from [Fly.io](https://fly.io).

Most agent sandboxes are ephemeral: the environment vanishes when the session ends. A Sprite is a **stateful Linux microVM** that suspends when idle and keeps everything — files, packages, databases, running services — so your agent can resume yesterday's environment today. And because Sprites support **checkpoints**, your agent can snapshot the whole environment before a risky change and roll back if it goes wrong.

## Installation

```sh
pip install sprites-adk
```

You'll need a Sprites API token ([get started](https://docs.sprites.dev/quickstart/)):

```sh
export SPRITES_TOKEN=...
```

## Quickstart

```python
from google.adk.agents import Agent
from sprites_adk import SpritesPlugin

plugin = SpritesPlugin()  # or SpritesPlugin(sprite_name="my-project") for a persistent env

root_agent = Agent(
    model="gemini-flash-latest",
    name="sprite_agent",
    instruction="Run code and commands in the Sprite sandbox, not locally.",
    tools=plugin.get_tools(),
)
```

Pass the plugin to your runner to get lifecycle callbacks and error handling:

```python
runner = InMemoryRunner(agent=root_agent, plugins=[plugin])
```

## Two modes

| | `SpritesPlugin()` | `SpritesPlugin(sprite_name="my-project")` |
|---|---|---|
| Sprite name | auto-generated `adk-…` | yours |
| Reused across sessions | no | **yes — full state persists** |
| Destroyed on `plugin.close()` | yes | no |

The Sprite is created lazily on first tool use; constructing the agent needs no network. Sprites suspend automatically when idle — a parked environment costs (almost) nothing.

## Tools

| Tool | Description |
|---|---|
| `execute_command_in_sprite` | Run a shell command (cwd, timeout supported) |
| `execute_code_in_sprite` | Run a Python / JavaScript / bash snippet |
| `write_file_to_sprite` | Write a text file (parents auto-created) |
| `read_file_from_sprite` | Read a text file |
| `create_sprite_checkpoint` | Snapshot the entire environment |
| `list_sprite_checkpoints` | List checkpoints, newest first |
| `restore_sprite_checkpoint` | Roll back to a checkpoint (**destructive**, requires `confirm=true`) |

All tools return structured dicts (`success`, `stdout`/`stderr`/`exit_code`, …); failures come back as `{"success": false, "error": ...}` so the agent can adapt instead of crashing the run.

File reads and writes run as commands inside the Sprite (via `base64`, so quotes/newlines/unicode survive) rather than through a separate filesystem API. That keeps them consistent with everything else the agent does — in particular, files written this way are correctly reverted by `restore_sprite_checkpoint`. `write_file_to_sprite` is capped at 256 KB; generate larger files with a command inside the Sprite. `/tmp` is tmpfs and is not captured by checkpoints.

### A note on restore

`restore_sprite_checkpoint` rewinds the **whole environment** and permanently discards anything newer than the checkpoint. The tool refuses to run unless `confirm=true` is passed, and its description instructs the model to get explicit user confirmation first.

## Configuration

```python
SpritesPlugin(
    token=None,                # default: $SPRITES_TOKEN
    sprite_name=None,          # default: auto-generated "adk-…"
    plugin_name="sprites_plugin",
    base_url="https://api.sprites.dev",
    destroy_on_close=None,     # default: True if unnamed, False if named
    client_timeout=600.0,      # HTTP timeout for Sprites API calls
)
```

## Examples

- [`examples/quickstart.py`](examples/quickstart.py) — minimal agent
- [`examples/persistent_environment.py`](examples/persistent_environment.py) — a named dev environment that survives across sessions
- [`examples/checkpoint_rollback.py`](examples/checkpoint_rollback.py) — snapshot, break things, roll back

## Attribution

So Fly.io can estimate how much Sprites usage is agent-driven, this plugin declares itself as ADK by setting `FLY_INVOKED_BY=google-adk` (only if unset — an explicit value is never overwritten). Sprites API calls then carry a coarse, privacy-safe [client-signals](https://github.com/superfly/client-signals) marker (`agent=google-adk`). It's advisory only — never used for gating or rate-limiting — and you can opt out by setting `FLY_INVOKED_BY` to your own value.

## Resources

- [Sprites docs](https://docs.sprites.dev)
- [Sprites Python SDK](https://github.com/superfly/sprites-py)
- [Google ADK docs](https://google.github.io/adk-docs/)

## License

MIT
