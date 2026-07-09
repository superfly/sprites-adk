"""A persistent development environment that survives across sessions.

Because the Sprite is named, every run of this script attaches to the SAME
Linux environment: packages installed yesterday are still installed today,
files are still there, and the agent picks up where it left off. Sprites
suspend automatically when idle, so a parked environment costs (almost)
nothing.

    export SPRITES_TOKEN=...
    export GOOGLE_API_KEY=...
    python examples/persistent_environment.py "install uv and create a fastapi project in /app"
    # ...later, a new process, same environment:
    python examples/persistent_environment.py "add a /health endpoint to the project in /app"
"""

import asyncio
import sys

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from sprites_adk import SpritesPlugin


async def main() -> None:
    prompt = " ".join(sys.argv[1:]) or "What is in /app? Summarize the project state."

    # Named sprite: reused across sessions, never auto-destroyed.
    plugin = SpritesPlugin(sprite_name="my-dev-environment")

    agent = Agent(
        model="gemini-flash-latest",
        name="dev_env_agent",
        instruction=(
            "You maintain a long-lived development environment inside a "
            "Sprite. All commands, code, and files run inside the Sprite. "
            "It persists between sessions, so check existing state before "
            "assuming a fresh machine. Create a checkpoint before risky "
            "changes."
        ),
        tools=plugin.get_tools(),
    )

    runner = InMemoryRunner(agent=agent, plugins=[plugin])
    session = await runner.session_service.create_session(
        app_name=runner.app_name, user_id="demo"
    )
    async for event in runner.run_async(
        user_id="demo",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        if event.content and event.content.parts and event.content.parts[0].text:
            print(event.content.parts[0].text)

    await plugin.close()  # named sprite is preserved


if __name__ == "__main__":
    asyncio.run(main())
