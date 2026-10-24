"""Check native login startup and cancellation without opening a browser or using an account."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from managed.providers import Providers
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--codex',type=Path,required=True);parser.add_argument('--claude',type=Path,required=True)
parser.add_argument('--bwrap',type=Path,default=Path('/usr/bin/bwrap'));parser.add_argument('--library-dir')
args=parser.parse_args()
async def main():
    with tempfile.TemporaryDirectory(prefix='delta-provider-login-') as directory:
        mux=Providers(SimpleNamespace(runtime_dir=args.codex,claude_runtime_dir=args.claude,state_dir=directory,
                                     bwrap=args.bwrap,library_dir=args.library_dir),lambda event:None)
        results={}
        try:
            await mux.handle('configure',{'token':'synthetic-owner-no-api-access'})
            for provider,kind,hosts in [('codex','chatgpt',('auth.openai.com','chatgpt.com')),
                                        ('claude','claude',('claude.ai','claude.com','platform.claude.com','console.anthropic.com'))]:
                await mux.handle('selectProvider',{'provider':provider})
                initial=await mux.handle('initialize',{'credential_store':'ephemeral'})
                assert initial['account'] is None and initial['session'] is None
                login=await mux.handle('login',{'type':kind});url=urlsplit(login['authUrl'])
                assert url.scheme=='https' and url.hostname in hosts
                await mux.handle('cancelLogin',{})
                final=await mux.handle('status',{})
                assert final['login'] is None and final['account'] is None
                results[provider]={'authorization_host':url.hostname,'startup':True,'cancellation':True}
            print(json.dumps({'status':'passed','providers':results,'browser_opened':False,'account_used':False,'model_requests':0}))
        finally:await mux.close()
asyncio.run(main())
