# Delta Observatory agents

This repository holds tooling for research agents that use Delta Observatory.
Agents use the same control surface as the frontend: the HTTP API.
An agent sees the same data and takes the same actions as Richard in the frontend.

## Current state

The repository contains the agent instructions, the [operating manual](MANUAL.md), and the [campaign template](templates/campaign.md). No agent code exists.
The API has no access control, campaign budgets, blinding policy, or agent records.
[DESIGN.md](../DESIGN.md) defines the target agent control surface. [ROADMAP.md](../ROADMAP.md) stage R8 tracks its delivery.

## Boundary

| Belongs in this repository | Stays in its current owner |
|---|---|
| An MCP adapter generated from the OpenAPI document, with no logic | API endpoints, in [backend/](../backend/README.md) |
| The operating manual for agents, and role prompts | Contracts and record shapes, in [database/contracts/](../database/contracts/README.md) |
| Campaign templates: selection rule, budgets, and stop conditions | Scientific methods, in [workers/](../workers/README.md) |
| The template for a lab sandbox | Lab outputs, outside the workspace |
| Agent evaluation harnesses, for example triage scoring against labels | Experiment records, in [experiments/](../experiments/README.md) |
| Notes about the agent surface | Agent records, in PostgreSQL through the API |

## Rules

1. Agent code uses the API only. The API address is `http://10.0.0.47:30870/api`.
2. Agent code receives no `DATABASE_URL`, no `raw/` mount, and no artifact-volume mount.
3. This repository defines no job, result, method-parameter, or record shapes. Put a new shape in `database/contracts/` first.
4. Keep lab outputs outside the workspace. Each lab run uses its own directory.
5. Agent code does not submit observations or candidates to external services. Richard makes each external submission.

## Layout

| Path | Content |
|---|---|
| [MANUAL.md](MANUAL.md) | Current control surface, data, methods, rules, and report format for agents. |
| [templates/campaign.md](templates/campaign.md) | Campaign fields to complete and approve before data access. |

## Planned contents

| Content | Dependency |
|---|---|
| Lab sandbox template | None |
| MCP adapter | API parity with the frontend, and API access control |
| Triage evaluation harness | Candidate, assessment, and decision records in a later contract version |
