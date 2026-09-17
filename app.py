import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import http.server
import socketserver

import webview


def get_base_dir():
    return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))


def get_data_dir():
    """Keep operational data outside a PyInstaller bundle and uninstall folder."""
    root = os.environ.get('APPDATA') if sys.platform == 'win32' else os.path.expanduser('~/.local/share')
    path = os.path.join(root or os.path.expanduser('~'), 'MughalEAzamPOS')
    os.makedirs(path, exist_ok=True)
    return path


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def start_server(port, directory):
    class CustomHandler(QuietHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)
    with socketserver.TCPServer(('127.0.0.1', port), CustomHandler) as httpd:
        httpd.serve_forever()


class Api:
    def __init__(self, database_path):
        self.database_path = database_path
        self.window = None
        self._initialize_database()

    def _connection(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self):
        with self._connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL, role TEXT NOT NULL, name TEXT NOT NULL,
                permissions TEXT NOT NULL DEFAULT '[]')''')
            db.execute('CREATE TABLE IF NOT EXISTS application_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')

    def _backup_after_write(self):
        with self._connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'backup_directory'").fetchone()
        if not row or not row['value']:
            return
        directory = row['value']
        try:
            os.makedirs(directory, exist_ok=True)
            destination = os.path.join(directory, 'pos_backup_latest.sqlite')
            # SQLite backup makes a consistent copy even while the application is writing.
            with self._connection() as source, sqlite3.connect(destination) as target:
                source.backup(target)
        except Exception as exc:
            print(f'[BACKUP ERROR] {exc}')

    def get_boot_data(self):
        """A fresh process deliberately has no session; only disk-backed users decide login."""
        return {'users': self.list_users(), 'state': self.load_state()}

    def list_users(self):
        with self._connection() as db:
            rows = db.execute('SELECT id, name, username, password, role, permissions FROM users ORDER BY id').fetchall()
        return [{**dict(row), 'permissions': json.loads(row['permissions'])} for row in rows]

    def save_user(self, user, user_id=None):
        username = (user.get('username') or '').strip()
        if not username or not user.get('password') or not user.get('name'):
            return {'ok': False, 'error': 'Name, username, and password are required.'}
        try:
            with self._connection() as db:
                if user_id is None:
                    cursor = db.execute('INSERT INTO users (username, password, role, name, permissions) VALUES (?, ?, ?, ?, ?)',
                        (username, user['password'], user.get('role', 'Cashier'), user['name'], json.dumps(user.get('permissions', []))))
                    user_id = cursor.lastrowid
                else:
                    db.execute('UPDATE users SET username=?, password=?, role=?, name=?, permissions=? WHERE id=?',
                        (username, user['password'], user.get('role', 'Cashier'), user['name'], json.dumps(user.get('permissions', [])), user_id))
            self._backup_after_write()
            return {'ok': True, 'users': self.list_users(), 'id': user_id}
        except sqlite3.IntegrityError:
            return {'ok': False, 'error': 'That username already exists.'}

    def delete_user(self, user_id):
        with self._connection() as db:
            db.execute('DELETE FROM users WHERE id = ?', (user_id,))
        self._backup_after_write()
        return {'ok': True, 'users': self.list_users()}

    def load_state(self):
        with self._connection() as db:
            row = db.execute("SELECT value FROM application_state WHERE key = 'pos_state'").fetchone()
        return json.loads(row['value']) if row else {}

    def save_state(self, state):
        # Users are intentionally excluded: they always use direct SQL writes above.
        state.pop('users', None)
        with self._connection() as db:
            db.execute("INSERT INTO application_state(key, value) VALUES ('pos_state', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (json.dumps(state),))
        self._backup_after_write()
        return {'ok': True}

    def get_system_printers(self):
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

    def test_printer(self, printer_name, receipt_type='Test'):
        return self.print_direct(printer_name, {'title': f'TEST {receipt_type.upper()}', 'orderId': 'TEST-001', 'items': []})

    def print_direct(self, printer_name, receipt_data):
        if not printer_name:
            return {'status': 'error', 'message': 'Select a system printer first.'}
        # Keep the job short: no page-sized padding or trailing blank lines.  Thermal
        # printers feed after the last line only enough to perform the cut command.
        lines = [
            receipt_data.get('header', 'MUGHAL-E-AZAM RESTAURANT'),
            receipt_data.get('title', 'RECEIPT'),
            '-' * 32,
            f"Order: {receipt_data.get('orderId', '')}",
        ]
        if receipt_data.get('time'):
            lines.append(f"Time: {receipt_data['time']}")
        if receipt_data.get('tableName'):
            lines.append(f"Table: {receipt_data['tableName']}")
        if receipt_data.get('customerName'):
            lines.append(f"Customer: {receipt_data['customerName']}")
        lines.append('-' * 32)
        for item in receipt_data.get('items', []):
            quantity = item.get('qty', 1)
            name = item.get('name', '')
            amount = item.get('price', 0) * quantity
            lines.append(f'{quantity}x {name}  Rs.{amount}')
        lines.extend([
            '-' * 32,
            f"Subtotal: Rs.{receipt_data.get('subtotal', 0)}",
            f"Discount: Rs.{receipt_data.get('discount', 0)}" if receipt_data.get('discount', 0) else '',
            f"Delivery: Rs.{receipt_data.get('deliveryFee', 0)}" if receipt_data.get('deliveryFee', 0) else '',
            f"TOTAL: Rs.{receipt_data.get('grandTotal', 0)}",
            receipt_data.get('receiptFooter', ''),
        ])
        text = '\n'.join(line for line in lines if line) + '\n'
        try:
            if sys.platform == 'win32':
                import win32print
                printer = win32print.OpenPrinter(printer_name)
                try:
                    win32print.StartDocPrinter(printer, 1, ('POS Receipt', None, 'RAW'))
                    win32print.StartPagePrinter(printer)
                    win32print.WritePrinter(printer, text.encode('utf-8') + b'\x1dV\x42\x00')
                    win32print.EndPagePrinter(printer)
                    win32print.EndDocPrinter(printer)
                finally:
                    win32print.ClosePrinter(printer)
            else:
                result = subprocess.run(['lp', '-d', printer_name], input=text.encode('utf-8'), capture_output=True, check=False)
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
        with self._connection() as db:
            db.execute("INSERT INTO settings(key, value) VALUES ('backup_directory', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (directory,))
        self._backup_after_write()
        return {'ok': True, 'directory': directory}

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
            # Connections are short-lived, so no connection pool remains open here.
            os.replace(temporary, self.database_path)
            return {'ok': True, 'boot': self.get_boot_data()}
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def main():
    base_dir, port = get_base_dir(), get_free_port()
    threading.Thread(target=start_server, args=(port, base_dir), daemon=True).start()
    api = Api(os.path.join(get_data_dir(), 'database.sqlite'))
    api.window = webview.create_window('MUGHAL-E-AZAM - Restaurant', f'http://127.0.0.1:{port}/index.html', js_api=api, width=1280, height=800, resizable=True, min_size=(900, 600))
    webview.start()


if __name__ == '__main__':
    main()
