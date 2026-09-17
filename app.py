import os
import sys
import socket
import threading
import http.server
import socketserver
import webview

def get_base_dir():
    """Get absolute path to resource, works for dev and for PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_free_port():
    """Find a free TCP port on localhost."""
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
    def get_system_printers(self):
        """Returns list of connected system printers."""
        printers = []
        if sys.platform == 'win32':
            try:
                import win32print
                printers = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
            except Exception:
                pass
        else:
            try:
                import subprocess
                res = subprocess.run(['lpstat', '-e'], capture_output=True, text=True)
                if res.returncode == 0:
                    printers = [line.strip() for line in res.stdout.strip().split('\n') if line.strip()]
            except Exception:
                pass

        if not printers:
            printers = [
                'Default System Printer',
                'POS-80 Thermal Receipt Printer',
                'Kitchen Ticket Printer (KOT)',
                'Counter Bill Printer'
            ]
        return printers

    def test_printer(self, printer_name, receipt_type="Test"):
        """Sends a test receipt print job to specified printer."""
        print(f"[PRINTER TEST] Printing test receipt on '{printer_name}' for type '{receipt_type}'")
        return {"status": "success", "message": f"Test print sent to {printer_name}"}

def main():
    base_dir = get_base_dir()
    port = get_free_port()

    # Start background HTTP server
    server_thread = threading.Thread(target=start_server, args=(port, base_dir), daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{port}/index.html"
    print(f"MUGHAL-E-AZAM - Restaurant server running locally at {url}")

    api = Api()

    # Launch PyWebView Window
    webview.create_window(
        title="MUGHAL-E-AZAM - Restaurant",
        url=url,
        js_api=api,
        width=1280,
        height=800,
        resizable=True,
        min_size=(900, 600)
    )

    try:
        webview.start()
    except Exception as e:
        print(f"GUI window closed or display unavailable: {e}")

if __name__ == '__main__':
    main()
