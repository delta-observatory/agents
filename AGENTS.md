# Instructions for agent tooling

Read [README.md](README.md) before work in this repository.
Read the [workspace instructions](../AGENTS.md).
Follow the boundary and the rules in [README.md](README.md).

Use the API at `http://10.0.0.47:30870/api`.
Read the API description at `http://10.0.0.47:30870/api/openapi.json`.
Do not read or write PostgreSQL directly.
Do not read `raw/` or the artifact volume directly.
Do not define job, result, method-parameter, or record shapes in this repository.
Keep lab outputs outside the workspace.
Do not submit observations or candidates to external services.

Write documentation as current state. Follow the [workspace documentation style](../AGENTS.md#documentation-style).

## Commits

Follow the commit rules in the [workspace instructions](../AGENTS.md#commits).
Do not commit credentials, tokens, or environment files.
Keep [AGENTS.md](AGENTS.md) and [CLAUDE.md](CLAUDE.md) identical.
