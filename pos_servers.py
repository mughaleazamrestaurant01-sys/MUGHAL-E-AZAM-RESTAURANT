import json
import functools
import hmac
import http.server
import threading
import urllib.request


class LocalAssetServer:
    """Serve the bundled interface from a private, verified loopback address."""

    def __init__(self, directory, api):
        handler = functools.partial(self._handler(), directory=directory)
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.server.daemon_threads = True
        self.server.api = api
        self.thread = threading.Thread(target=self.server.serve_forever, name='pos-assets', daemon=True)

    @staticmethod
    def _handler():
        class QuietAssetHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def _reply(self, status, payload):
                encoded = json.dumps(payload, ensure_ascii=False).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _payload(self):
                length = int(self.headers.get('Content-Length', 0))
                return json.loads(self.rfile.read(length).decode('utf-8')) if length else {}

            def _api_call(self, method, payload):
                api = self.server.api
                calls = {
                    'boot': lambda: api.get_boot_data(),
                    'printer-config': lambda: api.get_printer_config(),
                    'backup-directory': lambda: {'directory': api.get_backup_directory()},
                    'system-printers': lambda: api.get_system_printers(),
                    'save-state': lambda: api.save_state(payload.get('state', {})),
                    'save-printer-config': lambda: api.save_printer_config(payload.get('config', {})),
                    'authenticate': lambda: api.authenticate(payload.get('username'), payload.get('password')),
                    'save-user': lambda: api.save_user(payload.get('user', {}), payload.get('userId')),
                    'delete-user': lambda: api.delete_user(payload.get('userId')),
                    'print-direct': lambda: api.print_direct(payload.get('printerName'), payload.get('receiptData', {})),
                    'test-printer': lambda: api.test_printer(payload.get('printerName'), payload.get('receiptType', 'Test'), payload.get('cutMode', 'escpos_full')),
                    'create-backup': lambda: api.create_backup_now(),
                }
                if method not in calls:
                    raise ValueError('Unknown local POS API request.')
                return calls[method]()

            def do_GET(self):
                if self.path.startswith('/api/'):
                    try:
                        self._reply(200, self._api_call(self.path[5:], {}))
                    except Exception as exc:
                        self._reply(500, {'ok': False, 'error': f'Local POS service error: {exc}'})
                    return
                super().do_GET()

            def do_POST(self):
                if not self.path.startswith('/api/'):
                    self.send_error(404)
                    return
                try:
                    self._reply(200, self._api_call(self.path[5:], self._payload()))
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    self._reply(400, {'ok': False, 'error': f'Invalid local POS request: {exc}'})
                except Exception as exc:
                    self._reply(500, {'ok': False, 'error': f'Local POS service error: {exc}'})

        return QuietAssetHandler

    @property
    def url(self):
        host, port = self.server.server_address[:2]
        return f'http://{host}:{port}/index.html'

    def start(self):
        self.thread.start()
        try:
            with urllib.request.urlopen(self.url, timeout=3) as response:
                if response.status != 200:
                    raise RuntimeError(f'asset server returned HTTP {response.status}')
        except Exception:
            self.close()
            raise

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        if self.thread.is_alive():
            self.thread.join(timeout=2)


class SharedApiServer(http.server.ThreadingHTTPServer):
    """Small authenticated LAN gateway for a counter-owned POS database."""
    daemon_threads = True

    def __init__(self, address, api, token):
        self.api = api
        self.token = token
        super().__init__(address, SharedApiHandler)


class SharedApiHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _reply(self, status, payload):
        encoded = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _allowed(self):
        return hmac.compare_digest(self.headers.get('X-POS-Token', ''), self.server.token)

    def _body(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length).decode('utf-8')) if length else {}

    def do_GET(self):
        if not self._allowed():
            return self._reply(401, {'ok': False, 'error': 'Invalid shared POS token.'})
        if self.path == '/v1/boot':
            return self._reply(200, self.server.api.get_boot_data())
        if self.path == '/v1/backup-directory':
            return self._reply(200, {'directory': self.server.api.get_backup_directory()})
        return self._reply(404, {'ok': False, 'error': 'Unknown shared POS endpoint.'})

    def do_POST(self):
        if not self._allowed():
            return self._reply(401, {'ok': False, 'error': 'Invalid shared POS token.'})
        try:
            data = self._body()
            if self.path == '/v1/state':
                result = self.server.api.save_state(data.get('state', {}))
            elif self.path == '/v1/authenticate':
                result = self.server.api.authenticate(data.get('username'), data.get('password'))
            elif self.path == '/v1/users':
                result = self.server.api.save_user(data.get('user', {}), data.get('userId'))
            elif self.path == '/v1/backup':
                result = self.server.api.create_backup_now()
            else:
                return self._reply(404, {'ok': False, 'error': 'Unknown shared POS endpoint.'})
            self._reply(200, result)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._reply(400, {'ok': False, 'error': f'Invalid request: {exc}'})
        except Exception as exc:
            self._reply(500, {'ok': False, 'error': f'Shared POS server error: {exc}'})

    def do_DELETE(self):
        if not self._allowed():
            return self._reply(401, {'ok': False, 'error': 'Invalid shared POS token.'})
        if not self.path.startswith('/v1/users/'):
            return self._reply(404, {'ok': False, 'error': 'Unknown shared POS endpoint.'})
        try:
            self._reply(200, self.server.api.delete_user(int(self.path.rsplit('/', 1)[1])))
        except (ValueError, IndexError):
            self._reply(400, {'ok': False, 'error': 'Invalid user id.'})
