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
| Read | `GET /health`, `/methods`, `/rules`, `/datasets`, `/observations`, `/targets`, `/runs`, `/runs/default`, `/runs/{id}/results`, `/runs/{id}/observations/{observation_id}/fold`, `/jobs/{id}`, `/artifacts/{id}`, `/artifacts/{id}/content` |
| Check without a write | `POST /runs/estimate` |
| Write | `POST /datasets/{id}/index`, `POST /runs`, `POST /jobs/{id}/cancel` |

## Same view as the frontend

The frontend shows only values that the API supplies, and it applies only API rules. Use these operations to see what Richard sees:

| Frontend view | API operation |
|---|---|
| Target table, sky markers, and marker colours | `GET /targets?run_id=<run>`. Each row has sky position, magnitude, labels, the run's search values, and `status`. |
| Search field | `GET /targets?q=<query>`. The grammar is `target-query/1`, for example `snr>20 err<0.01 wasp`. |
| The run shown without a choice | `GET /runs/default` (rule `default-run/1`). |
| Phase fold and its binned means | `GET /runs/{run}/observations/{observation}/fold`. Add `period=<days>` for a display fold. A fold is a display calculation, not a stored result. |
| Work estimate and parameter check in the run form | `POST /runs/estimate` with the body of `POST /runs`. It writes nothing. |

`GET /rules` describes each named rule. A rule name has a version, for example `period-agreement/1`.
The `status` values are `match`, `near`, `miss`, `signal`, `eb`, and `quiet`. They are display bins from unvalidated thresholds.
Do not use a status as evidence. Do not count statuses as a progress measure.
`GET /targets` returns at most 5000 rows for each request. Use `offset` for more rows. The `total` field gives the number of matches.

Each request needs your client token: `Authorization: Bearer <token>`. Richard creates the token for your campaign.
Without a valid token the API gives 401. Without the permission for an operation it gives 403.
An agent token can hold `read`, `run.submit`, and `record.write`. Acquisition, identity reveal, and administration stay with Richard.
Each run records the client that created it. You can cancel only the jobs of your own runs.
Use the API port 30870. Do not use the frontend port 30871.
The API has no candidate, assessment, decision, note, or agent-task records.

## Campaign rules in the API

Your token belongs to one campaign. `GET /me` gives its `campaign_id`. `GET /campaigns/{id}` gives the campaign, its budgets, and its use.
The API applies these rules to each of your requests:

| Rule | API behaviour |
|---|---|
| Approval | Before Richard approves the campaign, observation reads give 403. After the campaign closes, reads and writes give 403. |
| Blinding | The campaign level is `open`, `labels`, or `labels_identity`. The default is `labels_identity`. Withheld values are null or absent. Each response names them in `withheld`. A filter, query field, text search, or sort on a withheld value gives 422. |
| Cohort guard | Lists leave out observations that an evaluation reservation protects. `protected_excluded` gives their number. A read gives 403, and a run request gives 422. The API records each refusal. |
| Budgets | `observations_read`, `jobs`, `compute_seconds`, and `storage_bytes`. A request past a limit gives 403. `POST /runs/estimate` shows the budget state after the run. |
| Fixed decisions | `POST /campaigns/{id}/fix-decisions` fixes your decisions. After it, new runs give 403. Richard then records the reveal, and blinding ends. |

A 503 response means that the cohort guard cannot read the register. Stop and report it.
The `labels` level withholds `labels`, `label_class`, `planet_name`, `reference_period_days`, `relative_period_error`, `status`, and `reference_comparison` values.
The `labels_identity` level also withholds `target_id`, `relative_path`, `sha256`, sky position, and identifying header keywords.

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
3. Use the write endpoints only in a campaign that Richard approved. The API also enforces this rule.
4. Stay inside the campaign budgets. Stop at each stop condition. A budget refusal from the API is a stop condition.
5. Do not try to find withheld values from other sources before the reveal. Identity comparison is a worker method, not an agent task.
6. Do not try again after a cohort guard refusal. Report the refused observation.
7. Record each observation that you read in the campaign's touched list. `observations_read` in the budget state gives the API count.
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
