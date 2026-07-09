"""Checkpoint / rollback: let an agent experiment fearlessly.

The agent snapshots the Sprite before a risky change; if the change breaks
the environment, it rolls back to the checkpoint instead of trying to
hand-undo the damage. Restore is destructive (it discards state newer than
the checkpoint), so the restore tool requires explicit confirmation.

    export SPRITES_TOKEN=...
    export GOOGLE_API_KEY=...
    python examples/checkpoint_rollback.py
"""

import asyncio

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from sprites_adk import SpritesPlugin

PROMPT = """
Set up a marker file /work/state.txt containing "v1".
Then create a checkpoint with the comment "before-experiment".
Then simulate a failed experiment: overwrite /work/state.txt with "broken".
Finally, restore the checkpoint (I confirm the restore - discarding the
"broken" state is exactly what I want) and read /work/state.txt to prove
the environment was rolled back.
"""


async def main() -> None:
    plugin = SpritesPlugin()  # ephemeral sprite, destroyed on close

    agent = Agent(
        model="gemini-flash-latest",
        name="rollback_agent",
        instruction=(
            "You operate a Sprite sandbox with checkpoint/restore. Before "
            "risky changes, create a checkpoint. Restoring discards newer "
            "state, so only pass confirm=true when the user has clearly "
            "agreed."
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
        new_message=types.Content(role="user", parts=[types.Part(text=PROMPT)]),
    ):
        if event.content and event.content.parts and event.content.parts[0].text:
            print(event.content.parts[0].text)

    await plugin.close()


if __name__ == "__main__":
    asyncio.run(main())
