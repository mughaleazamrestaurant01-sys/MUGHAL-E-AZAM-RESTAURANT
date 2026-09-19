import sys
import subprocess
import threading


class PrinterManager:
    @staticmethod
    def get_system_printers():
        """Return installed system print queues; physical-device discovery is driver/OS-owned."""
        res_container = []
        exc_container = []

        def enumerate_printers():
            try:
                if sys.platform == 'win32':
                    import win32print
                    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
                    res_container.append({'printers': [p[2] for p in win32print.EnumPrinters(flags)], 'error': ''})
                    return
                result = subprocess.run(['lpstat', '-e'], capture_output=True, text=True, check=False)
                if result.returncode:
                    res_container.append({'printers': [], 'error': result.stderr.strip() or 'The system print service did not return any printers.'})
                else:
                    res_container.append({'printers': [line.strip() for line in result.stdout.splitlines() if line.strip()], 'error': ''})
            except Exception as exc:
                exc_container.append(exc)

        t = threading.Thread(target=enumerate_printers, daemon=True)
        t.start()
        t.join(timeout=3.0)
        if t.is_alive():
            return {'printers': [], 'error': 'Printer discovery timed out after 3 seconds.'}
        if exc_container:
            return {'printers': [], 'error': f'Unable to read system printers: {exc_container[0]}'}
        return res_container[0] if res_container else {'printers': [], 'error': 'No response from printer service.'}

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

        res_container = []
        exc_container = []

        def execute_print():
            try:
                def money(value):
                    return f"Rs. {float(value or 0):.2f}"

                paper_width = receipt_data.get('paperWidth', '80mm')
                width = 32 if paper_width == '58mm' else 48
                is_kot = receipt_data.get('isKot', False)

                def center(value=''):
                    value = str(value or '')[:width]
                    return value.center(width)

                def wrapped(value, prefix=''):
                    value = str(value or '').strip()
                    if not value:
                        return []
                    available = max(1, width - len(prefix))
                    return [prefix + value[position:position + available] for position in range(0, len(value), available)]

                def centered(value):
                    return [center(part) for part in wrapped(value)]

                def line(left='', right=''):
                    left, right = str(left), str(right)
                    max_left = max(1, width - len(right) - 1)
                    left_str = left[:max_left]
                    spaces = max(1, width - len(left_str) - len(right))
                    return left_str + (' ' * spaces) + right

                if is_kot:
                    lines = [*centered('*** KITCHEN TICKET ***'), '=' * width]
                    if receipt_data.get('tableName'):
                        lines.extend([center(f"TABLE: {receipt_data['tableName']}"), '-' * width])
                    lines.append(f"KOT NO : {receipt_data.get('orderId', '')}")
                    if receipt_data.get('time'):
                        lines.append(f"TIME   : {receipt_data['time']}")
                    if receipt_data.get('serverName'):
                        lines.append(f"SERVER : {receipt_data['serverName']}")
                    if receipt_data.get('orderType'):
                        lines.append(f"TYPE   : {receipt_data['orderType']}")
                    lines.extend(['=' * width, line('ITEM DESCRIPTION', 'QTY'), '=' * width])
                    for item in receipt_data.get('items', []):
                        lines.append(line(str(item.get('name', '')).upper(), f"{item.get('qty', 0)}x"))
                        if item.get('notes'):
                            lines.append(f"  * NOTE: {item['notes']}")
                    lines.extend(['=' * width, *centered('[ END OF ORDER - COOK PROMPTLY ]')])
                else:
                    order_type = receipt_data.get('orderType', '')
                    is_preview = receipt_data.get('isPreview', False)
                    is_delivery = order_type == 'Delivery'
                    is_takeaway = order_type == 'Takeaway'
                    payment_method = receipt_data.get('paymentMethod', '')
                    lines = centered(receipt_data.get('restaurantName') or receipt_data.get('header') or 'MUGHAL-E-AZAM RESTAURANT')
                    lines.extend(centered(receipt_data.get('restaurantTagline')))
                    lines.extend(centered(receipt_data.get('restaurantAddress')))
                    if receipt_data.get('restaurantPhone'):
                        lines.extend(centered(f"TEL: {receipt_data['restaurantPhone']}"))
                    title = '*** PREVIEW CHECK (UNPAID) ***' if is_preview else (
                        '*** TAKEAWAY ORDER ***' if is_takeaway else (
                            '*** DELIVERY RECEIPT ***' if is_delivery else (
                                receipt_data.get('title') or '*** FINAL CASH RECEIPT ***'
                            )
                        )
                    )
                    lines.extend(['=' * width, *centered(title), '=' * width])
                    if is_takeaway:
                        lines.extend([*centered(f"TOKEN: #{receipt_data.get('orderId', '')}"), '-' * width])
                    lines.append(f"{'ORD NO' if is_delivery or is_takeaway else 'INV NO'} : {receipt_data.get('orderId', '')}")
                    if receipt_data.get('time'):
                        lines.append(f"DATE   : {receipt_data['time']}")
                    if receipt_data.get('tableName'):
                        lines.append(f"TABLE  : {receipt_data['tableName']}")
                    if is_takeaway:
                        if receipt_data.get('customerName'):
                            lines.append(f"CUST   : {receipt_data['customerName']}")
                        if receipt_data.get('customerPhone'):
                            lines.append(f"PHONE  : {receipt_data['customerPhone']}")
                        lines.append(f"STATUS : {'PAID (' + str(payment_method) + ')' if payment_method else 'UNPAID'}")
                    if is_delivery:
                        lines.append(f"PAYMENT: {payment_method or 'CASH ON DELIVERY'}")
                        lines.extend(['-' * width, 'CUSTOMER DETAILS:'])
                        if receipt_data.get('customerName'):
                            lines.append(f"NAME : {receipt_data['customerName']}")
                        if receipt_data.get('customerPhone'):
                            lines.append(f"TEL  : {receipt_data['customerPhone']}")
                        if receipt_data.get('customerAddress'):
                            lines.append('ADDR :')
                            lines.extend(wrapped(receipt_data['customerAddress']))
                    lines.extend(['-' * width, line('QTY DESCRIPTION', 'PRICE (RS.)'), '-' * width])
                    for item in receipt_data.get('items', []):
                        qty, name, price = item.get('qty', 0), item.get('name', ''), item.get('price', 0)
                        lines.append(line(f"{qty} x {name}", f"{float(qty or 0) * float(price or 0):.2f}"))
                    lines.append('-' * width)
                    lines.append(line('SUB TOTAL', f"{float(receipt_data.get('subtotal') or 0):.2f}"))
                    if float(receipt_data.get('discount') or 0):
                        lines.append(line('DISCOUNT', f"-{float(receipt_data.get('discount') or 0):.2f}"))
                    if float(receipt_data.get('deliveryFee') or 0):
                        lines.append(line('DELIVERY FEE', f"{float(receipt_data.get('deliveryFee') or 0):.2f}"))
                    total_label = 'EST. TOTAL' if is_preview else ('COLLECT CASH' if is_delivery and 'cash' in str(payment_method).lower() else 'TOTAL PAID')
                    lines.extend(['=' * width, line(total_label, money(receipt_data.get('grandTotal'))), '=' * width])
                    if is_preview:
                        closing = '* NO PAYMENT RECEIVED *\nPLEASE PRESENT TO CASHIER'
                    elif is_takeaway:
                        closing = '[ READY FOR COUNTER PICKUP ]\nTHANK YOU FOR ORDERING!'
                    elif is_delivery and 'cash' in str(payment_method).lower():
                        closing = '* CASH ON DELIVERY (COD) *\nDRIVER: PLEASE COLLECT EXACT AMOUNT'
                    else:
                        closing = receipt_data.get('receiptFooter') or 'THANK YOU FOR YOUR VISIT!\nPLEASE COME AGAIN'
                    for part in closing.split('\n'):
                        lines.extend(centered(part))

                text = '\n'.join(line for line in lines if line is not None) + '\n'
                cut_mode = receipt_data.get('cutMode', 'escpos_full')
                cut_commands = {
                    'star': b'\x1bi',
                    'star_full': None,
                    'star_raw_full': b'\x1bi',
                    'star_partial': b'\x1bm',
                    'escpos': b'\x1dV\x42\x00',
                    'escpos_full': b'\x1dV\x00',
                    'escpos_partial': b'\x1dV\x01',
                    'none': b'',
                }
                if cut_mode not in cut_commands:
                    res_container.append({'status': 'error', 'message': 'The selected printer cut profile is invalid.'})
                    return
                if cut_mode == 'star_full' and sys.platform == 'win32':
                    try:
                        self._print_with_windows_driver(printer_name, text)
                        res_container.append({'status': 'success', 'message': f'Print job sent to {printer_name} using the Windows Star driver.'})
                        return
                    except Exception as exc:
                        res_container.append({'status': 'error', 'message': f'Windows driver print failed: {exc}'})
                        return
                cut_command = (b'\n' * 5) + cut_commands[cut_mode]
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
                res_container.append({'status': 'success', 'message': f'Print job sent to {printer_name}.'})
            except Exception as exc:
                exc_container.append(exc)

        t = threading.Thread(target=execute_print, daemon=True)
        t.start()
        t.join(timeout=5.0)
        if t.is_alive():
            return {'status': 'error', 'message': f'Printing to {printer_name} timed out after 5 seconds.'}
        if exc_container:
            return {'status': 'error', 'message': f'Print failed: {exc_container[0]}'}
        return res_container[0] if res_container else {'status': 'error', 'message': 'No response from print driver.'}
