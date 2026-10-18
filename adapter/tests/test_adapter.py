"""Tests of the adapter: tool generation, parameter placement, status pass-through, downloads, and the token.

Run from the agents repository: python3 -m unittest discover -s adapter/tests -t .
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from adapter import generate, server
from adapter.tests.stub import Stub

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / 'openapi.fixture.json'
ROOT = HERE.parents[1]
TOKEN = 'dlt_test-token-that-must-not-appear'


def operations(document):
    return [(p, m) for p, item in document['paths'].items() for m in item if m in ('get', 'post', 'put', 'patch', 'delete')]


class GenerateTest(unittest.TestCase):
    def setUp(self):
        self.document = generate.load(str(FIXTURE))
        self.tools = {t['name']: t for t in generate.tools(self.document)}

    def test_one_tool_for_each_operation(self):
        self.assertEqual(len(self.tools), len(operations(self.document)))
        for name in self.tools:
            self.assertRegex(name, generate.NAME_PATTERN)

    def test_names_are_stable(self):
        again = [t['name'] for t in generate.tools(generate.load(str(FIXTURE)))]
        self.assertEqual(again, list(self.tools))
        self.assertIn('get_run', self.tools)
        self.assertIn('claim_task', self.tools)

    def test_parameters_and_body(self):
        tool = self.tools['get_fold']
        self.assertEqual(tool['http']['path_params'], ['run_id', 'observation_id'])
        self.assertIn('period', tool['inputSchema']['properties'])
        self.assertEqual(sorted(tool['inputSchema']['required']), ['observation_id', 'run_id'])
        candidate = self.tools['create_candidate']
        self.assertTrue(candidate['http']['body'])
        self.assertEqual(candidate['http']['query_params'], ['campaign_id'])
        self.assertIn('body', candidate['inputSchema']['required'])

    def test_references_are_resolved(self):
        text = json.dumps([t['inputSchema'] for t in self.tools.values()])
        self.assertNotIn('$ref', text)
        run = self.tools['create_run']['inputSchema']['properties']['body']
        self.assertIn('observation_ids', run['properties'])

    def test_no_header_parameters(self):
        for tool in self.tools.values():
            self.assertNotIn('authorization', {k.lower() for k in tool['inputSchema']['properties']})


class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.stub = Stub().__enter__()
        self.addCleanup(self.stub.__exit__)
        self.downloads = tempfile.mkdtemp()
        settings = server.Settings(api_url=self.stub.url + '/api', token=TOKEN, openapi=str(FIXTURE),
                                   downloads=Path(self.downloads), inline_bytes=1_000_000, timeout=10)
        self.adapter = server.Adapter(settings, generate.load(str(FIXTURE)))

    def result(self, name, arguments):
        answer = self.adapter.call(name, arguments)
        return answer, json.loads(answer['content'][0]['text'])

    def test_path_query_and_body_placement(self):
        run, obs = '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222'
        self.stub.json('GET', f'/api/runs/{run}/observations/{obs}/fold', 200, {'ok': True})
        answer, text = self.result('get_fold', {'run_id': run, 'observation_id': obs, 'period': 0.94, 'points': True})
        self.assertFalse(answer['isError'])
        self.assertEqual(text, {'status': 200, 'body': {'ok': True}})
        request = self.stub.requests[-1]
        self.assertEqual(request['query'], {'period': ['0.94'], 'points': ['true']})
        self.assertEqual(request['headers']['Authorization'], f'Bearer {TOKEN}')
        self.stub.json('POST', '/api/candidates', 201, {'id': 'c1'})
        document = {'contract': 'candidate/1', 'kind': 'transit_signal'}
        answer, text = self.result('create_candidate', {'body': document, 'campaign_id': run})
        request = self.stub.requests[-1]
        self.assertEqual(request['body'], document)
        self.assertEqual(request['query'], {'campaign_id': [run]})
        self.assertEqual(text['status'], 201)

    def test_error_status_passes_through(self):
        self.stub.json('POST', '/api/runs', 422, {'detail': [{'loc': ['observation_ids', 0], 'msg': 'observation not found'}]})
        answer, text = self.result('create_run', {'body': {'method': {'id': 'tess-bls', 'version': 1}, 'observation_ids': []}})
        self.assertTrue(answer['isError'])
        self.assertEqual(text['status'], 422)
        self.assertEqual(text['body']['detail'][0]['msg'], 'observation not found')

    def test_argument_errors(self):
        answer = self.adapter.call('get_run', {})
        self.assertTrue(answer['isError'])
        answer = self.adapter.call('get_run', {'run_id': 'x', 'extra': 1})
        self.assertTrue(answer['isError'])
        self.assertEqual(self.stub.requests, [])

    def test_binary_download(self):
        payload = b'PK\x03\x04' + os.urandom(2048)
        artifact = '33333333-3333-3333-3333-333333333333'
        self.stub.routes[('GET', f'/api/artifacts/{artifact}/content')] = lambda r: (
            200, {'Content-Type': 'application/zip', 'Content-Disposition': 'attachment; filename="export.zip"'}, payload)
        answer, text = self.result('get_artifact_content', {'artifact_id': artifact})
        download = text['download']
        self.assertEqual(download['sha256'], hashlib.sha256(payload).hexdigest())
        self.assertEqual(download['bytes'], len(payload))
        self.assertEqual(Path(download['path']).read_bytes(), payload)
        self.assertTrue(download['path'].endswith('export.zip'))

    def test_gzip_artifact_keeps_stored_bytes(self):
        payload = b'\x1f\x8b' + os.urandom(100)
        artifact = '44444444-4444-4444-4444-444444444444'
        self.stub.routes[('GET', f'/api/artifacts/{artifact}/content')] = lambda r: (
            200, {'Content-Type': 'application/vnd.delta.columns+json', 'Content-Encoding': 'gzip'}, payload)
        _, text = self.result('get_artifact_content', {'artifact_id': artifact})
        self.assertEqual(text['download']['sha256'], hashlib.sha256(payload).hexdigest())
        self.assertEqual(text['download']['content_encoding'], 'gzip')

    def test_token_is_scrubbed(self):
        self.stub.json('GET', '/api/me', 200, {'echo': TOKEN})
        answer, text = self.result('me', {})
        self.assertNotIn(TOKEN, answer['content'][0]['text'])


class StdioTest(unittest.TestCase):
    def test_json_rpc_session_without_token_in_output(self):
        with Stub() as stub, tempfile.TemporaryDirectory() as directory:
            stub.json('GET', '/api/health', 200, {'status': 'ok'})
            stub.json('GET', '/api/me', 401, {'detail': 'a valid bearer token is required'})
            token_file = Path(directory, 'token')
            token_file.write_text(TOKEN + '\n')
            env = {**os.environ, 'DELTA_API_URL': stub.url + '/api', 'DELTA_TOKEN_FILE': str(token_file),
                   'DELTA_OPENAPI': str(FIXTURE), 'DELTA_ADAPTER_DOWNLOADS': directory}
            messages = [
                {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}},
                {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
                {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'health', 'arguments': {}}},
                {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'me', 'arguments': {}}},
                {'jsonrpc': '2.0', 'id': 5, 'method': 'ping'},
                {'jsonrpc': '2.0', 'id': 6, 'method': 'resources/list'},
            ]
            process = subprocess.run([sys.executable, '-m', 'adapter.server'], cwd=ROOT, env=env, capture_output=True,
                                     text=True, timeout=60, input=''.join(json.dumps(m) + '\n' for m in messages))
            self.assertNotIn(TOKEN, process.stdout + process.stderr)
            answers = {a['id']: a for a in map(json.loads, process.stdout.splitlines())}
            self.assertEqual(sorted(answers), [1, 2, 3, 4, 5, 6])
            self.assertEqual(answers[1]['result']['protocolVersion'], '2025-06-18')
            self.assertGreater(len(answers[2]['result']['tools']), 40)
            self.assertFalse(answers[3]['result']['isError'])
            self.assertTrue(answers[4]['result']['isError'])
            self.assertEqual(json.loads(answers[4]['result']['content'][0]['text'])['status'], 401)
            self.assertEqual(answers[6]['error']['code'], -32601)
            self.assertTrue(all(r['headers'].get('Authorization') == f'Bearer {TOKEN}' for r in stub.requests))


if __name__ == '__main__':
    unittest.main()
