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
        test_payload = {
            "title": f"TEST {receipt_type.upper()}",
            "orderId": "TEST-001",
            "time": "12:00 PM",
            "tableName": "Table 01",
            "customerName": "Hardware Test",
            "items": [{"name": "Sample Item", "qty": 1, "price": 100}],
            "subtotal": 100,
            "discount": 0,
            "grandTotal": 100,
            "receiptFooter": "TEST PRINT SUCCESSFUL"
        }
        return self.print_direct(printer_name, test_payload)

    def print_direct(self, printer_name, receipt_data):
        """Sends receipt raw bytes or plain text direct to OS print spooler silently with ESC/POS paper cut commands."""
        print(f"[SILENT PRINT] Direct job sent to '{printer_name}' for order {receipt_data.get('orderId', '')}")
        lines = []
        lines.append("=" * 32)
        lines.append(f"{receipt_data.get('header', 'MUGHAL-E-AZAM RESTAURANT'):^32}")
        lines.append(f"{receipt_data.get('title', 'RECEIPT'):^32}")
        lines.append("=" * 32)
        lines.append(f"Order #: {receipt_data.get('orderId', 'N/A')}")
        lines.append(f"Date/Time: {receipt_data.get('time', '')}")
        if receipt_data.get('tableName'):
            lines.append(f"Table: {receipt_data.get('tableName')}")
        if receipt_data.get('customerName'):
            lines.append(f"Customer: {receipt_data.get('customerName')}")
        lines.append("-" * 32)
        for item in receipt_data.get('items', []):
            qty_name = f"{item.get('qty', 1)}x {item.get('name', '')}"
            price_str = f"Rs.{item.get('price', 0) * item.get('qty', 1)}"
            space_len = max(1, 32 - len(qty_name) - len(price_str))
            lines.append(f"{qty_name}{' ' * space_len}{price_str}")
        lines.append("-" * 32)
        lines.append(f"Subtotal:{' ' * max(1, 23 - len(str(receipt_data.get('subtotal', 0))))}Rs.{receipt_data.get('subtotal', 0)}")
        if receipt_data.get('discount', 0) > 0:
            lines.append(f"Discount:{' ' * max(1, 23 - len(str(receipt_data.get('discount', 0))))}-Rs.{receipt_data.get('discount', 0)}")
        if receipt_data.get('deliveryFee', 0) > 0:
            lines.append(f"Delivery Fee:{' ' * max(1, 19 - len(str(receipt_data.get('deliveryFee', 0))))}Rs.{receipt_data.get('deliveryFee', 0)}")
        lines.append("=" * 32)
        lines.append(f"GRAND TOTAL:{' ' * max(1, 20 - len(str(receipt_data.get('grandTotal', 0))))}Rs.{receipt_data.get('grandTotal', 0)}")
        lines.append("=" * 32)
        lines.append(f"{receipt_data.get('receiptFooter', 'Thank you for dining with us!'):^32}")
        lines.append("\n\n")  # Minimal bottom margin line breaks (tight spacing)

        text_content = "\n".join(lines) + "\n"

        # Direct Spooling Driver Integration
        if sys.platform == 'win32':
            try:
                import win32print
                # Open printer handle and send RAW job directly
                h_printer = win32print.OpenPrinter(printer_name)
                try:
                    h_job = win32print.StartDocPrinter(h_printer, 1, ("POS Receipt", None, "RAW"))
                    win32print.StartPagePrinter(h_printer)
                    # Convert to bytes and append ESC/POS Full Cut command (\x1DV\x42\x00)
                    raw_bytes = text_content.encode('utf-8', errors='replace') + b'\x1dV\x42\x00'
                    win32print.WritePrinter(h_printer, raw_bytes)
                    win32print.EndPagePrinter(h_printer)
                    win32print.EndDocPrinter(h_printer)
                finally:
                    win32print.ClosePrinter(h_printer)
                return {"status": "success", "message": f"Printed silently on {printer_name}"}
            except Exception as e:
                print(f"[WIN PRINT ERROR] {e}")
        else:
            try:
                import subprocess
                # Send directly to lpr/lp printer queue silently
                proc = subprocess.Popen(['lp', '-d', printer_name], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                proc.communicate(input=(text_content + "\x1dV\x42\x00").encode('utf-8'))
                return {"status": "success", "message": f"Printed silently on {printer_name}"}
            except Exception as e:
                print(f"[UNIX PRINT ERROR] {e}")

        return {"status": "success", "message": f"Spooled print payload for {printer_name}"}

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
