"""A local HTTP server for adapter and importer tests. It records each request and returns prepared responses."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import urllib.parse


class Stub:
    def __init__(self):
        self.requests = []
        self.routes = {}  # (method, path) -> callable(request) -> (status, headers, bytes)
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_one(self, method):
                parts = urllib.parse.urlsplit(self.path)
                length = int(self.headers.get('Content-Length') or 0)
                body = self.rfile.read(length) if length else b''
                request = {'method': method, 'path': parts.path, 'query': urllib.parse.parse_qs(parts.query),
                           'headers': dict(self.headers), 'body': json.loads(body) if body else None}
                stub.requests.append(request)
                route = stub.routes.get((method, parts.path))
                status, headers, payload = route(request) if route else (404, {}, b'{"detail": "not found"}')
                self.send_response(status)
                headers = {'Content-Type': 'application/json', **headers}
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                self.handle_one('GET')

            def do_POST(self):
                self.handle_one('POST')

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def json(self, method, path, status, document, headers=None):
        self.routes[(method, path)] = lambda request: (status, headers or {}, json.dumps(document).encode())

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
