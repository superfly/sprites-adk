# ADK docs catalog submission

This directory holds the draft page for the `google/adk-docs` integrations
catalog, per their [contributing guide](https://github.com/google/adk-docs/blob/main/CONTRIBUTING.md#integrations).

To submit, open a PR against `google/adk-docs` that copies:

1. `sprites.md` (this directory) → `docs/integrations/sprites.md`.
2. `assets/sprites.png` (this directory) → `docs/integrations/assets/sprites.png`.
   The Sprites brandmark, squared to 1000×1000 on a transparent canvas.
3. Optional but encouraged: screenshots of an agent session using the
   integration, also under `docs/integrations/assets/`.

Their review criteria: working/testable code examples, clear value for ADK
developers, and terms-of-service compliance. `sprites-adk` is published on
PyPI (https://pypi.org/project/sprites-adk/), so the install instructions
in the page work as written.
