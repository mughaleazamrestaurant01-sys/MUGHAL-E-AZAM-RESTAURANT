import json
import os
import hashlib
import hmac
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import argparse
import http.server
import time
import urllib.error
import urllib.request

import webview


def get_base_dir():
    return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))


def get_data_dir():
    """Keep operational data outside a PyInstaller bundle and uninstall folder."""
    root = os.environ.get('APPDATA') if sys.platform == 'win32' else os.path.expanduser('~/.local/share')
    path = os.path.join(root or os.path.expanduser('~'), 'MughalEAzamPOS')
    os.makedirs(path, exist_ok=True)
    return path


def acquire_single_instance():
    """Return a Windows mutex handle, or None when the POS is already open."""
    if sys.platform != 'win32':
        return True

    import ctypes

    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, 'Local\\MughalEAzamPOSDesktop')
    if not mutex:
        raise OSError('Unable to create the POS single-instance lock.')
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.user32.MessageBoxW(
            None,
            'Mughal-E-Azam POS is already open. Use the existing POS window instead of starting a second copy.',
            'Mughal-E-Azam POS',
            0x40,
        )
        ctypes.windll.kernel32.CloseHandle(mutex)
        return None
    return mutex


class Api:
    def __init__(self, database_path):
        self.database_path = database_path
        self.window = None
        self._database_lock = threading.RLock()
        self._last_automatic_backup = 0.0
        self._backup_in_progress = False
        self._initialize_database()

    def _connection(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA busy_timeout = 10000')
        connection.execute('PRAGMA temp_store = MEMORY')
        connection.execute('PRAGMA cache_size = -8000')
        return connection

    def _initialize_database(self):
        with self._connection() as db:
            db.execute('PRAGMA journal_mode = WAL')
            db.execute('PRAGMA synchronous = NORMAL')
            db.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL, role TEXT NOT NULL, name TEXT NOT NULL,
                permissions TEXT NOT NULL DEFAULT '[]')''')
            db.execute('CREATE TABLE IF NOT EXISTS application_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')

    @staticmethod
    def _hash_password(password, salt=None):
        salt = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 200_000)
        return f'pbkdf2_sha256${salt}${digest.hex()}'

    @staticmethod
    def _verify_password(password, stored):
        if stored.startswith('pbkdf2_sha256$'):
            try:
                _, salt, expected = stored.split('$', 2)
                actual = Api._hash_password(password, salt)
                return hmac.compare_digest(actual, stored)
            except (TypeError, ValueError):
                return False
        # Migrate legacy plaintext credentials after their first successful login.
        return hmac.compare_digest(password, stored)

    @staticmethod
    def _public_user(row):
        return {
            'id': row['id'], 'name': row['name'], 'username': row['username'],
            'role': row['role'], 'permissions': json.loads(row['permissions'])
        }

    def _create_database_backup(self, directory):
        try:
            os.makedirs(directory, exist_ok=True)
            destination = os.path.join(directory, 'pos_backup_latest.sqlite')
            temporary = f'{destination}.tmp'
            with self._database_lock:
                # SQLite backup makes a consistent copy even while the application is writing.
                with self._connection() as source, sqlite3.connect(temporary, timeout=10) as target:
                    source.backup(target)
                os.replace(temporary, destination)
            return {'ok': True, 'path': destination}
        except Exception as exc:
            if 'temporary' in locals() and os.path.exists(temporary):
                os.unlink(temporary)
            return {'ok': False, 'error': f'Backup failed: {exc}'}

    def _backup_after_write(self):
        """Schedule a backup without delaying the POS write/UI bridge response."""
        with self._connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'backup_directory'").fetchone()
        if not row or not row['value']:
            return {'ok': True, 'skipped': True}
        with self._database_lock:
            now = time.monotonic()
            if self._backup_in_progress or now - self._last_automatic_backup < 60:
                return {'ok': True, 'skipped': True}
            self._last_automatic_backup = now
            self._backup_in_progress = True

        def backup_in_background():
            try:
                self._create_database_backup(row['value'])
            finally:
                with self._database_lock:
                    self._backup_in_progress = False

        threading.Thread(target=backup_in_background, daemon=True).start()
        return {'ok': True, 'scheduled': True}

    def get_boot_data(self):
        """A fresh process deliberately has no session; only disk-backed users decide login."""
        return {'users': self.list_users(), 'state': self.load_state()}

    def list_users(self):
        with self._connection() as db:
            rows = db.execute('SELECT id, name, username, password, role, permissions FROM users ORDER BY id').fetchall()
        return [self._public_user(row) for row in rows]

    def authenticate(self, username, password):
        username = (username or '').strip()
        password = password or ''
        with self._connection() as db:
            row = db.execute('SELECT id, name, username, password, role, permissions FROM users WHERE username = ?', (username,)).fetchone()
            if not row or not self._verify_password(password, row['password']):
                return {'ok': False, 'error': 'Invalid credentials.'}
            if not row['password'].startswith('pbkdf2_sha256$'):
                db.execute('UPDATE users SET password = ? WHERE id = ?', (self._hash_password(password), row['id']))
                row = db.execute('SELECT id, name, username, password, role, permissions FROM users WHERE id = ?', (row['id'],)).fetchone()
        return {'ok': True, 'user': self._public_user(row)}

    def save_user(self, user, user_id=None):
        username = (user.get('username') or '').strip()
        if not username or not user.get('name') or (user_id is None and not user.get('password')):
            return {'ok': False, 'error': 'Name and username are required; a password is required for a new user.'}
        if user.get('password') and len(user['password']) < 8:
            return {'ok': False, 'error': 'Passwords must contain at least 8 characters.'}
        try:
            with self._connection() as db:
                if user_id is None:
                    cursor = db.execute('INSERT INTO users (username, password, role, name, permissions) VALUES (?, ?, ?, ?, ?)',
                        (username, self._hash_password(user['password']), user.get('role', 'Cashier'), user['name'], json.dumps(user.get('permissions', []))))
                    user_id = cursor.lastrowid
                else:
                    existing = db.execute('SELECT role FROM users WHERE id = ?', (user_id,)).fetchone()
                    if not existing:
                        return {'ok': False, 'error': 'The requested user account was not found.'}
                    # Do not allow the only administrator to be demoted. Without this
                    # guard, a valid account set could become impossible to administer.
                    if existing['role'] == 'Admin' and user.get('role', 'Cashier') != 'Admin':
                        admin_count = db.execute("SELECT COUNT(*) FROM users WHERE role = 'Admin'").fetchone()[0]
                        if admin_count <= 1:
                            return {'ok': False, 'error': 'The last administrator account cannot be changed to a non-admin role.'}
                    if user.get('password'):
                        db.execute('UPDATE users SET username=?, password=?, role=?, name=?, permissions=? WHERE id=?',
                            (username, self._hash_password(user['password']), user.get('role', 'Cashier'), user['name'], json.dumps(user.get('permissions', [])), user_id))
                    else:
                        db.execute('UPDATE users SET username=?, role=?, name=?, permissions=? WHERE id=?',
                            (username, user.get('role', 'Cashier'), user['name'], json.dumps(user.get('permissions', [])), user_id))
            self._backup_after_write()
            return {'ok': True, 'users': self.list_users(), 'id': user_id}
        except sqlite3.IntegrityError:
            return {'ok': False, 'error': 'That username already exists.'}

    def delete_user(self, user_id):
        with self._connection() as db:
            count = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            if count <= 1:
                return {'ok': False, 'error': 'The last user account cannot be deleted.'}
            user = db.execute('SELECT role FROM users WHERE id = ?', (user_id,)).fetchone()
            if not user:
                return {'ok': False, 'error': 'The requested user account was not found.'}
            if user['role'] == 'Admin':
                admin_count = db.execute("SELECT COUNT(*) FROM users WHERE role = 'Admin'").fetchone()[0]
                if admin_count <= 1:
                    return {'ok': False, 'error': 'The last administrator account cannot be deleted.'}
            if db.execute('DELETE FROM users WHERE id = ?', (user_id,)).rowcount != 1:
                return {'ok': False, 'error': 'The requested user account was not found.'}
        self._backup_after_write()
        return {'ok': True, 'users': self.list_users()}

    def load_state(self):
        with self._connection() as db:
            row = db.execute("SELECT value FROM application_state WHERE key = 'pos_state'").fetchone()
        return json.loads(row['value']) if row else {}

    def save_state(self, state):
        # Users are intentionally excluded: they always use direct SQL writes above.
        try:
            if not isinstance(state, dict):
                return {'ok': False, 'error': 'POS data payload is invalid; expected an object.'}
            state = {key: value for key, value in state.items() if key != 'users'}
            encoded = json.dumps(state, ensure_ascii=False, separators=(',', ':'))
            with self._database_lock:
                with self._connection() as db:
                    db.execute("INSERT INTO application_state(key, value) VALUES ('pos_state', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                               (encoded,))
                backup = self._backup_after_write()
            return {'ok': True, 'backupError': backup.get('error', '')}
        except (TypeError, ValueError) as exc:
            return {'ok': False, 'error': f'POS data cannot be encoded: {exc}'}
        except sqlite3.Error as exc:
            return {'ok': False, 'error': f'POS database write failed: {exc}'}
        except Exception as exc:
            return {'ok': False, 'error': f'POS data save failed: {exc}'}

    def get_printer_config(self):
        with self._connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'printer_config'").fetchone()
        try:
            return json.loads(row['value']) if row else {}
        except (TypeError, ValueError):
            return {}

    def save_printer_config(self, config):
        try:
            with self._connection() as db:
                db.execute("INSERT INTO settings(key, value) VALUES ('printer_config', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(config),))
            return {'ok': True}
        except (TypeError, ValueError, sqlite3.Error) as exc:
            return {'ok': False, 'error': f'Printer settings save failed: {exc}'}

    def get_system_printers(self):
        """Return installed system print queues; physical-device discovery is driver/OS-owned."""
        try:
            if sys.platform == 'win32':
                import win32print
                flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
                return {'printers': [p[2] for p in win32print.EnumPrinters(flags)], 'error': ''}
            result = subprocess.run(['lpstat', '-e'], capture_output=True, text=True, check=False)
            if result.returncode:
                return {'printers': [], 'error': result.stderr.strip() or 'The system print service did not return any printers.'}
            return {'printers': [line.strip() for line in result.stdout.splitlines() if line.strip()], 'error': ''}
        except Exception as exc:
            return {'printers': [], 'error': f'Unable to read system printers: {exc}'}

    def test_printer(self, printer_name, receipt_type='Test', cut_mode='escpos_full'):
        return self.print_direct(printer_name, {
            'title': f'TEST {receipt_type.upper()}', 'orderId': 'TEST-001',
            'items': [], 'isKot': receipt_type.upper() == 'KOT', 'cutMode': cut_mode
        })

    @staticmethod
    def _print_with_windows_driver(printer_name, text):
        """Print through the Star Windows driver so its Document Bottom cut applies."""
        import win32ui

        printer_dc = win32ui.CreateDC()
        printer_dc.CreatePrinterDC(printer_name)
        font = win32ui.CreateFont({'name': 'Consolas', 'height': -24, 'weight': 400})
        printer_dc.StartDoc('POS Receipt')
        try:
            printer_dc.StartPage()
            printer_dc.SelectObject(font)
            x, y = 24, 24
            line_height = max(24, printer_dc.GetTextExtent('Ag')[1] + 4)
            for receipt_line in text.rstrip('\n').split('\n'):
                printer_dc.TextOut(x, y, receipt_line)
                y += line_height
            printer_dc.EndPage()
            printer_dc.EndDoc()
        except Exception:
            printer_dc.AbortDoc()
            raise
        finally:
            printer_dc.DeleteDC()

    def print_direct(self, printer_name, receipt_data):
        if not printer_name:
            return {'status': 'error', 'message': 'Select a system printer first.'}

        def money(value):
            return f"Rs. {float(value or 0):.2f}"

        width = 32
        is_kot = receipt_data.get('isKot', False)

        def center(value=''):
            value = str(value or '')[:width]
            return value.center(width)

        def line(left='', right=''):
            left, right = str(left), str(right)
            return left[:width - len(right) - 1] + ' ' * max(1, width - len(left[:width - len(right) - 1]) - len(right)) + right

        if is_kot:
            lines = [center('KITCHEN ORDER TICKET'), '-' * width,
                     f"Order: {receipt_data.get('orderId', '')}"]
            if receipt_data.get('time'):
                lines.append(f"Time: {receipt_data['time']}")
            if receipt_data.get('orderType'):
                lines.append(f"Type: {receipt_data['orderType']}")
            if receipt_data.get('tableName'):
                lines.append(f"Table: {receipt_data['tableName']}")
            if receipt_data.get('customerName'):
                lines.append(f"Customer: {receipt_data['customerName']}")
            lines.append('-' * width)
            for item in receipt_data.get('items', []):
                lines.append(f"{item.get('qty', 0)}x {item.get('name', '')}"[:width])
            lines.append('-' * width)
        else:
            lines = [
                center(receipt_data.get('restaurantName') or receipt_data.get('header') or 'MUGHAL-E-AZAM RESTAURANT'),
                center(receipt_data.get('restaurantTagline')),
                center(receipt_data.get('restaurantAddress')),
                center(receipt_data.get('restaurantPhone')),
                '-' * width,
                center(receipt_data.get('title', 'RECEIPT')),
                '-' * width,
                line('Order #', receipt_data.get('orderId', '')),
            ]
            if receipt_data.get('time'):
                lines.append(line('Date / Time', receipt_data['time']))
            if receipt_data.get('orderType'):
                lines.append(line('Order Type', receipt_data['orderType']))
            if receipt_data.get('tableName'):
                lines.append(line('Table', receipt_data['tableName']))
            if receipt_data.get('customerName'):
                lines.append(line('Customer', receipt_data['customerName']))
            if receipt_data.get('customerPhone'):
                lines.append(line('Phone', receipt_data['customerPhone']))
            if receipt_data.get('customerAddress'):
                lines.append('Address:')
                lines.extend(str(receipt_data['customerAddress'])[i:i + width] for i in range(0, len(str(receipt_data['customerAddress'])), width))
            lines.append('-' * width)
            for item in receipt_data.get('items', []):
                qty, name, price = item.get('qty', 0), item.get('name', ''), item.get('price', 0)
                lines.append(f"{qty}x {name}"[:width])
                lines.append(line('', money(float(qty or 0) * float(price or 0))))
            lines.append('-' * width)
            lines.append(line('Subtotal', money(receipt_data.get('subtotal'))))
            if float(receipt_data.get('discount') or 0):
                lines.append(line('Discount', '-' + money(receipt_data.get('discount'))))
            if float(receipt_data.get('deliveryFee') or 0):
                lines.append(line('Delivery Fee', money(receipt_data.get('deliveryFee'))))
            lines.append(line('TOTAL', money(receipt_data.get('grandTotal'))))
            if receipt_data.get('paymentMethod'):
                lines.append(line('Payment', receipt_data['paymentMethod']))
            lines.extend(['-' * width, center(receipt_data.get('receiptFooter') or 'Thank you for your order!')])

        text = '\n'.join(line for line in lines if line is not None) + '\n'
        # The Star Windows driver can perform a configured Document Bottom cut, but
        # only for a driver-rendered job. RAW jobs bypass that driver feature.
        # Keep raw command profiles for printers/emulations that require them.
        cut_mode = receipt_data.get('cutMode', 'escpos_full')
        cut_commands = {
            'star': b'\x1b\x69',             # Legacy Star (ESC i) setting.
            'star_full': None,                # Windows Star driver bottom cut.
            'star_raw_full': b'\x1b\x69',    # Star line-mode raw full cut.
            'star_partial': b'\x1b\x6d',     # Star line-mode partial cut.
            'escpos': b'\x1dV\x42\x00',     # Legacy ESC/POS setting.
            'escpos_full': b'\x1dV\x00',
            'escpos_partial': b'\x1dV\x01',
            'none': b'',
        }
        if cut_mode not in cut_commands:
            return {'status': 'error', 'message': 'The selected printer cut profile is invalid.'}
        if cut_mode == 'star_full' and sys.platform == 'win32':
            try:
                self._print_with_windows_driver(printer_name, text)
                return {'status': 'success', 'message': f'Print job sent to {printer_name} using the Windows Star driver.'}
            except Exception as exc:
                return {'status': 'error', 'message': f'Windows driver print failed: {exc}'}
        cut_command = (b'\n' * 5) + cut_commands[cut_mode]
        try:
            if sys.platform == 'win32':
                import win32print
                printer = win32print.OpenPrinter(printer_name)
                try:
                    win32print.StartDocPrinter(printer, 1, ('POS Receipt', None, 'RAW'))
                    win32print.StartPagePrinter(printer)
                    win32print.WritePrinter(printer, text.encode('utf-8') + cut_command)
                    win32print.EndPagePrinter(printer)
                    win32print.EndDocPrinter(printer)
                finally:
                    win32print.ClosePrinter(printer)
            else:
                result = subprocess.run(['lp', '-d', printer_name, '-o', 'raw'], input=text.encode('utf-8') + cut_command, capture_output=True, check=False)
                if result.returncode:
                    raise RuntimeError(result.stderr.decode(errors='replace').strip())
            return {'status': 'success', 'message': f'Print job sent to {printer_name}.'}
        except Exception as exc:
            return {'status': 'error', 'message': f'Print failed: {exc}'}

    def select_backup_folder(self):
        selected = self.window.create_file_dialog(webview.FOLDER_DIALOG) if self.window else None
        if not selected:
            return {'ok': False, 'cancelled': True}
        directory = selected[0] if isinstance(selected, (list, tuple)) else selected
        with self._database_lock:
            with self._connection() as db:
                db.execute("INSERT INTO settings(key, value) VALUES ('backup_directory', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (directory,))
            backup = self._create_database_backup(directory)
        if not backup['ok']:
            return backup
        return {'ok': True, 'directory': directory, 'path': backup['path']}

    def create_backup_now(self):
        directory = self.get_backup_directory()
        if not directory:
            return {'ok': False, 'error': 'Select a custom backup folder first.'}
        return self._create_database_backup(directory)

    def get_backup_directory(self):
        with self._connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'backup_directory'").fetchone()
        return row['value'] if row else ''

    def restore_from_directory(self):
        selected = self.window.create_file_dialog(webview.FOLDER_DIALOG) if self.window else None
        if not selected:
            return {'ok': False, 'cancelled': True}
        directory = selected[0] if isinstance(selected, (list, tuple)) else selected
        source = os.path.join(directory, 'pos_backup_latest.sqlite')
        if not os.path.isfile(source):
            return {'ok': False, 'error': 'pos_backup_latest.sqlite was not found in the selected folder.'}
        fd, temporary = tempfile.mkstemp(dir=os.path.dirname(self.database_path), suffix='.sqlite')
        os.close(fd)
        try:
            shutil.copy2(source, temporary)
            with sqlite3.connect(temporary) as candidate:
                if candidate.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    return {'ok': False, 'error': 'The selected backup database failed its integrity check.'}
                candidate.execute('SELECT 1 FROM users LIMIT 1')
            # Connections are short-lived, so no connection pool remains open here.
            os.replace(temporary, self.database_path)
            return {'ok': True, 'boot': self.get_boot_data()}
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


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

    # Backups are centrally owned; OS printers remain per terminal.
    def select_backup_folder(self): return {'ok': False, 'error': 'Select backup folders on the main counter PC.'}
    def restore_from_directory(self): return {'ok': False, 'error': 'Restore backups on the main counter PC.'}
    def get_system_printers(self): return Api.get_system_printers(self)
    def test_printer(self, printer_name, receipt_type='Test', cut_mode='escpos_full'): return Api.test_printer(self, printer_name, receipt_type, cut_mode)
    def print_direct(self, printer_name, receipt_data): return Api.print_direct(self, printer_name, receipt_data)


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

    instance_lock = acquire_single_instance()
    if instance_lock is None:
        return

    # Everything needed by the interface is local and bundled. Loading index.html
    # directly avoids starting a second HTTP service, selecting a port, and making
    # a loopback browser request during each desktop launch.
    local_html = os.path.join(get_base_dir(), 'index.html')
    api = RemoteApi(args.server_url, args.server_token, os.path.join(get_data_dir(), 'terminal-settings.sqlite')) if args.server_url else Api(os.path.join(get_data_dir(), 'database.sqlite'))
    if args.share_lan:
        threading.Thread(target=SharedApiServer((args.server_host, args.server_port), api, args.server_token).serve_forever, daemon=True).start()
    api.window = webview.create_window('MUGHAL-E-AZAM - Restaurant', local_html, js_api=api, width=1280, height=800, resizable=True, min_size=(900, 600))
    try:
        webview.start()
    finally:
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.kernel32.CloseHandle(instance_lock)


if __name__ == '__main__':
    main()
