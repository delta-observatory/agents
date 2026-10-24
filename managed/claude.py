"""Host the unmodified Claude Code login and print interfaces.

Claude Code owns OAuth, browser callbacks, refresh, and its credential files.
Delta never reads OAuth tokens. Only generated, scoped API tools reach the model.
"""
import asyncio
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import signal
import tempfile
import uuid
from urllib.parse import urlsplit
from .host import Host
from .claude_sandbox import command


class ClaudeHost(Host):
    provider='claude'
    models=frozenset({'sonnet','opus','haiku'})
    session_contract='agent-session/2'

    def __init__(self,args,emit):
        super().__init__(args,emit)
        self.profile=None;self.temporary=None;self.login_proc=None;self.login_task=None
        self.login_ready=None;self.run_task=None;self.server=None;self.bridge_tasks=set();self.account_key=None
        self.instructions='';self.resume=False;self.cancelled_login=False

    async def spawn(self,arguments):
        args=command(self.args.claude_runtime_dir,self.profile,self.args.bwrap,arguments,{})
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}
        if self.args.library_dir:env['LD_LIBRARY_PATH']=self.args.library_dir
        if self.account_key:env['ANTHROPIC_API_KEY']=self.account_key
        return await asyncio.create_subprocess_exec(*args,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE,env=env,limit=4*1024*1024)

    async def cli(self,arguments):
        proc=await self.spawn(arguments)
        try:
            out,_=await asyncio.wait_for(proc.communicate(),30)
            return proc.returncode,out.decode(errors='replace')
        except BaseException:
            if proc.returncode is None:proc.kill()
            await proc.wait();raise

    async def status(self):
        account=None
        if self.profile:
            code,out=await self.cli(['auth','status','--json'])
            try:raw=json.loads(out)
            except ValueError:raise ValueError('Claude Code returned an invalid account status.') from None
            if code==0 and raw.get('loggedIn'):
                account={'type':raw.get('authMethod','claude.ai'),'email':raw.get('email'),
                         'planType':raw.get('subscriptionType') or raw.get('organizationName')}
        return {'provider':self.provider,'initialized':self.profile is not None,'account':account,'session':self.session,
                'campaign_id':self.campaign,'credential_store':self.credential_store,'login':self.pending_login}

    async def initialize(self,campaign=None,credential_store='ephemeral'):
        if credential_store not in ('ephemeral','provider'):
            raise ValueError('Select memory-only storage or the private provider profile.')
        if self.profile:
            if self.credential_store!=credential_store:raise ValueError('Sign out before changing credential storage.')
            return await self.status()
        if credential_store=='ephemeral':
            if not Path('/dev/shm').is_dir():raise ValueError('Memory-only provider storage is unavailable on this system.')
            self.temporary=tempfile.TemporaryDirectory(prefix='delta-provider-',dir='/dev/shm')
            self.profile=Path(self.temporary.name)
        else:self.profile=Path(self.args.state_dir)/'claude'
        self.credential_store=credential_store
        try:return await self.status()
        except BaseException:
            await self.close();raise

    async def login(self,params):
        if not self.profile:raise ValueError('Initialize the provider first.')
        if self.session:raise ValueError('Disconnect the investigation before changing the provider account.')
        if self.pending_login:raise ValueError('Complete or cancel the pending login first.')
        kind=params.get('type')
        if kind=='apiKey':
            key=params.get('apiKey','').strip()
            if not key:raise ValueError('Enter an API key.')
            self.account_key=key;self.secrets.append(key)
            return {'type':kind}
        if kind not in ('claude','console','sso'):raise ValueError('Select a supported login method.')
        arguments=['auth','login']+({'console':['--console'],'sso':['--sso']}.get(kind,['--claudeai']))
        self.pending_login={'type':kind,'loginId':str(uuid.uuid4())}
        self.cancelled_login=False;self.login_ready=asyncio.get_running_loop().create_future()
        try:
            self.login_proc=await self.spawn(arguments)
            self.login_task=asyncio.create_task(self.watch_login())
            return await asyncio.wait_for(asyncio.shield(self.login_ready),25)
        except BaseException:
            if self.login_ready and not self.login_ready.done():self.login_ready.cancel()
            await self.cancel_login();raise

    async def watch_login(self):
        proc=self.login_proc
        async def read(stream):
            buffer=''
            while chunk:=await stream.read(4096):
                buffer=(buffer+chunk.decode(errors='replace'))[-32000:]
                # The CLI prints the URL. Never forward diagnostics or credentials.
                for value in re.findall(r'https://[^\s\x1b<>]+(?=[\s\x1b])',buffer):
                    url=urlsplit(value)
                    if url.hostname in ('claude.ai','claude.com','platform.claude.com','console.anthropic.com') and ('oauth' in url.path or 'authorize' in url.path):
                        if self.pending_login:
                            self.pending_login['authUrl']=value
                            if not self.login_ready.done():self.login_ready.set_result(dict(self.pending_login))
                if len(buffer)>16000:buffer=buffer[-8000:]
        try:
            await asyncio.wait_for(asyncio.gather(read(proc.stdout),read(proc.stderr),proc.wait()),600)
            if not self.login_ready.done():self.login_ready.set_exception(ValueError('Claude Code did not return a login address. Try again.'))
            if not self.cancelled_login:
                success=proc.returncode==0 and bool((await self.status())['account'])
                self.emit({'event':'login','success':success,'error':'' if success else 'Provider login did not complete. Try again.'})
        except asyncio.TimeoutError:
            if proc.returncode is None:proc.terminate();await proc.wait()
            self.emit({'event':'login','success':False,'error':'Provider login expired. Try again.'})
        finally:
            self.pending_login=None;self.login_proc=None
            self.emit({'event':'account'})

    async def cancel_login(self):
        self.cancelled_login=True
        if self.login_proc and self.login_proc.returncode is None:
            self.login_proc.terminate()
            try:await asyncio.wait_for(self.login_proc.wait(),5)
            except asyncio.TimeoutError:self.login_proc.kill();await self.login_proc.wait()
        if self.login_task:await self.login_task
        self.pending_login=None;self.login_task=None
        if self.login_ready and not self.login_ready.done():self.login_ready.cancel()
        return {'cancelled':True}

    async def handle(self,action,params):
        if action=='configure':return await super().handle(action,params)
        if not self.owner_token:raise ValueError('The desktop host is not configured.')
        if action=='login':return await self.login(params)
        if action=='cancelLogin':return await self.cancel_login()
        if action=='submitLoginCode':
            code=params.get('code','').strip()
            if not self.pending_login or not self.login_proc:raise ValueError('Start provider login first.')
            if not 1<=len(code)<=4096 or '\n' in code or '\r' in code:raise ValueError('Paste the authorization code from the provider page.')
            self.secrets.append(code)
            self.login_proc.stdin.write((code+'\n').encode());await self.login_proc.stdin.drain()
            return {'submitted':True}
        if action=='models':return {'data':[{'id':m,'model':m,'displayName':m.title(),'isDefault':m=='sonnet'} for m in ('sonnet','opus','haiku')]}
        if action=='logout':
            await self.disconnect();await self.cancel_login()
            if self.profile:
                code,_=await self.cli(['auth','logout'])
                if code:raise ValueError('Claude Code could not remove the account. Try again.')
            self.account_key=None
            await self.close();return await self.status()
        return await super().handle(action,params)

    async def rpc(self,method,params):
        if method in ('thread/start','thread/resume'):
            if method=='thread/resume':
                ident=str(uuid.UUID(params['threadId']))
                if not any((self.profile/'projects').glob('*/'+ident+'.jsonl')):
                    raise ValueError('The saved provider conversation is unavailable.')
            self.instructions=params['developerInstructions'];self.resume=method=='thread/resume'
            return {'thread':{'id':params.get('threadId') or str(uuid.uuid4())}}
        if method=='turn/start':
            if self.proc and self.proc.returncode is None:raise ValueError('Wait for the current agent turn.')
            self.bridge_secret=secrets.token_urlsafe(32);self.bridge_id=str(uuid.uuid4())
            self.server=await asyncio.start_server(self.mcp,'127.0.0.1',0,limit=65536)
            port=self.server.sockets[0].getsockname()[1]
            mcp={'mcpServers':{'delta':{'type':'http','alwaysLoad':True,'url':f'http://127.0.0.1:{port}/mcp',
                                     'headers':{'Authorization':'Bearer '+self.bridge_secret}}}}
            arguments=['--print','--verbose','--output-format','stream-json','--include-partial-messages',
                       '--restricted','--tools','','--disable-slash-commands','--no-chrome','--strict-mcp-config',
                       '--mcp-config',json.dumps(mcp),'--allowedTools','mcp__delta__*','--permission-mode','dontAsk',
                       '--settings',json.dumps({'disableAllHooks':True,'autoMemoryEnabled':False}),
                       '--model',self.session['document']['model'],'--append-system-prompt',self.instructions,
                       '--resume' if self.resume else '--session-id',self.thread]
            try:
                self.proc=await self.spawn(arguments)
                self.proc.stdin.write((params['input'][0]['text']+'\n').encode());await self.proc.stdin.drain();self.proc.stdin.close()
                self.run_task=asyncio.create_task(self.read_turn(self.proc))
            except BaseException:
                self.server.close();await self.server.wait_closed();self.server=None;raise
            return {'turn':{'id':self.bridge_id}}
        if method=='turn/interrupt':
            if self.proc and self.proc.returncode is None:
                self.proc.send_signal(signal.SIGINT)
                try:await asyncio.wait_for(self.proc.wait(),10)
                except asyncio.TimeoutError:self.proc.kill();await self.proc.wait()
            if self.run_task:await self.run_task
            return {}
        raise ValueError('This operation is unavailable for this provider.')

    async def mcp(self,reader,writer):
        task=asyncio.current_task();self.bridge_tasks.add(task)
        try:
            headers=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),10)
            lines=headers.decode('latin1').split('\r\n');method,path,_=lines[0].split(' ',2)
            fields={k.strip().lower():v.strip() for line in lines[1:] if ':' in line for k,v in [line.split(':',1)]}
            size=int(fields.get('content-length','0'))
            if path!='/mcp' or not hmac.compare_digest(fields.get('authorization',''),'Bearer '+self.bridge_secret):
                await self.http(writer,403,{});return
            if method!='POST':await self.http(writer,405,{});return
            if not 0<size<=2_000_000:await self.http(writer,413,{});return
            message=json.loads(await asyncio.wait_for(reader.readexactly(size),10));ident=message.get('id');kind=message.get('method')
            if ident is None:await self.http(writer,202,None);return
            if kind=='initialize':result={'protocolVersion':message.get('params',{}).get('protocolVersion','2025-03-26'),
                'capabilities':{'tools':{}},'serverInfo':{'name':'delta-observatory','version':'1'}}
            elif kind=='ping':result={}
            elif kind=='tools/list':result={'tools':self.adapter.list_tools()}
            elif kind=='tools/call':
                p=message['params'];name=p['name']
                try:
                    result=await self.call_tool({'tool':name,'threadId':self.thread,'callId':self.bridge_id+'-'+str(ident),'arguments':p.get('arguments',{})})
                    self.emit({'event':'tool','name':name,'success':not result.get('isError',False)})
                except Exception as error:result={'isError':True,'content':[{'type':'text','text':self.scrub(error)}]}
            else:
                await self.http(writer,200,{'jsonrpc':'2.0','id':ident,'error':{'code':-32601,'message':'Unknown method.'}});return
            await self.http(writer,200,{'jsonrpc':'2.0','id':ident,'result':result})
        except (ValueError,KeyError,asyncio.IncompleteReadError,asyncio.LimitOverrunError,asyncio.TimeoutError):
            await self.http(writer,400,{})
        finally:
            writer.close();await writer.wait_closed();self.bridge_tasks.discard(task)

    async def http(self,writer,code,value):
        body=b'' if value is None else json.dumps(value).encode()
        writer.write(f'HTTP/1.1 {code} Response\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'.encode()+body)
        await writer.drain()

    async def read_turn(self,proc):
        failed='The provider stopped before completing this turn.';usage=0;messages={};model_ids=set()
        async def discard():
            while await proc.stderr.read(4096):pass
        errors=asyncio.create_task(discard())
        try:
            while line:=await proc.stdout.readline():
                try:message=json.loads(line)
                except ValueError:continue
                kind=message.get('type')
                if kind=='stream_event':
                    delta=message.get('event',{}).get('delta',{})
                    if delta.get('type')=='text_delta':self.emit({'event':'message_delta','text':self.scrub(delta.get('text',''))})
                elif kind=='assistant':
                    response=message.get('message',{})
                    if response.get('model'):model_ids.add(self.scrub(response['model'])[:120])
                    text='\n'.join(b['text'] for b in response.get('content',[]) if b.get('type')=='text')
                    if text:await self.record('agent_message',text);self.emit({'event':'message','text':self.scrub(text)})
                    count=response.get('usage',{})
                    messages[response.get('id',str(len(messages)))]=sum(int(count.get(k,0) or 0) for k in ('input_tokens','output_tokens','cache_creation_input_tokens','cache_read_input_tokens'))
                    usage=sum(messages.values())
                    await self.measure(usage)
                elif kind=='result':
                    failed='Provider request failed. Check your account and retry.' if message.get('is_error') else ''
                    total=message.get('usage',{})
                    usage=max(usage,sum(int(total.get(k,0) or 0) for k in ('input_tokens','output_tokens','cache_creation_input_tokens','cache_read_input_tokens')))
                    await self.measure(usage)
                    self.resume=True
            await proc.wait()
            if proc.returncode and not failed:failed='The provider process stopped with an error.'
        except Exception as error:failed=self.scrub(error)
        finally:
            if proc.returncode is None:proc.terminate();await proc.wait()
            await errors
            self.paused=True;self.turn=None
            if self.server:self.server.close();await self.server.wait_closed();self.server=None
            if self.bridge_tasks:await asyncio.gather(*list(self.bridge_tasks),return_exceptions=True)
            self.token_offset=self.session['document']['tokens'] if self.session else 0
            await self.state(state='error' if failed else 'idle')
            await self.record('agent_error' if failed else 'agent_completed',failed or 'The agent turn ended. Provider model: '+', '.join(sorted(model_ids))+'.')
            self.emit({'event':'turn','state':'error' if failed else 'idle','message':failed})

    async def measure(self,usage):
        if not self.session:return
        total=max(self.token_offset+usage,self.session['document']['tokens']);await self.state(tokens=total)
        self.emit({'event':'usage','tokens':total,'turns':self.session['document']['turns']})
        investigation=await self.api('/investigations/'+self.campaign)
        approved=next(r for r in investigation['revisions'] if r['id']==investigation['approved_revision_id'])
        sessions=await self.api('/investigations/'+self.campaign+'/sessions')
        if sum(s['document']['tokens'] for s in sessions['items'])>=approved['document']['limits']['model_tokens']:
            self.paused=True
            if self.proc and self.proc.returncode is None:self.proc.send_signal(signal.SIGINT)

    async def connect(self,*args,**kwargs):
        result=await super().connect(*args,**kwargs)
        self.token_offset=self.session['document']['tokens']
        return result

    async def close(self):
        if self.session:
            try:await self.interrupt()
            except Exception:pass
        await self.cancel_login()
        if self.server:self.server.close();await self.server.wait_closed();self.server=None
        self.proc=None;self.session=None;self.adapter=None;self.campaign=None;self.thread=None;self.agent_token=None
        self.token_offset=0;self.profile=None;self.credential_store=None;self.account_key=None
        if self.temporary:self.temporary.cleanup();self.temporary=None
        return {'state':'disconnected'}
