"""MCP server over stdio that gives the Delta Observatory API operations to an agent as tools.

The server reads the API description at startup and makes one tool for each operation (adapter/generate.py).
A tool call sends exactly one HTTP request with the client token and returns the status code and the response.
The API applies every permission, campaign rule, and scientific rule. The server adds no logic.

Settings:
  DELTA_API_URL            API address. Default http://localhost:30870/api
  DELTA_TOKEN_FILE         File that holds the client token. Without it, requests carry no token.
  DELTA_OPENAPI            Optional file or URL of the API description. Default <DELTA_API_URL>/openapi.json
  DELTA_ADAPTER_DOWNLOADS  Directory for responses that are not inline JSON. Default ~/.cache/delta-adapter/downloads
  DELTA_ADAPTER_INLINE_BYTES  Largest JSON response returned inline. Default 1000000
  DELTA_ADAPTER_TIMEOUT    Request timeout in seconds. Default 120

Run: python -m adapter.server
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from . import generate

PROTOCOL_VERSION = '2025-06-18'
SERVER_INFO = {'name': 'delta-observatory-api', 'version': '1'}


@dataclass
class Settings:
    api_url: str
    token: str | None
    openapi: str
    downloads: Path
    inline_bytes: int
    timeout: float

    @classmethod
    def from_env(cls, env=os.environ) -> 'Settings':
        api_url = env.get('DELTA_API_URL', 'http://localhost:30870/api').rstrip('/')
        token_file = env.get('DELTA_TOKEN_FILE')
        token = Path(token_file).expanduser().read_text().strip() if token_file else None
        return cls(api_url=api_url, token=token or None,
                   openapi=env.get('DELTA_OPENAPI') or f'{api_url}/openapi.json',
                   downloads=Path(env.get('DELTA_ADAPTER_DOWNLOADS', '~/.cache/delta-adapter/downloads')).expanduser(),
                   inline_bytes=int(env.get('DELTA_ADAPTER_INLINE_BYTES', '1000000')),
                   timeout=float(env.get('DELTA_ADAPTER_TIMEOUT', '120')))


class Adapter:
    def __init__(self, settings: Settings, document: dict):
        self.settings = settings
        self.tools = {t['name']: t for t in generate.tools(document)}
        parts = urllib.parse.urlsplit(settings.api_url)
        self.origin = f'{parts.scheme}://{parts.netloc}'

    def scrub(self, text: str) -> str:
        """Remove the client token from any text that leaves the adapter."""
        token = self.settings.token
        return text.replace(token, '<token>') if token else text

    def list_tools(self) -> list[dict]:
        return [{'name': t['name'], 'description': t['description'], 'inputSchema': t['inputSchema']}
                for t in self.tools.values()]

    def request(self, name: str, arguments: dict) -> tuple[int, dict]:
        """Send the request of one tool call. Return the HTTP status and a description of the response."""
        tool = self.tools[name]
        http = tool['http']
        unknown = sorted(set(arguments) - set(tool['inputSchema']['properties']))
        missing = [k for k in tool['inputSchema']['required'] if k not in arguments]
        if unknown or missing:
            raise ValueError(f'unknown arguments {unknown}, missing arguments {missing}')
        path = http['path']
        for key in http['path_params']:
            path = path.replace('{' + key + '}', urllib.parse.quote(str(arguments[key]), safe=''))
        query = []
        for key in http['query_params']:
            value = arguments.get(key)
            if value is None:
                continue
            for item in (value if isinstance(value, list) else [value]):
                query.append((key, json.dumps(item) if isinstance(item, bool) else str(item)))
        url = self.origin + path + ('?' + urllib.parse.urlencode(query) if query else '')
        data, headers = None, {'Accept': 'application/json, */*'}
        if http['body'] and generate.BODY in arguments:
            data = json.dumps(arguments[generate.BODY]).encode()
            headers['Content-Type'] = 'application/json'
        if self.settings.token:
            headers['Authorization'] = f'Bearer {self.settings.token}'
        request = urllib.request.Request(url, data=data, headers=headers, method=http['method'])
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout) as response:
                return response.status, self.describe(name, response.headers, response.read())
        except urllib.error.HTTPError as error:
            with error:
                return error.code, self.describe(name, error.headers, error.read())

    def describe(self, name: str, headers, payload: bytes) -> dict:
        media_type = (headers.get('Content-Type') or '').split(';')[0].strip()
        encoding = headers.get('Content-Encoding')
        is_json = media_type == 'application/json' or media_type.endswith('+json')
        if is_json and not encoding and len(payload) <= self.settings.inline_bytes:
            try:
                return {'body': json.loads(payload)}
            except ValueError:
                pass
        return {'download': self.save(name, headers, payload, media_type, encoding)}

    def save(self, name: str, headers, payload: bytes, media_type: str, encoding: str | None) -> dict:
        """Keep the response bytes unchanged in a file, so that the SHA-256 can be compared with a stored checksum."""
        digest = hashlib.sha256(payload).hexdigest()
        disposition = headers.get('Content-Disposition') or ''
        match = re.search(r'filename="?([^";]+)"?', disposition)
        base = re.sub(r'[^A-Za-z0-9._-]', '_', match.group(1)) if match else f'{name}.bin'
        directory = self.settings.downloads
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f'{digest[:16]}-{base}'
        target.write_bytes(payload)
        return {'path': str(target), 'bytes': len(payload), 'sha256': digest, 'media_type': media_type or None,
                'content_encoding': encoding, 'note': 'The file holds the response bytes without decoding.'}

    def call(self, name: str, arguments: dict) -> dict:
        """The MCP result of one tool call."""
        if name not in self.tools:
            return {'content': [{'type': 'text', 'text': f'unknown tool {name}'}], 'isError': True}
        try:
            status, response = self.request(name, arguments or {})
        except ValueError as error:
            return {'content': [{'type': 'text', 'text': self.scrub(str(error))}], 'isError': True}
        except (urllib.error.URLError, OSError) as error:
            return {'content': [{'type': 'text', 'text': self.scrub(f'request failed: {error}')}], 'isError': True}
        text = json.dumps({'status': status, **response}, indent=1, ensure_ascii=False)
        return {'content': [{'type': 'text', 'text': self.scrub(text)}], 'isError': status >= 400}

    def handle(self, message: dict) -> dict | None:
        """Answer one JSON-RPC message. A notification has no answer."""
        method, ident = message.get('method'), message.get('id')
        if ident is None:
            return None
        if method == 'initialize':
            requested = (message.get('params') or {}).get('protocolVersion')
            result = {'protocolVersion': requested or PROTOCOL_VERSION, 'capabilities': {'tools': {'listChanged': False}},
                      'serverInfo': SERVER_INFO}
        elif method == 'ping':
            result = {}
        elif method == 'tools/list':
            result = {'tools': self.list_tools()}
        elif method == 'tools/call':
            params = message.get('params') or {}
            result = self.call(params.get('name'), params.get('arguments') or {})
        else:
            return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32601, 'message': f'unknown method {method}'}}
        return {'jsonrpc': '2.0', 'id': ident, 'result': result}


def log(text: str):
    print(text, file=sys.stderr, flush=True)


def serve(adapter: Adapter, stdin=sys.stdin, stdout=sys.stdout):
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            answer = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'parse error'}}
        else:
            answer = adapter.handle(message)
            if message.get('method') == 'tools/call':
                params = message.get('params') or {}
                log(f"tool {params.get('name')}: {'error' if answer and answer['result'].get('isError') else 'ok'}")
        if answer is not None:
            stdout.write(json.dumps(answer) + '\n')
            stdout.flush()


def main() -> int:
    settings = Settings.from_env()
    adapter = Adapter(settings, generate.load(settings.openapi))
    log(f'{len(adapter.tools)} tools from {settings.openapi}')
    serve(adapter)
    return 0


if __name__ == '__main__':
    sys.exit(main())
