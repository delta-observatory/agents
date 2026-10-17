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
| Read records | `GET /candidates`, `/candidates/{id}`, `/assessments`, `/decisions`, `/notes`, `/tasks`, `/tasks/{id}` |
| Check without a write | `POST /runs/estimate` |
| Write | `POST /runs`, `POST /jobs/{id}/cancel` |
| Write records | `POST /candidates`, `/assessments`, `/decisions`, `/notes`, `/tasks`, `/tasks/claim`, `/tasks/{id}/heartbeat`, `/tasks/{id}/release`, `/tasks/{id}/report`, `/tasks/{id}/cancel` |

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

## Research records

Write your work as records through the API. Each record is a document of its contract in [database/contracts/records/](../database/contracts/README.md#research-records).
Put the contract name in the `contract` field, for example `"contract": "candidate/1"`.
Records do not change. Write a new record to correct one, and name the earlier record in `supersedes`.

| Record | Use |
|---|---|
| Candidate | A signal that you propose. Give its observations and evidence. Use tier `platform` when the evidence includes a measurement or a job of a worker method. Use tier `lab` for evidence from your own code. |
| Decision | Your judgment about a candidate. Use judge `model`. Give the question, your judged evidence status, one action, and your reason. Give the model, the packet checksum, and the policy, or the reason that each is unknown. |
| Assessment | The evidence status from your decision. Use axis `evidence`, basis `model_judgment`, and the `decision_id`. |
| Note | Free text about records. A note changes no value. |
| Agent task | A unit of work for the agents of your campaign. |

Keep these items apart:

- Measurements come from worker methods. Refer to them by `measurement` ID. Do not copy their values into a candidate.
- Your judgment is a model judgment. Scores in a decision are judgments, not uncertainties or probabilities.
- The evidence status of a candidate comes from the newest evidence assessment (rule `candidate-status/1`).
- The identity status comes from identity comparison. You cannot write it. A campaign that withholds labels hides it from you until the reveal.

A reference names a record by `kind` and `id`, or an external file by `uri`, `sha256`, and `bytes`.
Give each lab file that supports a candidate as an external reference with its SHA-256.
A reference to a record of another campaign, a withheld value, or a protected observation gives 422.

After `fix-decisions`, the API refuses new candidates, decisions, and evidence assessments in your campaign. Notes and tasks continue until the close.
Each decision records the values that blinding withheld from you.

## Agent tasks

Agent tasks coordinate the agents of one campaign. No coordinator agent is necessary.

1. Claim a task: `POST /tasks/claim` with `{}`, or with `{"kinds": ["vetting"]}`. A null `task` means that no task is available.
2. Keep the `lease_id` of the claim. Extend the lease with `POST /tasks/{id}/heartbeat` before `lease_expires_at`.
3. End the task with `POST /tasks/{id}/report` and an `agent-task-report/1` document. Give the records that you wrote as `outputs`.
4. If you cannot finish, release the task with `POST /tasks/{id}/release`, or report it as `failed` with a reason.

A 409 response to a lease operation means that your lease ended. Stop the work on that task. Do not write its report.
A task whose lease expires goes to the next claim. After the last permitted attempt, the task becomes `failed`.

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
5. Do not try to find withheld values from other sources before the reveal. Do not write withheld values in record text. Identity comparison is a worker method, not an agent task.
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
3. Candidates, with evidence status and identity status kept separate. Give the ID of each candidate and decision record.
4. Failures and limits.
5. The touched list.
6. Proposed changes, each with the component repository that owns it.

Label each model judgment as a model judgment. Keep judgments separate from measurements.
