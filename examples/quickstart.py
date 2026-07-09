"""Quickstart: an ADK agent with a Sprites sandbox.

Prerequisites:
    pip install sprites-adk
    export SPRITES_TOKEN=...   # `sprite tokens create`
    export GOOGLE_API_KEY=...  # for the Gemini model

Run with the ADK CLI from the directory above this file:
    adk run examples
or programmatically via Runner (see persistent_environment.py).
"""

from google.adk.agents import Agent

from sprites_adk import SpritesPlugin

# No sprite_name: an ephemeral `adk-` prefixed Sprite is created on first
# tool use and destroyed when the plugin is closed.
plugin = SpritesPlugin()

root_agent = Agent(
    model="gemini-flash-latest",
    name="sprite_agent",
    instruction=(
        "You help users build and test code inside a persistent Linux "
        "sandbox (a Sprite). Run commands and code in the sandbox, not "
        "locally. Create a checkpoint before risky operations such as "
        "package installs or migrations."
    ),
    tools=plugin.get_tools(),
)
