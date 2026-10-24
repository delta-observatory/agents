"""Run the published Claude Code binary with a separate profile and no workspace mounts."""
from pathlib import Path


def command(binary_root,profile,bwrap,arguments,extra_env=None):
    binary_root,profile,bwrap=(Path(p).resolve() for p in (binary_root,profile,bwrap))
    if not (binary_root/'claude').is_file() or not bwrap.is_file():
        raise ValueError('The bundled Claude Code runtime or Linux isolation runtime is unavailable.')
    profile.mkdir(parents=True,exist_ok=True,mode=0o700);profile.chmod(0o700)
    # The caller supplies a clean environment. Secrets never enter command arguments.
    args=[str(bwrap),'--die-with-parent','--new-session','--unshare-user','--unshare-pid','--unshare-uts','--unshare-ipc',
          '--unsetenv','LD_LIBRARY_PATH','--setenv','PATH','/usr/bin:/bin','--setenv','HOME','/home/delta',
          '--setenv','CLAUDE_CONFIG_DIR','/home/delta/.claude','--setenv','LANG','C.UTF-8',
          '--setenv','MCP_CONNECTION_NONBLOCKING','0','--setenv','ENABLE_TOOL_SEARCH','false','--setenv','DISABLE_AUTOUPDATER','1','--setenv','BROWSER','/bin/true',
          '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/home/delta',
          '--bind',str(profile),'/home/delta/.claude','--ro-bind',str(binary_root),'/opt/provider',
          '--dir','/workspace','--chdir','/workspace']
    for directory in ('/usr','/bin','/lib','/lib64'):
        if Path(directory).exists():args+=['--ro-bind',directory,directory]
    for item in ('/etc/ssl','/etc/resolv.conf','/etc/hosts','/etc/nsswitch.conf'):
        if Path(item).exists():args+=['--ro-bind',item,item]
    for key,value in (extra_env or {}).items():args+=['--setenv',key,value]
    return args+['/opt/provider/claude',*arguments]
