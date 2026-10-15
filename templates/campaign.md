# Campaign: <campaign-id>

Complete every field before any observation read.
Richard approves the campaign before any write operation.
Do not change the selection rule, criteria, or budgets after data access. Record a change as a new campaign.

## Objective

| Field | Value |
|---|---|
| Question | |
| Programme | TESS transits or asteroids |
| Tier | Platform or lab |
| Strongest permitted conclusion | |
| Owner | Agent ID or person |

## Selection

| Field | Value |
|---|---|
| Dataset IDs | |
| Selection rule | Metadata conditions only. No outcome or label conditions. |
| Sample size | |
| Cohort register check | Reservations checked and the result |
| Blinding | `open`, `labels`, or `labels_identity` (default), and the reveal condition |

## Method

| Field | Value |
|---|---|
| Methods and versions | |
| Parameters | Defaults, or each changed value with its reason |
| Controls | For example, inverted or scrambled light curves |
| Injections | Model, grid, and number of trials |
| Identity comparison | Catalogs, matching rules, and the time of the comparison relative to decisions |

## Measures and criteria

| Field | Value |
|---|---|
| Progress measures | Each measure with its denominator |
| Comparison | Baseline or control |
| Positive, negative, and inconclusive outcomes | The numeric criterion for each |
| Resulting action for each outcome | |

## Budgets

| Resource | API budget key | Limit |
|---|---|---:|
| Observations read | `observations_read` | |
| Jobs submitted | `jobs` | |
| Worker time (s) | `compute_seconds` | |
| Artifact storage (bytes) | `storage_bytes` | |
| Model spending | None. The agent records it in the report. | |

## Stop conditions

- A budget reaches 90% of its limit.
- A required service fails three times for one request.
- A step needs a change in a component repository.
- <campaign-specific condition>

## Approval

| Field | Value |
|---|---|
| Approved by | |
| Approval time (UTC) | |
| Campaign file checksum at approval | |
