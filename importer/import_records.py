"""Import research records from an explicit import manifest (format research-import/1) through the API.

The importer writes only what the manifest states. It uses the API only.
1. It checks the size and SHA-256 of each external file of the manifest. A mismatch stops the import.
2. It finds each observation through GET /observations?target_id=, with the SHA-256 of the manifest.
3. It writes each candidate, note, and decision with its import_key. A 409 response with existing_id means
   that the record exists, so a repeated import writes nothing new.
Steps 1 and 2 finish for every item before the first write.

The importer writes candidates of tier "lab" with external references only. It writes no measurement,
no assessment, and no run. External files stay where they are. They are proposals, not platform evidence.

Usage: python importer/import_records.py --manifest <file> [--dry-run]
Settings: DELTA_API_URL (default http://localhost:30870/api) and DELTA_TOKEN_FILE, or --api and --token-file.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

FORMAT = 'research-import/1'
KEY = re.compile(r'^[a-z0-9][a-z0-9._:/-]{0,199}$')


class ImportStop(Exception):
    """A defect in the manifest, a file, or an API response. The import stops."""


class Api:
    def __init__(self, url: str, token: str | None, timeout: float = 60):
        self.url, self.token, self.timeout = url.rstrip('/'), token, timeout

    def send(self, method: str, path: str, query: dict | None = None, body: dict | None = None) -> tuple[int, object]:
        url = self.url + path + ('?' + urllib.parse.urlencode(query) if query else '')
        headers = {'Accept': 'application/json'}
        data = None
        if body is not None:
            data, headers['Content-Type'] = json.dumps(body).encode(), 'application/json'
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, json.loads(response.read() or b'null')
        except urllib.error.HTTPError as error:
            with error:
                payload = error.read()
            try:
                return error.code, json.loads(payload)
            except ValueError:
                return error.code, payload.decode(errors='replace')


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def existing_id(document) -> str | None:
    """The ID of the existing record in a 409 response, at the top level or in detail."""
    if not isinstance(document, dict):
        return None
    if document.get('existing_id'):
        return document['existing_id']
    detail = document.get('detail')
    return detail.get('existing_id') if isinstance(detail, dict) else None


def check_manifest(manifest: dict):
    if manifest.get('format') != FORMAT:
        raise ImportStop(f'the manifest format is {manifest.get("format")!r}, not {FORMAT}')
    keys = []
    for i, item in enumerate(manifest.get('items') or []):
        candidate = item.get('candidate') or {}
        if candidate.get('tier') != 'lab':
            raise ImportStop(f'items[{i}]: an imported candidate has tier "lab"')
        for field in ('observation_ids', 'evidence', 'import_key'):
            if field in candidate:
                raise ImportStop(f'items[{i}].candidate: the importer sets {field}')
        keys.append(item.get('import_key'))
        keys += [n.get('import_key') for n in item.get('notes', [])]
        keys += [d.get('import_key') for d in item.get('decisions', [])]
        for d in item.get('decisions', []):
            if 'candidate_id' in d.get('document', {}):
                raise ImportStop(f'items[{i}].decisions: the importer sets candidate_id')
    bad = [k for k in keys if not isinstance(k, str) or not KEY.match(k)]
    if bad or len(keys) != len(set(keys)):
        raise ImportStop(f'import keys must be unique and match {KEY.pattern}: {bad or "duplicates"}')
    if not keys:
        raise ImportStop('the manifest has no items')


def check_files(manifest: dict, base: Path) -> dict:
    """{item key: [external references]} after the size and SHA-256 check of every file."""
    refs = {}
    for item in manifest['items']:
        out = []
        for entry in item.get('external_files', []):
            path = (base / entry['path']).resolve()
            if not path.is_file():
                raise ImportStop(f'{entry["path"]}: the file does not exist')
            size, digest = path.stat().st_size, sha256(path)
            if size != entry['bytes'] or digest != entry['sha256']:
                raise ImportStop(f'{entry["path"]}: the file has {size} bytes and SHA-256 {digest}, '
                                   f'the manifest states {entry["bytes"]} bytes and {entry["sha256"]}')
            ref = {'kind': 'external', 'uri': entry.get('uri') or f'workspace:{entry["path"]}',
                   'sha256': digest, 'bytes': size}
            if entry.get('description'):
                ref['description'] = entry['description']
            out.append(ref)
        if not out:
            raise ImportStop(f'{item["import_key"]}: an imported candidate needs at least one external file')
        refs[item['import_key']] = out
    return refs


def find_observations(api: Api, manifest: dict) -> dict:
    """{item key: [observation IDs]}. Each observation must match its target ID and SHA-256."""
    found = {}
    for item in manifest['items']:
        ids = []
        for entry in item.get('observations', []):
            status, body = api.send('GET', '/observations', {'target_id': entry['target_id'], 'limit': 1000})
            if status != 200:
                raise ImportStop(f'GET /observations?target_id={entry["target_id"]} gave {status}: {body}')
            matches = [o['id'] for o in body['items'] if o.get('sha256') == entry['sha256']]
            if len(matches) != 1:
                raise ImportStop(f'{entry["target_id"]}: {len(matches)} observations have SHA-256 {entry["sha256"]}')
            ids.append(matches[0])
        if not ids:
            raise ImportStop(f'{item["import_key"]}: an imported candidate needs at least one observation')
        found[item['import_key']] = ids
    return found


def write(api: Api, path: str, query: dict | None, document: dict, dry_run: bool) -> dict:
    """Write one record. Return its ID and whether the import created it."""
    if dry_run:
        return {'id': None, 'outcome': 'planned', 'import_key': document['import_key']}
    status, body = api.send('POST', path, query, document)
    if status == 201:
        return {'id': body['id'], 'outcome': 'created', 'import_key': document['import_key']}
    if status == 409 and existing_id(body):
        return {'id': existing_id(body), 'outcome': 'existing', 'import_key': document['import_key']}
    raise ImportStop(f'POST {path} for {document["import_key"]} gave {status}: {body}')


def run(api: Api, manifest_path: Path, dry_run: bool) -> dict:
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    check_manifest(manifest)
    base = (manifest_path.parent / manifest.get('root', '.')).resolve()
    refs = check_files(manifest, base)
    observations = find_observations(api, manifest)
    query = {'campaign_id': manifest['campaign_id']} if manifest.get('campaign_id') else None
    items = []
    for item in manifest['items']:
        key = item['import_key']
        candidate = {**item['candidate'], 'import_key': key, 'observation_ids': observations[key], 'evidence': refs[key]}
        written = write(api, '/candidates', query, candidate, dry_run)
        subject = [{'kind': 'candidate', 'id': written['id'] or '00000000-0000-0000-0000-000000000000'}]
        notes = [write(api, '/notes', None, {'contract': 'note/1', 'import_key': n['import_key'], 'body': n['body'],
                                             'subjects': subject}, dry_run) for n in item.get('notes', [])]
        decisions = [write(api, '/decisions', None, {'evidence': refs[key], **d['document'], 'import_key': d['import_key'],
                                                     'candidate_id': subject[0]['id']}, dry_run)
                     for d in item.get('decisions', [])]
        items.append({'import_key': key, 'observation_ids': observations[key], 'candidate': written,
                      'notes': notes, 'decisions': decisions})
    outcomes = [r['outcome'] for i in items for r in [i['candidate'], *i['notes'], *i['decisions']]]
    return {'manifest': str(manifest_path), 'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'dry_run': dry_run,
            'counts': {o: outcomes.count(o) for o in ('created', 'existing', 'planned')}, 'items': items}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--dry-run', action='store_true', help='check files and observations, and write nothing')
    parser.add_argument('--api', default=os.environ.get('DELTA_API_URL', 'http://localhost:30870/api'))
    parser.add_argument('--token-file', default=os.environ.get('DELTA_TOKEN_FILE'))
    args = parser.parse_args(argv)
    token = Path(args.token_file).expanduser().read_text().strip() if args.token_file else None
    try:
        report = run(Api(args.api, token), args.manifest, args.dry_run)
    except ImportStop as error:
        message = str(error).replace(token, '<token>') if token else str(error)
        json.dump({'error': message, 'written': 'Writes stop at the first error. Earlier writes stay.'}, sys.stdout, indent=2)
        sys.stdout.write('\n')
        return 1
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
