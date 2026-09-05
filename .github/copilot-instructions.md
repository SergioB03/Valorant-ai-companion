# Repository Workflow

- Document every repository change in the relevant README, architecture, deployment, security, or change record documentation. Keep the documentation in the same change as the code.
- Before starting a major change to the frontend, UI, or a user-facing workflow, capture screenshots of the current affected state. Store them under `docs/changes/<date>-<slug>/` (e.g. `docs/changes/2026-09-05-optimization-waves/`) next to that change's README, using descriptive names (`before-desktop.png`, `after-mobile.png`, ...), and reference them from the change documentation.
- After a major user-facing change, capture updated screenshots and document the before/after behavior, affected routes, and any known limitations.
- Treat a change as major when it changes a primary screen, navigation, layout, visual design, user workflow, API contract, deployment behavior, or security behavior. For backend-only refactors with no user-visible impact, screenshots are not required.