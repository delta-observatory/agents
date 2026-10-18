"""Functional check: one agent task lifecycle through the generated adapter.

The check starts the adapter (python -m adapter.server) as an MCP server over stdio and acts as its client.
It claims one task of kind adapter_check, reads the stored result of the task's job, writes a platform candidate,
a decision, and an evidence assessment, sends three requests that the API must refuse, and reports the task.
The records state that they carry no scientific judgment. The check makes no scientific measurement.

Run from agents/ with the token file of an agent client of an approved campaign:
  DELTA_TOKEN_FILE=<agent token file> python3 -m checks.adapter_lifecycle

The output is a JSON report. It never contains the token.
"""
import json
import os
import subprocess
import sys

NO_JUDGMENT = 'Functional adapter check. This record carries no scientific judgment.'


class Client:
    """A minimal MCP client over the stdio of the adapter process."""

    def __init__(self):
        self.process = subprocess.Popen([sys.executable, '-m', 'adapter.server'], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, text=True, env=os.environ.copy())
        self.next_id = 0
        self.tools = {}

    def rpc(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        self.process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': self.next_id, 'method': method,
                                             'params': params or {}}) + '\n')
        self.process.stdin.flush()
        reply = json.loads(self.process.stdout.readline())
        if 'error' in reply:
            raise RuntimeError(f'{method}: {reply["error"]}')
        return reply['result']

    def start(self):
        self.rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                'clientInfo': {'name': 'adapter-lifecycle-check', 'version': '1'}})
        self.process.stdin.write(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) + '\n')
        self.process.stdin.flush()
        for tool in self.rpc('tools/list')['tools']:
            # The description ends with the HTTP method and path of the operation.
            self.tools[tool['name']] = tool
        return len(self.tools)

    def tool_for(self, method: str, path: str) -> str:
        marker = f'HTTP: {method} /api{path}'
        names = [n for n, t in self.tools.items() if t['description'].endswith(marker)]
        if len(names) != 1:
            raise RuntimeError(f'no single tool for {marker}: {names}')
        return names[0]

    def call(self, method: str, path: str, **arguments) -> tuple[int, object]:
        result = self.rpc('tools/call', {'name': self.tool_for(method, path), 'arguments': arguments})
        payload = json.loads(result['content'][0]['text'])
        return payload['status'], payload.get('body')

    def stop(self):
        self.process.stdin.close()
        self.process.wait(timeout=10)


def expect(steps: list, name: str, status: int, wanted: int, body=None):
    steps.append({'step': name, 'status': status, 'expected': wanted, 'ok': status == wanted,
                  **({'detail': body.get('detail')} if isinstance(body, dict) and status >= 400 else {})})
    if status != wanted:
        raise SystemExit(json.dumps({'failed_step': name, 'steps': steps}, indent=1, default=str))


def main() -> int:
    client = Client()
    steps = []
    tools = client.start()
    status, me = client.call('GET', '/me')
    expect(steps, 'me', status, 200)
    status, campaign = client.call('GET', '/campaigns/{campaign_id}', campaign_id=me['campaign_id'])
    expect(steps, 'campaign', status, 200)

    status, claim = client.call('POST', '/tasks/claim', body={'kinds': ['adapter_check']})
    expect(steps, 'claim task', status, 200)
    task = claim['task']
    if task is None:
        raise SystemExit(json.dumps({'failed_step': 'claim task', 'reason': 'no task of kind adapter_check'}))
    lease = task['lease_id']
    job_ref = next(r for r in task['inputs'] if r['kind'] == 'job')

    status, job = client.call('GET', '/jobs/{job_id}', job_id=job_ref['id'])
    expect(steps, 'read job', status, 200)
    status, results = client.call('GET', '/runs/{run_id}/results', run_id=job['run_id'], observation_id=job['observation_id'])
    expect(steps, 'read stored result', status, 200)
    search = {m['name']: m for m in results['jobs'][0]['measurements']['search']}
    evidence = [{'kind': 'measurement', 'id': search[n]['id']} for n in ('period', 'transit_time', 'depth')] + \
               [{'kind': 'job', 'id': job['id']}]

    status, candidate = client.call('POST', '/candidates', body={
        'contract': 'candidate/1', 'kind': 'transit_signal', 'tier': 'platform', 'label': f'ADAPTER-CHECK-{task["id"][:8]}',
        'summary': NO_JUDGMENT + ' The candidate refers to the stored period, transit time, and depth of one tess-bls job.',
        'observation_ids': [job['observation_id']], 'evidence': evidence})
    expect(steps, 'write candidate', status, 201)
    status, decision = client.call('POST', '/decisions', body={
        'contract': 'decision/1', 'candidate_id': candidate['id'], 'question': {'id': 'adapter-check', 'version': 1},
        'mode': 'advisory', 'judge': 'model',
        'model': {'kind': 'unavailable', 'reason': 'A deterministic check script wrote this decision. No model judged the evidence.'},
        'packet': {'kind': 'unavailable', 'reason': 'The check assembled no evidence packet.'},
        'policy': {'kind': 'unavailable', 'reason': 'No decision policy exists.'},
        'judged_evidence_status': 'ambiguous', 'action': 'request_human_review', 'reason': NO_JUDGMENT,
        'evidence': evidence})
    expect(steps, 'write decision', status, 201)
    status, assessment = client.call('POST', '/assessments', body={
        'contract': 'assessment/1', 'candidate_id': candidate['id'], 'axis': 'evidence', 'status': 'ambiguous',
        'basis': 'model_judgment', 'decision_id': decision['id'], 'reason': NO_JUDGMENT, 'evidence': evidence})
    expect(steps, 'write evidence assessment', status, 201)

    status, body = client.call('POST', '/assessments', body={
        'contract': 'assessment/1', 'candidate_id': candidate['id'], 'axis': 'identity', 'status': 'matched',
        'basis': 'review', 'reason': NO_JUDGMENT, 'evidence': evidence})
    expect(steps, 'refused: identity assessment by an agent', status, 403, body)
    status, body = client.call('POST', '/runs', body={'method': {'id': 'tess-bls', 'version': 1},
                                                      'observation_ids': [job['observation_id']]})
    expect(steps, 'refused: run past the jobs budget', status, 403, body)
    status, body = client.call('POST', '/notes', body={'contract': 'note/1', 'body': NO_JUDGMENT,
                                                       'import_key': 'check:adapter/refused',
                                                       'subjects': [{'kind': 'candidate', 'id': candidate['id']}]})
    expect(steps, 'refused: import key from an agent', status, 403, body)

    status, _ = client.call('POST', '/tasks/{task_id}/heartbeat', task_id=task['id'], body={'lease_id': lease})
    expect(steps, 'extend lease', status, 200)
    outputs = [{'kind': 'candidate', 'id': candidate['id']}, {'kind': 'decision', 'id': decision['id']},
               {'kind': 'assessment', 'id': assessment['id']}]
    status, ended = client.call('POST', '/tasks/{task_id}/report', task_id=task['id'], body={
        'lease_id': lease, 'report': {'contract': 'agent-task-report/1', 'outcome': 'complete',
                                      'summary': NO_JUDGMENT + ' The task wrote one candidate, one decision, and one assessment.',
                                      'outputs': outputs}})
    expect(steps, 'report task', status, 200)
    status, after = client.call('GET', '/campaigns/{campaign_id}', campaign_id=me['campaign_id'])
    expect(steps, 'campaign after', status, 200)
    client.stop()
    print(json.dumps({
        'tools': tools, 'client': me['name'], 'campaign': campaign['name'], 'withheld': results.get('withheld'),
        'task': {'id': task['id'], 'state': ended['state'], 'attempts': ended['attempts'], 'outputs': ended['outputs']},
        'records': {'candidate': candidate['id'], 'decision': decision['id'], 'assessment': assessment['id']},
        'observations_read': after['budget_state']['observations_read'], 'steps': steps}, indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
