import json
import os
import sys
import threading
import argparse
import urllib.error
import urllib.request

import webview

from pos_db import DatabaseManager, get_base_dir, get_data_dir
from pos_printer import PrinterManager
from pos_servers import LocalAssetServer, SharedApiServer


class Api(DatabaseManager, PrinterManager):
    """Facade class bridging database and printing capabilities to PyWebView."""
    pass


class RemoteApi:
    """pywebview bridge used by a second terminal; printing always stays local."""
    def __init__(self, server_url, token, local_settings_path):
        self.server_url = server_url.rstrip('/')
        self.token = token
        self.window = None
        self.local_api = Api(local_settings_path)

    def _request(self, path, method='GET', payload=None):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        request = urllib.request.Request(
            f'{self.server_url}{path}', data=data, method=method,
            headers={'X-POS-Token': self.token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            try:
                return json.loads(exc.read().decode('utf-8'))
            except Exception:
                return {'ok': False, 'error': f'Shared POS server returned HTTP {exc.code}.'}
        except (urllib.error.URLError, TimeoutError) as exc:
            return {'ok': False, 'error': f'Cannot reach shared POS server: {exc}'}

    def get_boot_data(self): return self._request('/v1/boot')
    def get_printer_config(self): return self.local_api.get_printer_config()
    def save_printer_config(self, config): return self.local_api.save_printer_config(config)
    def authenticate(self, username, password): return self._request('/v1/authenticate', 'POST', {'username': username, 'password': password})
    def save_state(self, state): return self._request('/v1/state', 'POST', {'state': state})
    def save_user(self, user, user_id=None): return self._request('/v1/users', 'POST', {'user': user, 'userId': user_id})
    def delete_user(self, user_id): return self._request(f'/v1/users/{user_id}', 'DELETE')
    def get_backup_directory(self): return self._request('/v1/backup-directory').get('directory', '')
    def create_backup_now(self): return self._request('/v1/backup', 'POST')

    def select_backup_folder(self): return {'ok': False, 'error': 'Select backup folders on the main counter PC.'}
    def restore_from_directory(self): return {'ok': False, 'error': 'Restore backups on the main counter PC.'}
    def get_system_printers(self): return PrinterManager.get_system_printers()
    def test_printer(self, printer_name, receipt_type='Test', cut_mode='escpos_full'): return self.local_api.test_printer(printer_name, receipt_type, cut_mode)
    def print_direct(self, printer_name, receipt_data): return self.local_api.print_direct(printer_name, receipt_data)


def main():
    parser = argparse.ArgumentParser(description='Mughal-E-Azam POS')
    parser.add_argument('--share-lan', action='store_true', help='Share this counter database with another POS terminal.')
    parser.add_argument('--server-host', default='0.0.0.0', help='LAN address to bind when --share-lan is enabled.')
    parser.add_argument('--server-port', type=int, default=8765, help='LAN port for shared POS access.')
    parser.add_argument('--server-token', default=os.environ.get('MUGHAL_POS_TOKEN', ''), help='Shared POS token; required for LAN mode.')
    parser.add_argument('--server-url', default=os.environ.get('MUGHAL_POS_SERVER', ''), help='Use the specified main-counter shared POS server.')
    args = parser.parse_args()
    if args.server_url and not args.server_token:
        parser.error('--server-token (or MUGHAL_POS_TOKEN) is required with --server-url.')
    if args.share_lan and not args.server_token:
        parser.error('--server-token (or MUGHAL_POS_TOKEN) is required with --share-lan.')

    asset_server = None
    try:
        api = RemoteApi(args.server_url, args.server_token, os.path.join(get_data_dir(), 'terminal-settings.sqlite')) if args.server_url else Api(os.path.join(get_data_dir(), 'database.sqlite'))
        asset_server = LocalAssetServer(get_base_dir(), api)
        asset_server.start()
        if args.share_lan:
            threading.Thread(target=SharedApiServer((args.server_host, args.server_port), api, args.server_token).serve_forever, daemon=True).start()
        api.window = webview.create_window('MUGHAL-E-AZAM - Restaurant', asset_server.url, js_api=api, width=1280, height=800, resizable=True, min_size=(900, 600))
        webview.start()
    except Exception as exc:
        print(f'POS startup failed: {exc}', file=sys.stderr)
        raise
    finally:
        if asset_server:
            asset_server.close()


if __name__ == '__main__':
    main()
