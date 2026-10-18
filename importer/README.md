# Research importer

`import_records.py` writes research records from an explicit import manifest through the API.
It uses the API only. It contains no scientific or policy logic. The API applies permissions and campaign rules.
Use a person or service client with `read` and `record.write`. The record contracts state that agents do not write import keys.

```bash
DELTA_TOKEN_FILE=<token file> python3 importer/import_records.py --manifest imports/<name>.json --dry-run
DELTA_TOKEN_FILE=<token file> python3 importer/import_records.py --manifest imports/<name>.json
```

`--dry-run` checks the files and finds the observations. It writes nothing.
The report is JSON: the manifest SHA-256, and for each item the observation IDs and each record with `created`, `existing`, or `planned`.

## Procedure

1. The importer checks the manifest: format, unique import keys, and candidates of tier `lab` without `observation_ids`, `evidence`, or `import_key`.
2. It checks the size and SHA-256 of each external file. A mismatch stops the import before any request.
3. It finds each observation with `GET /observations?target_id=`. Exactly one observation must have the SHA-256 of the manifest.
4. It writes, for each item, the candidate, then its notes, then its decisions. Each record has its `import_key`.
5. A `409` response with `existing_id` means that the record exists. The importer uses that ID and writes nothing.

Steps 1 to 3 finish for every item before the first write. A failed write stops the import. Earlier writes stay, and a repeated import continues from them.

## What the importer writes

| Record | Content |
|---|---|
| Candidate | The candidate document of the manifest, with tier `lab`. The importer adds `observation_ids`, `import_key`, and `evidence`: one external reference for each external file, with URI, SHA-256, size, and description. |
| Note | The note body of the manifest, with the candidate as its subject. |
| Decision | Only a decision that the manifest states, with the candidate ID. Without `evidence` in the document, the evidence is the external references of the item. |

The importer writes no measurement, no assessment, and no run.
An external file stays where it is. It is a proposal, not platform evidence.
The author of a manifest states only values that the source record states. A judgment that the source does not state does not go into a manifest.

## Manifest format `research-import/1`

```json
{
  "format": "research-import/1",
  "description": "What the manifest imports and why.",
  "root": "../..",
  "campaign_id": null,
  "items": [
    {
      "import_key": "experiment:<record>/<item>",
      "observations": [{"target_id": "TIC:<n>", "sha256": "<hex>", "file_name": "<optional>"}],
      "external_files": [
        {"path": "<path below root>", "sha256": "<hex>", "bytes": 0, "uri": "workspace:<path>", "description": "<text>"}
      ],
      "candidate": {"contract": "candidate/1", "kind": "transit_signal", "tier": "lab", "label": "<optional>", "summary": "<text>"},
      "notes": [{"import_key": "<key>", "body": "<text>"}],
      "decisions": [{"import_key": "<key>", "document": {"contract": "decision/1", "...": "..."}}]
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `root` | Directory of the external file paths, relative to the manifest file. |
| `campaign_id` | Optional. The campaign of the candidates. Without it, the records have no campaign, and agents do not see them. |
| `import_key` | Pattern `^[a-z0-9][a-z0-9._:/-]{0,199}$`. Unique in the manifest and in the database. |
| `uri` | Optional. The default is `workspace:<path>`. |
| `notes`, `decisions` | Optional. |

[database/contracts/](https://github.com/delta-observatory/database/blob/main/contracts/README.md) defines the candidate, note, and decision documents and the `import_key` field.

## Manifests

| Manifest | Content |
|---|---|
| [imports/t01-known-planet-recovery.json](../imports/t01-known-planet-recovery.json) | The closed T01 record for its two registered development hosts, TIC 100100827 and TIC 25155310: one lab candidate for each host with the T01 result files, and one note that quotes the T01 outcome and limits. No assessment and no decision. |
| [imports/research-search-a61de640-final001.json](../imports/research-search-a61de640-final001.json) | The seven retained candidates of delta-research publication FINAL001 on the 18 registered light curves of the selection manifest `research-search-a61de640-final001`. One lab candidate for each star with the dossier, report, target table, and publication manifest as external references. One note that quotes the report limits. One advisory decision of judge `model` that keeps the source assessment `retained` in `response` and maps it to the judged evidence status `supported`. No assessment. |

## Tests

```bash
python3 -m unittest discover -s importer/tests -t .
```

The tests use a stub API. They check the dry run, the written documents, a repeated import that writes nothing new, a file mismatch, an observation mismatch, and the manifest rules.
