"""Provider account lifecycle checks use a local protocol fixture, never real credentials."""
import asyncio
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,Mock,patch
from managed.host import Host

FIXTURE='''
import json,sys
account=None
for line in sys.stdin:
    request=json.loads(line)
    if 'id' not in request:continue
    method=request['method'];params=request.get('params',{});result={}
    if method=='account/read':result={'account':account}
    elif method=='account/login/start':
        if params['type']=='apiKey':account={'type':'apiKey'}
        else:result={'type':params['type'],'loginId':'fixture-login','authUrl':'https://auth.openai.com/fixture'}
    elif method=='account/logout':account=None
    elif method=='fixture/complete':
        account={'type':'chatgpt','email':'fixture@example.invalid','planType':'pro'}
        print(json.dumps({'method':'account/login/completed','params':{'loginId':'fixture-login','success':True}}),flush=True)
        print(json.dumps({'method':'account/updated','params':{'authMode':'chatgpt'}}),flush=True)
    print(json.dumps({'id':request['id'],'result':result}),flush=True)
'''

class LoginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        fixture=Path(self.temp.name)/'provider.py';fixture.write_text(FIXTURE)
        self.patcher=patch('managed.host.command',return_value=[sys.executable,str(fixture)])
        self.command=self.patcher.start()
        self.emit=Mock()
        self.host=Host(SimpleNamespace(runtime_dir='unused',state_dir=self.temp.name,bwrap='unused',library_dir=None),self.emit)
        self.host.owner_token='fixture-owner';self.host.api=AsyncMock()

    async def asyncTearDown(self):
        await self.host.close();self.patcher.stop();self.temp.cleanup()

    async def test_login_cancel_completion_and_logout_without_investigation(self):
        self.assertIsNone((await self.host.handle('status',{}))['account'])
        status=await self.host.handle('initialize',{})
        self.assertTrue(status['initialized']);self.assertIsNone(status['session'])
        self.host.api.assert_not_called()
        await self.host.handle('login',{'type':'chatgpt'})
        self.assertEqual((await self.host.status())['login']['loginId'],'fixture-login')
        with self.assertRaisesRegex(ValueError,'pending login'):await self.host.handle('login',{'type':'chatgpt'})
        self.assertIsNone((await self.host.handle('cancelLogin',{}))['login'])
        await self.host.handle('login',{'type':'chatgptDeviceCode'})
        await self.host.rpc('fixture/complete',{})
        await asyncio.sleep(0)
        status=await self.host.status()
        self.assertEqual(status['account']['type'],'chatgpt');self.assertIsNone(status['login'])
        await self.host.handle('logout',{})
        self.assertFalse((await self.host.status())['initialized'])
        self.host.api.assert_not_called()

    async def test_disconnect_preserves_account_and_logout_clears_process(self):
        await self.host.initialize()
        await self.host.handle('login',{'type':'apiKey','apiKey':'fixture-private-key'})
        status=await self.host.disconnect()
        self.assertEqual(status['account']['type'],'apiKey')
        self.assertTrue(status['initialized'])
        self.assertEqual(self.host.scrub('fixture-private-key'),'<credential>')
        with self.assertRaisesRegex(ValueError,'Sign out'):await self.host.initialize(credential_store='keyring')
        await self.host.handle('logout',{})
        self.assertIsNone(self.host.proc)

    async def test_login_requires_valid_type_and_approved_connection(self):
        await self.host.initialize()
        with self.assertRaisesRegex(ValueError,'supported login'):await self.host.handle('login',{'type':'unknown'})
        with self.assertRaisesRegex(ValueError,'API key'):await self.host.handle('login',{'type':'apiKey','apiKey':''})
        with self.assertRaisesRegex(ValueError,'Sign in'):await self.host.connect('gpt-5.4',True,campaign='11111111-1111-4111-8111-111111111111')
        await self.host.handle('login',{'type':'apiKey','apiKey':'fixture-key'})
        self.host.api.return_value={'state':'draft','head_revision_id':'a','approved_revision_id':None}
        with self.assertRaisesRegex(ValueError,'Approve'):await self.host.connect('gpt-5.4',True,campaign='11111111-1111-4111-8111-111111111111')
        self.assertEqual(self.host.api.await_count,1)

    async def test_foreign_thread_messages_do_not_enter_current_investigation(self):
        self.host.thread='current';self.host.session={'id':'current-session'}
        await self.host.notification({'method':'item/completed','params':{'threadId':'previous','item':{'type':'agentMessage','text':'Other investigation'}}})
        self.host.api.assert_not_called();self.emit.assert_not_called()
        self.host.session=None

    async def test_provider_process_failure_allows_reinitialization(self):
        await self.host.initialize()
        self.host.proc.terminate()
        await self.host.proc.wait()
        status=await self.host.initialize()
        self.assertTrue(status['initialized'])
        self.assertIsNone(status['account'])
