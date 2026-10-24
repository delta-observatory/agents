import sys, argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
parser=argparse.ArgumentParser(description='Check the isolated agent with a local fake provider. No account or model calls occur.')
parser.add_argument('--runtime',type=Path,required=True)
parser.add_argument('--bwrap',type=Path,default=Path('/usr/bin/bwrap'))
args=parser.parse_args()
runtime,bwrap=args.runtime,args.bwrap
from managed.sandbox import command
import json,subprocess,threading,tempfile,time,queue
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
requests=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  raw=self.rfile.read(int(self.headers.get('Content-Length','0')))
  try:requests.append(json.loads(raw))
  except Exception:requests.append({'raw':raw.decode(errors='replace')[:500]})
  response={'id':'resp_delta_fixture','object':'response','status':'completed','model':'gpt-5.4','output':[{'id':'msg_delta_fixture','type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':'The engineering connection works.','annotations':[]}]}],'usage':{'input_tokens':10,'output_tokens':6,'total_tokens':16}}
  if len(requests)==1:
   response['output']=[{'id':'fc_delta','type':'function_call','call_id':'fixture-call','name':'delta_fixture','arguments':'{}','status':'completed'}]
  events=[{'type':'response.created','response':{**response,'status':'in_progress','output':[]}}, {'type':'response.output_item.added','output_index':0,'item':{**response['output'][0]}}, {'type':'response.output_item.done','output_index':0,'item':response['output'][0]},{'type':'response.completed','response':response}]
  body=''.join('data: '+json.dumps(e)+'\n\n' for e in events).encode()
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
s=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=s.serve_forever,daemon=True).start()
with tempfile.TemporaryDirectory(prefix='delta-codex-tool-check-') as d:
 profile=Path(d)/'profile'
 args=command(runtime,profile,bwrap)
 secret=Path(d)/'private-owner-token';secret.write_text('synthetic-private-marker')
 isolated=subprocess.run(args[:-4]+['/bin/sh','-c','test ! -e "$1" && test ! -e /run/postgresql && test ! -e "$2"','check',str(secret),str(Path.home())],capture_output=True)
 assert isolated.returncode==0,'The namespace exposed a host path.'
 config=profile/'config.toml'
 config.write_text('model_provider="fixture"\nmodel="gpt-5.4"\n'+config.read_text()+'enable_request_compression=false\n[model_providers.fixture]\nname="Engineering fixture"\nbase_url="http://127.0.0.1:'+str(s.server_port)+'/v1"\nwire_api="responses"\nrequires_openai_auth=false\n')
 p=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 lines=queue.Queue();threading.Thread(target=lambda:[lines.put(json.loads(line)) for line in p.stdout],daemon=True).start()
 def send(n,method,params):p.stdin.write(json.dumps({'id':n,'method':method,'params':params})+'\n');p.stdin.flush()
 def result(n):
  deadline=time.time()+25
  while time.time()<deadline:
   m=lines.get(timeout=max(.1,deadline-time.time()))
   if m.get('id')==n:
    if 'error'in m:raise RuntimeError(m['error'])
    return m['result']
 try:
  send(1,'initialize',{'clientInfo':{'name':'delta_test','version':'0.1'},'capabilities':{'experimentalApi':True}});result(1)
  send(2,'thread/start',{'model':'gpt-5.4','approvalPolicy':'never','sandbox':'read-only','environments':[],'cwd':'/workspace','dynamicTools':[{'type':'function','name':'delta_fixture','description':'An engineering API fixture.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}}]})
  thread=result(2)['thread']['id']
  send(3,'turn/start',{'threadId':thread,'input':[{'type':'text','text':'Return the fixed engineering message.'}]});result(3)
  deadline=time.time()+25
  while time.time()<deadline:
   m=lines.get(timeout=max(.1,deadline-time.time()))
   if m.get('method')=='item/tool/call':
    assert m['params']['tool']=='delta_fixture'
    p.stdin.write(json.dumps({'id':m['id'],'result':{'success':True,'contentItems':[{'type':'inputText','text':'fixture-result'}]}})+'\n');p.stdin.flush()
   if m.get('method')=='turn/completed':break
  assert len(requests)==2,'The direct API tool did not complete.'
  assert [t['name'] for t in requests[0]['tools']]==['delta_fixture'],'An unexpected tool was exposed.'
  assert any(i.get('type')=='function_call_output' and 'fixture-result' in str(i) for i in requests[1]['input'])
  print(json.dumps({'status':'passed','provider_requests':2,'only_api_tools':True,'host_files_inaccessible':True,'model':'gpt-5.4'}))
 finally:
  p.terminate()
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.kill();p.wait()
  p.stderr.read();s.shutdown()
