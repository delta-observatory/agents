import asyncio
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from managed.host import Host, permitted
from managed.sandbox import command, configuration

class BoundaryTests(unittest.TestCase):
    def test_configuration_has_no_shell_or_dispatcher(self):
        config=tomllib.loads(configuration())
        self.assertEqual(config['cli_auth_credentials_store'],'ephemeral')
        self.assertEqual(config['sandbox_mode'],'read-only')
        for name in ('shell_tool','unified_exec','code_mode_host','apps','multi_agent_v2'):
            self.assertFalse(config['features'][name])
        self.assertFalse(config['agents']['enabled'])
        self.assertFalse(config['skills']['bundled']['enabled'])
        with self.assertRaises(ValueError):configuration('file')

    def test_namespace_has_no_workspace_mount_or_token(self):
        with tempfile.TemporaryDirectory() as root:
            base=Path(root);(base/'codex').touch();(base/'bwrap').touch()
            args=command(base,base/'profile',base/'bwrap')
            self.assertIn('--clearenv',args)
            self.assertNotIn('DATABASE_URL',args)
            self.assertNotIn('/run',args)
            self.assertEqual(args[args.index('--chdir')+1],'/workspace')
            self.assertNotIn(str(Path.home()),args)

    def test_tool_allowlist_excludes_owner_operations(self):
        for path in ('/api/admin/clients','/api/acquisitions','/api/investigations/{campaign_id}/approve','/api/agent-sessions/{session_id}/turn','/api/runs'):
            self.assertFalse(permitted({'http':{'path':path,'method':'POST'}}))
        for path in ('/api/investigations/{campaign_id}/sessions','/api/runs/{run_id}/export'):
            self.assertFalse(permitted({'http':{'path':path,'method':'GET'}}))
        self.assertTrue(permitted({'http':{'path':'/api/investigations/{campaign_id}/execute','method':'POST'}}))

class HostTests(unittest.IsolatedAsyncioTestCase):
    async def test_consent_and_model_before_session_creation(self):
        host=Host(SimpleNamespace(),Mock());host.api=AsyncMock()
        with self.assertRaises(ValueError):await host.connect('gpt-5.4',False)
        with self.assertRaises(ValueError):await host.connect('unverified-model',True)
        host.api.assert_not_called()

    async def test_paused_tool_and_foreign_scope_fail_without_api_write(self):
        host=Host(SimpleNamespace(),Mock());host.reply=AsyncMock();host.api=AsyncMock()
        await host.tool({'id':1,'params':{'tool':'execute'}})
        self.assertFalse(host.reply.call_args[0][1]['success']);host.api.assert_not_called()
        host.paused=False;host.thread='thread';host.campaign='campaign'
        host.api.return_value={'state':'ready','head_revision_id':'r','approved_revision_id':'r'}
        call=Mock();host.adapter=SimpleNamespace(tools={'execute':{'http':{'path':'/api/investigations/{campaign_id}/execute','path_params':['campaign_id']}}},call=call)
        await host.tool({'id':2,'params':{'tool':'execute','threadId':'thread','callId':'stable','arguments':{'campaign_id':'other'}}})
        call.assert_not_called();self.assertFalse(host.reply.call_args[0][1]['success'])
        call.return_value={'content':[{'text':'ok'}]}
        await host.tool({'id':3,'params':{'tool':'execute','threadId':'thread','callId':'stable','arguments':{'campaign_id':'campaign','body':{'request_key':'model-controlled'}}}})
        self.assertEqual(call.call_args[0][1]['body']['request_key'],'agent-stable')
        self.assertTrue(host.reply.call_args[0][1]['success'])

    async def test_failed_connection_still_closes(self):
        host=Host(SimpleNamespace(),Mock());host.interrupt=AsyncMock(side_effect=ValueError('offline'))
        host.proc=SimpleNamespace(returncode=None,terminate=Mock(),wait=AsyncMock(),kill=Mock());host.session={'id':'one'}
        proc=host.proc
        await host.close()
        proc.terminate.assert_called_once();self.assertIsNone(host.proc)

    def test_credentials_are_scrubbed(self):
        host=Host(SimpleNamespace(),Mock());host.secrets=['private-owner-token']
        self.assertNotIn('private-owner-token',host.scrub('error private-owner-token'))
        self.assertNotIn('sk-abcdefghijk1234567890',host.scrub('sk-abcdefghijk1234567890'))
