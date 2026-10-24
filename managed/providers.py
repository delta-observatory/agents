"""Select provider processes without sharing accounts or session credentials."""
from .host import Host
from .claude import ClaudeHost


class Providers:
    def __init__(self,args,emit):
        self.emit=emit;self.active='codex'
        self.hosts={name:kind(args,lambda event,name=name:emit({**event,'provider':name}))
                    for name,kind in (('codex',Host),('claude',ClaudeHost))}

    def scrub(self,value):
        for host in self.hosts.values():value=host.scrub(value)
        return value

    async def close(self):
        for host in self.hosts.values():await host.close()
        return {'state':'disconnected'}

    async def handle(self,action,params):
        if action=='configure':
            for host in self.hosts.values():await host.handle(action,params)
            return {'ready':True}
        if action=='shutdown':return await self.close()
        if action=='selectProvider':
            selected=params.get('provider')
            if selected not in self.hosts:raise ValueError('Select OpenAI or Anthropic.')
            if selected==self.active:return await self.hosts[selected].status()
            current=self.hosts[self.active]
            if current.session:raise ValueError('Disconnect the investigation before changing providers.')
            if current.pending_login:await current.handle('cancelLogin',{})
            self.active=selected
            self.emit({'event':'account','provider':selected})
            return await self.hosts[selected].status()
        return await self.hosts[self.active].handle(action,params)
