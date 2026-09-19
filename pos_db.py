import json
import os
import hashlib
import hmac
import secrets
import shutil
import sqlite3
import tempfile
import threading
import time


def get_base_dir():
    import sys
    return getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_data_dir():
    """Keep operational data outside a PyInstaller bundle and uninstall folder."""
    import sys
    root = os.environ.get('APPDATA') if sys.platform == 'win32' else os.path.expanduser('~/.local/share')
    path = os.path.join(root or os.path.expanduser('~'), 'MughalEAzamPOS')
    os.makedirs(path, exist_ok=True)
    return path


class DatabaseManager:
    def __init__(self, database_path):
        self.database_path = database_path
        self.window = None
        self._database_lock = threading.RLock()
        self._last_automatic_backup = 0.0
        self._backup_in_progress = False
        self._initialize_database()

    def _connection(self):
        connection = sqlite3.connect(self.database_path, timeout=3)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA busy_timeout = 3000')
        connection.execute('PRAGMA temp_store = MEMORY')
        connection.execute('PRAGMA cache_size = -8000')
        return connection

    def _initialize_database(self):
        with self._connection() as db:
            if db.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'wal':
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
                return hmac.compare_digest(DatabaseManager._hash_password(password, salt), stored)
            except (TypeError, ValueError):
                return False
        return hmac.compare_digest(password, stored)

    @staticmethod
    def _public_user(row):
        return {'id': row['id'], 'name': row['name'], 'username': row['username'], 'role': row['role'], 'permissions': json.loads(row['permissions'])}

    def _create_database_backup(self, directory):
        try:
            os.makedirs(directory, exist_ok=True)
            destination = os.path.join(directory, 'pos_backup_latest.sqlite')
            temporary = f'{destination}.tmp'
            with self._connection() as source, sqlite3.connect(temporary, timeout=10) as target:
                source.backup(target)
            os.replace(temporary, destination)
            return {'ok': True, 'path': destination}
        except Exception as exc:
            if 'temporary' in locals() and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except Exception:
                    pass
            return {'ok': False, 'error': f'Backup failed: {exc}'}

    def _backup_after_write(self):
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

    def get_boot_data(self): return {'users': self.list_users(), 'state': self.load_state()}

    def list_users(self):
        with self._connection() as db:
            return [self._public_user(r) for r in db.execute('SELECT id, name, username, password, role, permissions FROM users ORDER BY id').fetchall()]

    def authenticate(self, username, password):
        username, password = (username or '').strip(), password or ''
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
                    if not existing: return {'ok': False, 'error': 'The requested user account was not found.'}
                    if existing['role'] == 'Admin' and user.get('role', 'Cashier') != 'Admin':
                        if db.execute("SELECT COUNT(*) FROM users WHERE role = 'Admin'").fetchone()[0] <= 1:
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
            if db.execute('SELECT COUNT(*) FROM users').fetchone()[0] <= 1:
                return {'ok': False, 'error': 'The last user account cannot be deleted.'}
            user = db.execute('SELECT role FROM users WHERE id = ?', (user_id,)).fetchone()
            if not user: return {'ok': False, 'error': 'The requested user account was not found.'}
            if user['role'] == 'Admin' and db.execute("SELECT COUNT(*) FROM users WHERE role = 'Admin'").fetchone()[0] <= 1:
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
        try:
            if not isinstance(state, dict): return {'ok': False, 'error': 'POS data payload is invalid; expected an object.'}
            encoded = json.dumps({k: v for k, v in state.items() if k != 'users'}, ensure_ascii=False, separators=(',', ':'))
            with self._database_lock, self._connection() as db:
                db.execute("INSERT INTO application_state(key, value) VALUES ('pos_state', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (encoded,))
            return {'ok': True, 'backupError': self._backup_after_write().get('error', '')}
        except (TypeError, ValueError) as exc: return {'ok': False, 'error': f'POS data cannot be encoded: {exc}'}
        except sqlite3.Error as exc: return {'ok': False, 'error': f'POS database write failed: {exc}'}
        except Exception as exc: return {'ok': False, 'error': f'POS data save failed: {exc}'}

    def get_printer_config(self):
        with self._connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'printer_config'").fetchone()
        try: return json.loads(row['value']) if row else {}
        except (TypeError, ValueError): return {}

    def save_printer_config(self, config):
        try:
            with self._connection() as db:
                db.execute("INSERT INTO settings(key, value) VALUES ('printer_config', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(config),))
            return {'ok': True}
        except (TypeError, ValueError, sqlite3.Error) as exc: return {'ok': False, 'error': f'Printer settings save failed: {exc}'}

    def select_backup_folder(self):
        import webview
        selected = self.window.create_file_dialog(webview.FOLDER_DIALOG) if self.window else None
        if not selected: return {'ok': False, 'cancelled': True}
        directory = selected[0] if isinstance(selected, (list, tuple)) else selected
        with self._connection() as db:
            db.execute("INSERT INTO settings(key, value) VALUES ('backup_directory', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (directory,))
        backup = self._create_database_backup(directory)
        return backup if not backup['ok'] else {'ok': True, 'directory': directory, 'path': backup['path']}

    def create_backup_now(self):
        directory = self.get_backup_directory()
        return self._create_database_backup(directory) if directory else {'ok': False, 'error': 'Select a custom backup folder first.'}

    def get_backup_directory(self):
        with self._connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'backup_directory'").fetchone()
        return row['value'] if row else ''

    def restore_from_directory(self):
        import webview
        selected = self.window.create_file_dialog(webview.FOLDER_DIALOG) if self.window else None
        if not selected: return {'ok': False, 'cancelled': True}
        directory = selected[0] if isinstance(selected, (list, tuple)) else selected
        source = os.path.join(directory, 'pos_backup_latest.sqlite')
        if not os.path.isfile(source): return {'ok': False, 'error': 'pos_backup_latest.sqlite was not found in the selected folder.'}
        fd, temporary = tempfile.mkstemp(dir=os.path.dirname(self.database_path), suffix='.sqlite')
        os.close(fd)
        try:
            shutil.copy2(source, temporary)
            with sqlite3.connect(temporary) as candidate:
                if candidate.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    return {'ok': False, 'error': 'The selected backup database failed its integrity check.'}
                candidate.execute('SELECT 1 FROM users LIMIT 1')
            os.replace(temporary, self.database_path)
            return {'ok': True, 'boot': self.get_boot_data()}
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
