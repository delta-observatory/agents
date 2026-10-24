"""Account and session checks use a process fixture, never a real provider account."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,Mock,patch
from managed.claude import ClaudeHost
from managed.claude_sandbox import command
from managed.providers import Providers

FIXTURE='''
import json,pathlib,sys,time
profile=pathlib.Path(sys.argv[1]);profile.mkdir(exist_ok=True,parents=True)
saved=profile/'fixture-account.json';args=sys.argv[2:]
if args==['auth','status','--json']:
 print(json.dumps({'loggedIn':saved.exists(),'authMethod':'claude.ai','email':'fixture@example.invalid','subscriptionType':'pro'}));sys.exit(0 if saved.exists() else 1)
if args==['auth','logout']:
 saved.unlink(missing_ok=True);sys.exit(0)
if args[:2]==['auth','login']:
 sys.stdout.write('Open https://claude.com/cai/oauth/author');sys.stdout.flush();time.sleep(.02)
 print('ize?state=fixture-state&code_challenge=fixture-challenge',flush=True)
 value=sys.stdin.readline().strip()
 if value=='fixture-code':saved.write_text('{}');sys.exit(0)
 sys.exit(1)
'''

class ClaudeLoginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        fixture=self.base/'provider.py';fixture.write_text(FIXTURE)
        def launch(runtime,profile,bwrap,arguments,extra_env):return [sys.executable,str(fixture),str(profile),*arguments]
        self.patcher=patch('managed.claude.command',side_effect=launch);self.patcher.start()
        self.events=[];self.host=ClaudeHost(SimpleNamespace(claude_runtime_dir='unused',bwrap='unused',state_dir=self.temp.name,library_dir=None),self.events.append)
        self.host.owner_token='fixture-owner';self.host.api=AsyncMock()

    async def asyncTearDown(self):
        await self.host.close();self.patcher.stop();self.temp.cleanup()

    async def test_login_cancel_callback_code_status_and_logout(self):
        await self.host.initialize()
        result=await self.host.login({'type':'claude'})
        self.assertEqual(result['authUrl'],'https://claude.com/cai/oauth/authorize?state=fixture-state&code_challenge=fixture-challenge')
        with self.assertRaisesRegex(ValueError,'pending login'):await self.host.login({'type':'claude'})
        await self.host.handle('cancelLogin',{});self.assertIsNone((await self.host.status())['account'])
        await self.host.login({'type':'sso'});await self.host.handle('submitLoginCode',{'code':'fixture-code'})
        await self.host.login_task
        self.assertEqual((await self.host.status())['account']['email'],'fixture@example.invalid')
        self.assertTrue(any(e.get('success') is True for e in self.events));self.host.api.assert_not_called()
        self.assertNotIn('fixture-code',json.dumps(self.events));self.assertEqual(self.host.scrub('fixture-code'),'<credential>')
        await self.host.handle('logout',{});self.assertIsNone((await self.host.status())['account'])

    async def test_profile_reuses_account_and_memory_is_removed(self):
        await self.host.initialize(credential_store='provider')
        await self.host.login({'type':'console'});await self.host.handle('submitLoginCode',{'code':'fixture-code'});await self.host.login_task
        await self.host.close();status=await self.host.initialize(credential_store='provider')
        self.assertIsNotNone(status['account']);await self.host.handle('logout',{})
        self.assertIsNone((await self.host.initialize(credential_store='provider'))['account'])
        await self.host.close();await self.host.initialize();profile=self.host.profile
        await self.host.close();self.assertFalse(profile.exists())

    async def test_failure_and_storage_validation(self):
        with self.assertRaisesRegex(ValueError,'storage'):await self.host.initialize(credential_store='keyring')
        await self.host.initialize()
        await self.host.login({'type':'claude'});await self.host.handle('submitLoginCode',{'code':'invalid-code'});await self.host.login_task
        self.assertTrue(any(e.get('success') is False for e in self.events));self.assertIsNone(self.host.pending_login)
        with self.assertRaisesRegex(ValueError,'Start provider'):await self.host.handle('submitLoginCode',{'code':'fixture-code'})
        with self.assertRaisesRegex(ValueError,'Sign out'):await self.host.initialize(credential_store='provider')

    async def test_api_key_never_enters_process_arguments(self):
        await self.host.initialize()
        self.host.account_key='fixture-private-key'
        with patch('asyncio.create_subprocess_exec',new_callable=AsyncMock) as spawn:
            await self.host.spawn(['auth','status'])
            self.assertNotIn('fixture-private-key',str(spawn.call_args.args))
            env=spawn.call_args.kwargs['env']
            self.assertEqual(env['ANTHROPIC_API_KEY'],'fixture-private-key')
            self.assertEqual(set(env),{'PATH','LANG','ANTHROPIC_API_KEY'})

    async def test_initialize_failure_cleans_memory_profile(self):
        self.host.cli=AsyncMock(side_effect=ValueError('fixture failure'))
        with self.assertRaisesRegex(ValueError,'fixture failure'):await self.host.initialize()
        self.assertIsNone(self.host.profile);self.assertIsNone(self.host.temporary)

    async def test_switch_cancels_pending_login_and_preserves_accounts(self):
        mux=Providers(self.host.args,Mock());mux.hosts['claude']=self.host
        mux.hosts['codex'].status=AsyncMock(return_value={'provider':'codex'})
        await mux.handle('selectProvider',{'provider':'claude'});await self.host.initialize();await self.host.login({'type':'claude'})
        await mux.handle('selectProvider',{'provider':'codex'});self.assertIsNone(self.host.pending_login)
        mux.hosts['codex'].session={'id':'active'}
        with self.assertRaisesRegex(ValueError,'Disconnect'):await mux.handle('selectProvider',{'provider':'claude'})
        with self.assertRaisesRegex(ValueError,'Select'):await mux.handle('selectProvider',{'provider':'unknown'})

class ClaudeBoundaryTests(unittest.TestCase):
    def test_namespace_has_no_host_credentials_and_preserves_oauth(self):
        with tempfile.TemporaryDirectory() as root:
            base=Path(root);(base/'claude').touch();(base/'bwrap').touch()
            args=command(base,base/'profile',base/'bwrap',['auth','login'])
            for value in ('--unsetenv','CLAUDE_CONFIG_DIR','--unshare-pid'):self.assertIn(value,args)
            for value in ('DATABASE_URL','DBUS_SESSION_BUS_ADDRESS','/run','--bare'):self.assertNotIn(value,args)
            self.assertEqual(args[-3:],['/opt/provider/claude','auth','login'])
            self.assertEqual((base/'profile').stat().st_mode&0o777,0o700)
