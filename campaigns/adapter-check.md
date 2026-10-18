# Campaign: adapter-check

This campaign is a functional check of the agent adapter. It is not a scientific campaign.
One agent client claims one task through the adapter, reads one stored result, writes its records, and ends the task.

## Objective

| Field | Value |
|---|---|
| Question | Does the generated adapter carry one agent task through claim, reads, record writes, and the report, under the campaign rules of the API? |
| Programme | TESS transits |
| Tier | Platform |
| Strongest permitted conclusion | The adapter and the API complete one task lifecycle. The records carry no scientific judgment. |
| Owner | Agent client `adapter-check-agent` |

## Selection

| Field | Value |
|---|---|
| Dataset IDs | `tess-spoc-light-curves` |
| Selection rule | The task names one job of the run "Slice check: T01 defaults on all development light curves". The agent reads no other observation. |
| Sample size | 1 observation |
| Cohort register check | The observation belongs to the development entry `application-vertical-slice-tess-development`. No evaluation reservation exists. |
| Blinding | `labels_identity` (default). No reveal is planned. |

## Method

| Field | Value |
|---|---|
| Methods and versions | Stored results of `tess-bls` v1. The agent submits no run. |
| Parameters | None |
| Controls | None. The check makes no scientific measurement. |
| Injections | None |
| Identity comparison | None |

## Measures and criteria

| Field | Value |
|---|---|
| Progress measures | None. The check measures no scientific progress. |
| Comparison | None |
| Positive, negative, and inconclusive outcomes | Positive: the task ends `complete` with its outputs, and the API refuses each prohibited action in the check. Negative: a step fails. |
| Resulting action for each outcome | Positive: close the campaign. Negative: record the defect and close the campaign. |

## Budgets

| Resource | API budget key | Limit |
|---|---|---:|
| Observations read | `observations_read` | 2 |
| Jobs submitted | `jobs` | 0 |
| Worker time (s) | `compute_seconds` | 0 |
| Artifact storage (bytes) | `storage_bytes` | 0 |
| Model spending | None. A script, not a model, drives the adapter. | 0 |

## Stop conditions

- A budget reaches 90% of its limit.
- A required service fails three times for one request.
- A step needs a change in a component repository.
- The task lease ends before the report.

## Approval

| Field | Value |
|---|---|
| Approved by | Richard, through the milestone request that authorizes one bounded task lifecycle through the adapter on development data |
| Approval time (UTC) | The `approved_at` time of the campaign record |
| Campaign file checksum at approval | The `campaign_file_sha256` of the campaign record |
