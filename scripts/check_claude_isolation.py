"""Exercise published Claude Code with an offline provider and one scoped API tool."""
import argparse
import asyncio
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from managed.claude import ClaudeHost
from managed.claude_sandbox import command

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime',type=Path,required=True);parser.add_argument('--bwrap',type=Path,default=Path('/usr/bin/bwrap'))
args=parser.parse_args();requests=[]

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        value=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
        if '/messages' not in self.path:
            self.send_response(200);self.end_headers();self.wfile.write(b'{}');return
        requests.append(value)
        # Only the application conversation contains the generated MCP tool.
        tool=next((t for t in value.get('tools',[]) if t.get('name')=='mcp__delta__delta_fixture'),None)
        has_result=any(c.get('type')=='tool_result' for m in value.get('messages',[]) if isinstance(m.get('content'),list) for c in m['content'])
        use_tool=bool(tool) and not has_result
        block={'type':'tool_use','id':'toolu_fixture','name':'mcp__delta__delta_fixture','input':{}} if use_tool else {'type':'text','text':'The engineering connection works.'}
        message={'id':'msg_'+str(len(requests)),'type':'message','role':'assistant','model':'claude-sonnet-4-6',
                 'content':[block],'stop_reason':'tool_use' if use_tool else 'end_turn','stop_sequence':None,'usage':{'input_tokens':10,'output_tokens':6}}
        if value.get('stream'):
            start={**message,'content':[],'stop_reason':None,'usage':{'input_tokens':10,'output_tokens':0}}
            first={**block,'input':{}} if use_tool else {'type':'text','text':''}
            delta={'type':'input_json_delta','partial_json':'{}'} if use_tool else {'type':'text_delta','text':block['text']}
            events=[{'type':'message_start','message':start},{'type':'content_block_start','index':0,'content_block':first},
                    {'type':'content_block_delta','index':0,'delta':delta},{'type':'content_block_stop','index':0},
                    {'type':'message_delta','delta':{'stop_reason':message['stop_reason'],'stop_sequence':None},'usage':{'output_tokens':6}}, {'type':'message_stop'}]
            body=''.join('event: '+e['type']+'\ndata: '+json.dumps(e)+'\n\n' for e in events).encode();kind='text/event-stream'
        else:body=json.dumps(message).encode();kind='application/json'
        self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

async def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    events=[];tool_calls=[]
    with tempfile.TemporaryDirectory(prefix='delta-claude-boundary-') as directory:
        base=Path(directory);private=base/'private-token';private.write_text('synthetic-private-marker')
        native=command(args.runtime,base/'probe',args.bwrap,['--version'])
        binary=native.index('/opt/provider/claude')
        result=subprocess.run(native[:binary]+['/bin/sh','-c','test ! -e "$1" && test ! -e /run/postgresql && test ! -e "$2"','check',str(private),str(Path.home())],env={'PATH':'/usr/bin:/bin'})
        assert result.returncode==0,'The provider namespace exposed a host path.'
        def fixture_command(runtime,profile,bwrap,arguments,extra):
            return command(runtime,profile,bwrap,arguments,{**extra,'ANTHROPIC_API_KEY':'fixture-key','ANTHROPIC_BASE_URL':f'http://127.0.0.1:{server.server_port}',
                'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC':'1'})
        host=ClaudeHost(SimpleNamespace(claude_runtime_dir=args.runtime,bwrap=args.bwrap,state_dir=directory,library_dir=None),events.append)
        host.owner_token='fixture-owner'
        async def api(path,body=None,**kwargs):
            if path.endswith('/state'):host.session['document'].update(body);return host.session
            if path.endswith('/sessions'):return {'items':[host.session]}
            if path.endswith('/turn'):host.session['document'].update(state='running',turns=1);return host.session
            if path.endswith('/events'):return {}
            return {'state':'ready','head_revision_id':'r','approved_revision_id':'r','revisions':[{'id':'r','document':{'limits':{'model_tokens':1000}}}]}
        host.api=api
        class Adapter:
            tools={'delta_fixture':{'http':{'path':'/api/methods','method':'GET','path_params':[]}}}
            def list_tools(self):return [{'name':'delta_fixture','description':'Read the fixed engineering fixture.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}}]
            def call(self,name,arguments):tool_calls.append(name);return {'content':[{'type':'text','text':'fixture-result'}]}
        try:
            with patch('managed.claude.command',side_effect=fixture_command):
                await host.initialize();host.campaign='fixture';host.thread=str(uuid.uuid4());host.adapter=Adapter()
                host.session={'id':'fixture','document':{'model':'sonnet','tokens':0,'turns':0}}
                host.instructions='Use delta_fixture once. Then return its result.'
                await host.send('Read the engineering fixture.')
                await asyncio.wait_for(host.run_task,60)
                selected=[r for r in requests if r.get('tools')]
                assert selected,'The provider received no tool definitions.'
                for request in selected:
                    assert [t['name'] for t in request['tools']]==['mcp__delta__delta_fixture'],[t['name'] for t in request['tools']]
                assert tool_calls==['delta_fixture'],tool_calls
                assert any('fixture-result' in json.dumps(r['messages']) for r in selected),'The tool result did not reach the provider.'
                assert any(e.get('event')=='turn' and e.get('state')=='idle' for e in events),events
                first_tokens=host.session['document']['tokens']
                await host.rpc('thread/resume',{'threadId':host.thread,'developerInstructions':host.instructions})
                await host.send('Continue with the preserved fixture result.')
                await asyncio.wait_for(host.run_task,60)
                assert host.session['document']['tokens']>first_tokens
                assert host.session['document']['state']=='idle',events
                print(json.dumps({'status':'passed','provider_requests':len(requests),'only_api_tools':True,'host_files_inaccessible':True,'tool_calls':len(tool_calls),'resumed':True,'measured_tokens':host.session['document']['tokens']}))
        finally:
            await host.close();server.shutdown();server.server_close()

asyncio.run(main())
