"""Tests of the importer against a stub API that keeps records in memory and refuses a repeated import key.

Run from the agents repository: python3 -m unittest discover -s importer/tests -t .
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from adapter.tests.stub import Stub
from importer import import_records

OBS_SHA = 'a' * 64


class FakeApi:
    """Records by import key. A second POST with a known key gives 409 with existing_id."""

    def __init__(self, stub: Stub):
        self.records = {}
        self.observation = str(uuid.uuid4())
        stub.json('GET', '/api/observations', 200, {'total': 2, 'items': [
            {'id': self.observation, 'target_id': 'TIC:1', 'sha256': OBS_SHA},
            {'id': str(uuid.uuid4()), 'target_id': 'TIC:1', 'sha256': 'b' * 64}]})
        for path in ('/api/candidates', '/api/notes', '/api/decisions'):
            stub.routes[('POST', path)] = self.post

    def post(self, request):
        key = request['body']['import_key']
        if key in self.records:
            return 409, {}, json.dumps({'detail': {'msg': 'import_key exists', 'existing_id': self.records[key]['id']}}).encode()
        record = {'id': str(uuid.uuid4()), 'path': request['path'], 'body': request['body']}
        self.records[key] = record
        return 201, {}, json.dumps({'id': record['id']}).encode()


class ImporterTest(unittest.TestCase):
    def setUp(self):
        self.stub = Stub().__enter__()
        self.addCleanup(self.stub.__exit__)
        self.fake = FakeApi(self.stub)
        self.api = import_records.Api(self.stub.url + '/api', 'dlt_test')
        self.directory = Path(tempfile.mkdtemp())
        evidence = self.directory / 'files' / 'result.json'
        evidence.parent.mkdir()
        evidence.write_bytes(b'{"period": 1.0}\n')
        self.evidence_sha = hashlib.sha256(evidence.read_bytes()).hexdigest()
        self.manifest = {
            'format': 'research-import/1', 'root': 'files',
            'items': [{
                'import_key': 'test:item-1',
                'observations': [{'target_id': 'TIC:1', 'sha256': OBS_SHA}],
                'external_files': [{'path': 'result.json', 'sha256': self.evidence_sha, 'bytes': evidence.stat().st_size,
                                    'uri': 'test:files/result.json', 'description': 'A result file.'}],
                'candidate': {'contract': 'candidate/1', 'kind': 'transit_signal', 'tier': 'lab', 'summary': 'A dip.'},
                'notes': [{'import_key': 'test:item-1/note', 'body': 'Quoted outcome.'}],
                'decisions': [{'import_key': 'test:item-1/decision', 'document': {'contract': 'decision/1', 'judge': 'model'}}],
            }]}

    def write_manifest(self, manifest=None) -> Path:
        path = self.directory / 'manifest.json'
        path.write_text(json.dumps(manifest or self.manifest))
        return path

    def posts(self):
        return [r for r in self.stub.requests if r['method'] == 'POST']

    def test_dry_run_writes_nothing(self):
        report = import_records.run(self.api, self.write_manifest(), dry_run=True)
        self.assertEqual(report['counts'], {'created': 0, 'existing': 0, 'planned': 3})
        self.assertEqual(self.posts(), [])

    def test_import_writes_stated_records(self):
        report = import_records.run(self.api, self.write_manifest(), dry_run=False)
        self.assertEqual(report['counts'], {'created': 3, 'existing': 0, 'planned': 0})
        candidate = self.fake.records['test:item-1']['body']
        self.assertEqual(candidate['tier'], 'lab')
        self.assertEqual(candidate['observation_ids'], [self.fake.observation])
        self.assertEqual(candidate['evidence'], [{'kind': 'external', 'uri': 'test:files/result.json',
                                                  'sha256': self.evidence_sha, 'bytes': 16, 'description': 'A result file.'}])
        candidate_id = self.fake.records['test:item-1']['id']
        note = self.fake.records['test:item-1/note']['body']
        self.assertEqual(note['subjects'], [{'kind': 'candidate', 'id': candidate_id}])
        decision = self.fake.records['test:item-1/decision']['body']
        self.assertEqual(decision['candidate_id'], candidate_id)
        self.assertEqual(sorted(r['path'] for r in self.posts()), ['/api/candidates', '/api/decisions', '/api/notes'])

    def test_repeated_import_writes_nothing_new(self):
        first = import_records.run(self.api, self.write_manifest(), dry_run=False)
        second = import_records.run(self.api, self.write_manifest(), dry_run=False)
        self.assertEqual(second['counts'], {'created': 0, 'existing': 3, 'planned': 0})
        self.assertEqual(len(self.fake.records), 3)
        self.assertEqual(second['items'][0]['candidate']['id'], first['items'][0]['candidate']['id'])

    def test_file_mismatch_stops_before_requests(self):
        self.manifest['items'][0]['external_files'][0]['bytes'] = 17
        with self.assertRaisesRegex(import_records.ImportStop, '16 bytes'):
            import_records.run(self.api, self.write_manifest(), dry_run=False)
        self.assertEqual(self.stub.requests, [])

    def test_observation_checksum_must_match(self):
        self.manifest['items'][0]['observations'][0]['sha256'] = 'c' * 64
        with self.assertRaisesRegex(import_records.ImportStop, '0 observations'):
            import_records.run(self.api, self.write_manifest(), dry_run=False)
        self.assertEqual(self.posts(), [])

    def test_manifest_rules(self):
        for change, message in [
            (lambda m: m['items'][0]['candidate'].update(tier='platform'), 'tier "lab"'),
            (lambda m: m['items'][0]['candidate'].update(evidence=[]), 'sets evidence'),
            (lambda m: m['items'][0]['notes'][0].update(import_key='test:item-1'), 'unique'),
            (lambda m: m.update(format='other/1'), 'format'),
        ]:
            manifest = json.loads(json.dumps(self.manifest))
            change(manifest)
            with self.assertRaisesRegex(import_records.ImportStop, message):
                import_records.run(self.api, self.write_manifest(manifest), dry_run=True)
        self.assertEqual(self.stub.requests, [])

    def standalone_note(self):
        return {'import_key': 'test:external-summary', 'body': 'External lab evidence. No planet validation.',
                'external_files': self.manifest['items'][0]['external_files']}

    def test_external_summary_needs_no_indexed_observation(self):
        manifest = {'format': 'research-import/1', 'root': 'files', 'notes': [self.standalone_note()]}
        path = self.write_manifest(manifest)
        dry = import_records.run(self.api, path, dry_run=True)
        self.assertEqual(dry['counts']['planned'], 1)
        self.assertEqual(self.stub.requests, [])
        first = import_records.run(self.api, path, dry_run=False)
        second = import_records.run(self.api, path, dry_run=False)
        self.assertEqual(first['counts']['created'], 1)
        self.assertEqual(second['counts']['existing'], 1)
        self.assertEqual(first['notes'][0]['id'], second['notes'][0]['id'])
        self.assertTrue(all(r['path'] == '/api/notes' for r in self.stub.requests))
        note = self.fake.records['test:external-summary']['body']
        self.assertEqual(note['subjects'][0]['kind'], 'external')
        self.assertEqual(note['subjects'][0]['sha256'], self.evidence_sha)

    def test_external_summary_mismatch_blocks_all_writes(self):
        self.manifest['notes'] = [self.standalone_note()]
        self.manifest['notes'][0]['external_files'] = [
            {**self.manifest['items'][0]['external_files'][0], 'sha256': '0' * 64}]
        with self.assertRaises(import_records.ImportStop):
            import_records.run(self.api, self.write_manifest(), dry_run=False)
        self.assertEqual(self.stub.requests, [])

    def test_external_summary_keys_share_the_candidate_namespace(self):
        self.manifest['notes'] = [{**self.standalone_note(), 'import_key': 'test:item-1'}]
        with self.assertRaisesRegex(import_records.ImportStop, 'unique'):
            import_records.run(self.api, self.write_manifest(), dry_run=False)
        self.assertEqual(self.stub.requests, [])

    def test_external_summary_requires_checked_subjects(self):
        for extra in [{'external_files': []}, {'subjects': []}, {'body': ''}]:
            manifest = {'format': 'research-import/1', 'root': 'files',
                        'notes': [{**self.standalone_note(), **extra}]}
            with self.assertRaises(import_records.ImportStop):
                import_records.run(self.api, self.write_manifest(manifest), dry_run=False)
        self.assertEqual(self.stub.requests, [])


if __name__ == '__main__':
    unittest.main()
