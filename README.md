# Delta Observatory agents

This repository is one component of [Delta Observatory](https://github.com/delta-observatory/delta-observatory). The entry repository describes the application and restores every component.

This repository holds tooling for research agents that use Delta Observatory.
Agents use the same control surface as the frontend: the HTTP API.
An agent sees the same data and takes the same actions as Richard in the frontend.

## Current state

The repository contains the agent instructions, the [operating manual](MANUAL.md), the [campaign template](templates/campaign.md), the [adapter](adapter/README.md), and the [research importer](importer/README.md).
The adapter is an MCP server over stdio. It makes one tool for each operation in the API description.
The importer writes research records from an explicit import manifest through the API, with import keys.
The API has client tokens, permissions, and campaigns with budgets, blinding, and the cohort guard.
It keeps agent records: candidates, assessments, decisions, notes, and agent tasks with leases.
[DESIGN.md](https://github.com/delta-observatory/delta-observatory/blob/main/DESIGN.md) defines the target agent control surface. [ROADMAP.md](https://github.com/delta-observatory/delta-observatory/blob/main/ROADMAP.md) stage R8 tracks its delivery.

The [managed desktop host](managed/README.md) connects an approved investigation to isolated Codex or Claude Code.
It requires explicit consent before sending permitted evidence to the provider.

## Boundary

| Belongs in this repository | Stays in its current owner |
|---|---|
| An MCP adapter generated from the OpenAPI document, with no logic | API endpoints, in [backend/](https://github.com/delta-observatory/backend/blob/main/README.md) |
| The operating manual for agents, and role prompts | Contracts and record shapes, in [database/contracts/](https://github.com/delta-observatory/database/blob/main/contracts/README.md) |
| Campaign templates: selection rule, budgets, and stop conditions | Scientific methods, in [workers/](https://github.com/delta-observatory/workers/blob/main/README.md) |
| The template for a lab sandbox | Lab outputs, outside the workspace |
| Agent evaluation harnesses, for example triage scoring against labels | Experiment records, in [experiments/](https://github.com/delta-observatory/experiments/blob/main/README.md) (private) |
| Notes about the agent surface | Agent records, in PostgreSQL through the API |

## Tests

```bash
python3 -m unittest discover -s adapter/tests -t .
python3 -m unittest discover -s importer/tests -t .
```

The tests use a stub HTTP server. They do not use the running API.

## Rules

1. Agent code uses the API only. The API address is `$DELTA_API_URL`, by default `http://localhost:30870/api`.
2. Agent code receives no `DATABASE_URL`, no `raw/` mount, and no artifact-volume mount.
3. This repository defines no job, result, method-parameter, or record shapes. Put a new shape in `database/contracts/` first.
4. Keep lab outputs outside the workspace. Each lab run uses its own directory.
5. Agent code does not submit observations or candidates to external services. Richard makes each external submission.

## Layout

| Path | Content |
|---|---|
| [prompts/exoplanet-search-continuation.md](prompts/exoplanet-search-continuation.md) | Continuation prompt for bounded TESS research with deferred candidate follow-up. |
| [MANUAL.md](MANUAL.md) | Current control surface, data, methods, rules, and report format for agents. |
| [templates/campaign.md](templates/campaign.md) | Campaign fields to complete and approve before data access. |
| [adapter/](adapter/README.md) | MCP adapter: `generate.py` makes tools from the API description, and `server.py` serves them over stdio. |
| [importer/](importer/README.md) | Research importer: `import_records.py` and the `research-import/1` manifest format. |
| [imports/](imports/) | Import manifests. Each manifest lists its files with SHA-256 and size. |
| [campaigns/](campaigns/) | Approved campaign files. `adapter-check.md` is the file of the functional adapter check. |
| `checks/adapter_lifecycle.py` | Functional check: one agent task through the adapter, with three requests that the API must refuse. Run `DELTA_TOKEN_FILE=<agent token file> python3 -m checks.adapter_lifecycle` in `agents/`. |

## Planned contents

| Content | Dependency |
|---|---|
| Lab sandbox template | None |
| Triage evaluation harness | Labeled evaluation examples. The candidate, assessment, and decision records exist. |

## License

The code is under the [MIT License](LICENSE).
