# Agent operating manual

This manual tells a research agent how to work with Delta Observatory.
It describes the current API, data, and methods, and the rules for agent work.
[DESIGN.md](../DESIGN.md) describes the target agent control surface. This manual describes what exists.

## Control surface

The HTTP API is the only control surface. The frontend uses the same API.
The API address is `http://10.0.0.47:30870/api`.
The API description is at `http://10.0.0.47:30870/api/openapi.json`.
[backend/README.md](../backend/README.md) describes each endpoint.

| Operation | Endpoints |
|---|---|
| Read | `GET /health`, `/methods`, `/datasets`, `/observations`, `/runs`, `/jobs/{id}`, `/artifacts/{id}`, `/artifacts/{id}/content` |
| Write | `POST /datasets/{id}/index`, `POST /runs`, `POST /jobs/{id}/cancel` |

The API has no access control. Any client can use the write endpoints.
The API has no campaign, candidate, assessment, decision, note, or agent-task records.
The API returns known-object labels in observation responses: `labels.class` and `labels.planets`.

## Data and methods

| Item | Current state |
|---|---|
| Indexed data | 46 TESS SPOC light curves. All are development data in the [cohort register](../experiments/COHORTS.md). |
| `tess-spoc-index` v1 | Ingestion only. No scientific calculation. |
| `tess-bls` v1 | Provisional transit search with the fixed T01 defaults. Depth accuracy, completeness, and false-alarm rates are not validated. |
| Acquisition | No API method. The platform has no data for new-object search. |

A lab pass on 120 TESS sector-56 light curves gives one known limit.
At every tested depth SNR threshold, `tess-bls` finds almost the same number of detections in real and inverted light curves.
Treat `tess-bls` threshold detections as unvalidated. The lab report is `~/repos/delta-lab/FINDINGS.md`. It is a lab result, not platform evidence.

## Rules

1. Use the API only. Do not read PostgreSQL, `raw/`, or the artifact volume directly.
2. Write a campaign file from the [campaign template](templates/campaign.md) before you read observation data.
3. Use the write endpoints only in a campaign that Richard approved.
4. Stay inside the campaign budgets. Stop at each stop condition.
5. In a blind campaign, do not use the `class` filter. Do not read `labels` fields before the campaign decisions are fixed.
6. Check the cohort register before you read observations. Do not read an observation that an evaluation reservation holds.
7. Record each observation that you read in the campaign's touched list.
8. Call each signal a "candidate". Do not call a signal a discovery or a new planet.
9. Keep lab code and lab outputs outside the workspace. A lab result is a proposal, not platform evidence.
10. Measure progress with calculated measures, for example excess over controls. Do not count your own judgments as progress.
11. Do not submit observations or candidates to an external service. Richard makes each external submission.
12. Do not change files in another component repository. Record a needed change in your report.

## Report

At the end of a campaign, write a report with these parts:

1. Summary: at most 10 lines.
2. Progress measures, each with its denominator and its comparison.
3. Candidates, with evidence status and identity status kept separate.
4. Failures and limits.
5. The touched list.
6. Proposed changes, each with the component repository that owns it.

Label each model judgment as a model judgment. Keep judgments separate from measurements.
