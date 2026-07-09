# ADK docs catalog submission

This directory holds the draft page for the `google/adk-docs` integrations
catalog, per their [contributing guide](https://github.com/google/adk-docs/blob/main/CONTRIBUTING.md#integrations).

To submit, open a PR against `google/adk-docs` that adds:

1. `docs/integrations/sprites.md` — the page in this directory.
2. `docs/integrations/assets/sprites.png` — a square, card-sized Sprites
   logo (not included here; export one from the sprites.dev brand assets).
3. Optional but encouraged: screenshots of an agent session using the
   integration, also under `docs/integrations/assets/`.

Their review criteria: working/testable code examples, clear value for ADK
developers, and terms-of-service compliance. Publish `sprites-adk` to PyPI
before opening the PR so the installation instructions work.
