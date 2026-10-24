"""A Linux namespace boundary for Codex app-server.

The model process receives its separate provider profile and operating-system libraries.
It receives no Delta token, database socket, observations, or artifact directory.
"""
from pathlib import Path
import os
import json
import shlex
import re

DISABLED = ('shell_tool','unified_exec','apply_patch_freeform','multi_agent','multi_agent_v2','multi_agent_mode','collab','default_mode_request_user_input','send_message_to_user_async','remote_models',
            'apps','connectors','plugins','remote_plugin','plugin_hooks','codex_hooks','goals','memories',
            'memory_tool','web_search','web_search_cached','web_search_request','standalone_web_search',
            'image_generation','imagegenext','view_image','browser_use','browser_use_external','computer_use',
            'in_app_browser','workspace_dependencies','worktrees','js_repl','code_mode','code_mode_host',
            'code_mode_only','code_mode_tool_search','shell_snapshot','shell_snapshot_v2','skill_search',
            'runtime_agent_instances','request_permissions','request_permissions_tool','search_tool','sleep_tool',
            'guardian_approval','network_proxy','remote_control','external_agent_memory_import')


def configuration(credential_store='ephemeral'):
    if credential_store not in ('ephemeral', 'keyring'):
        raise ValueError('Only memory or operating-system credential storage is permitted.')
    denial = json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                        'permissionDecisionReason': 'Delta permits scientific actions only through its API tools.'}})
    hook = "printf '%s\\n' " + shlex.quote(denial)
    return ('cli_auth_credentials_store = "' + credential_store + '"\nweb_search = "disabled"\n'
            'approval_policy = "never"\nsandbox_mode = "read-only"\n'
            'check_for_update_on_startup = false\nproject_doc_max_bytes = 0\n'
            '[tools.experimental_request_user_input]\nenabled = false\n[skills]\ninclude_instructions = false\n[skills.bundled]\nenabled = false\n'
            '[agents]\nenabled = false\n[analytics]\nenabled = false\n[feedback]\nenabled = false\n'
            '[features]\n' + ''.join(f'{key} = false\n' for key in DISABLED) +
            'skip_host_skill_discovery = true\nhooks = true\n'
            '[[hooks.PreToolUse]]\nmatcher = "^(apply_patch|Edit|Write|Bash|shell|exec_command|spawn_agent|Agent)$"\n'
            '[[hooks.PreToolUse.hooks]]\ntype = "command"\ncommand = ' + json.dumps(hook) + '\ntimeout = 5\n')


def command(binary_root, profile, bwrap, credential_store='ephemeral', environment=None):
    env = environment or os.environ
    binary_root, profile, bwrap = map(lambda p: Path(p).resolve(), (binary_root, profile, bwrap))
    if not (binary_root/'codex').is_file() or not bwrap.is_file():
        raise ValueError('The bundled Codex runtime or Linux isolation runtime is unavailable.')
    profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    (profile/'config.toml').write_text(configuration(credential_store))
    args = [str(bwrap), '--die-with-parent','--new-session','--unshare-user','--unshare-pid','--unshare-uts','--unshare-ipc',
            '--clearenv','--setenv','PATH','/usr/bin:/bin','--setenv','HOME','/home/delta','--setenv','CODEX_HOME','/home/delta/.codex',
            '--setenv','LANG','C.UTF-8','--setenv','SSL_CERT_FILE','/etc/ssl/certs/ca-certificates.crt',
            '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/home/delta',
            '--bind',str(profile),'/home/delta/.codex','--ro-bind',str(binary_root),'/opt/codex',
            '--dir','/workspace','--chdir','/workspace']
    for directory in ('/usr','/bin','/lib','/lib64'):
        if Path(directory).exists():
            args.extend(['--ro-bind',directory,directory])
    for item in ('/etc/ssl','/etc/resolv.conf','/etc/hosts','/etc/nsswitch.conf'):
        if Path(item).exists():
            args.extend(['--ro-bind',item,item])
    if credential_store == 'keyring':
        bus = env.get('DBUS_SESSION_BUS_ADDRESS','')
        match = re.fullmatch(r'unix:path=(/run/user/[0-9]+/bus)', bus)
        if not match or not Path(match.group(1)).exists():
            raise ValueError('The operating-system credential store is unavailable. Use memory-only login.')
        args.extend(['--ro-bind',match.group(1),match.group(1),'--setenv','DBUS_SESSION_BUS_ADDRESS',bus])
    return args + ['/opt/codex/codex','app-server','--listen','stdio://']
