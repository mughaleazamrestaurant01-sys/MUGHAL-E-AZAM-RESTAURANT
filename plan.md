# POS hardening and completion plan

## Completed

1. Consolidated the desktop POS onto the active `index.html` entry point and removed the stale duplicate page.
2. Added SQLite-backed application-state persistence for orders, tables, KDS tickets, carts, customer details, and order numbering.
3. Implemented recipe inventory validation and deduction at paid-order completion.
4. Replaced browser-side plaintext authentication with PBKDF2-hashed credentials and bridge-side authentication.
5. Added detailed native thermal receipt/KOT rendering and accurate printer setup guidance.
6. Added first-run administrator setup, durable user-account safeguards, boot locking, and visible feedback messages.
7. Added JSON backup coverage for operational state and surfaced backup/import errors.
8. Validated Python compilation, inline JavaScript syntax, state/authentication flows, receipt rendering, and diff whitespace.

## Operational notes

- The printer setup tab lists **installed operating-system print queues**. A physically connected printer appears only after its driver/queue is available to Windows or CUPS.
- Receipt payloads now end directly after the footer with one newline. The printer model and driver still control any unavoidable minimum feed required before cutting.

# Need a quick and deep review

High-confidence dummy / incomplete functionality
Thermal receipt and KOT printing are effectively dummy.

The Vue UI builds a complete printable receipt with line items, totals, delivery fee, and configured header/footer. 

However, the Python printer bridge sends only a title, order ID, and blank lines to the printer. It never reads items, totals, customer/table fields, header, or footer from receipt_data. 

Therefore, “Complete Paid Order & Print Receipt,” KOT printing, reprinting, receipt branding, and printed bill details are misleading: a real printer receives an almost empty slip rather than the detailed receipt displayed in the HTML.

“Recipe Deduction” is not implemented.

The inventory screen explicitly calls itself “Kitchen Raw Stock & Recipe Deduction.” 

A recipe editor exists and adds ingredient/quantity entries to dishes. 

But submitting an order only adds a ticket to kdsOrders, optionally prints it, and saves state; it never iterates over dish recipes or decreases ingredient quantities. 

Completing payment also writes the order history and clears the cart without changing inventory. 

Conclusion: recipe setup is currently stored configuration only; stock deduction is a dummy claim.

Table management is not persisted.

The application starts with four hard-coded sample/default tables (Table 01–Table 04). 

Users can add, rename, delete, select, and release tables in memory. 

But the SQLite state payload does not save tables; it only saves orders, purchases, customers, inventory, menu, categories, expenses, opening cash, and printer configuration. 

After restart, table edits are lost and the original four tables return. This makes the “Dining Table Layout & Management” feature only temporarily functional. 

Kitchen Display System state is temporary and can look “live” without being durable.

The KDS interface advertises “Live kitchen queue order management.” 

Tickets are held only in kdsOrders, and the status button merely changes Pending to Preparing or removes the ticket. 

kdsOrders is excluded from the persisted-state payload. 

A restart loses all active kitchen tickets and statuses. It works as a same-session demo queue, but not as a production kitchen workflow.

Order numbers are not persisted, so duplicate invoices are possible after restart.

The current order starts at the hard-coded value '1001'. 

It increments only in browser memory after payment. 

currentOrderId is not included in the state saved to SQLite. 

Every restart can resume at 1001, even while historical receipts already use those IDs. That makes the order/invoice numbering feature unreliable.

The JSON backup’s UI claim is inaccurate.

The backup screen says the JSON export includes “all menu items, inventory, transactions, customers & users.” 

The exported object does not include users; it also omits purchaseHistory, tables, KDS tickets, and the next order number. 

Native SQLite folder backup does preserve the database, including users, because it copies the SQLite database itself. 

So the folder/database backup is real; the JSON backup is partial and its “users” promise is dummy/incorrect.

Dead or stale code
MUGHAL-E-AZAM RESTAURANT.html is a stale duplicate and is not the application screen.

The desktop application explicitly serves index.html. 

The Windows build workflow packages index.html and the assets directory, not the duplicate HTML file. 

The duplicate file differs from the active file—for example, it lacks the boot lock and uses older local-storage-style initialization. The active index.html has different persistent-boot behavior. 

This file appears to be an old prototype/copy. It is dead code in the shipped desktop path and could confuse future maintenance.

startBoot() is unused, while its intended safety behavior is bypassed.

startBoot() correctly waits for the pywebviewready event before loading saved data, and it has an error path that keeps the UI locked. 

But Vue’s actual mounted() hook calls loadPersistentData() immediately and sets bootReady = true afterwards. 

loadPersistentData() silently returns if the desktop API is not available. 

This leaves startBoot() as unused code and means the “Never show unrestricted POS content until the desktop database bridge has answered” promise may not hold during bridge timing failures. 

All toast notifications are deliberately non-functional.

Numerous actions call showToast()—for example adding items, queueing orders, saving data, and handling printer errors. 

The method body intentionally does nothing. 

If this was a product decision, it is intentional; otherwise it makes success/error feedback appear dummy because the UI says nothing actually happens.

Not dummy, but important production concerns
Authentication is not secure. Passwords are stored and returned in plaintext in SQLite.  The login compares plaintext values in the browser. 

First-run access is unrestricted. If there are no users, all permissions are granted.  This may be intended for setup, but there is no forced initial administrator-creation flow.

CSV import is basic and not robust for all valid CSV files. The parser toggles quote mode but does not handle escaped quotes ("") or embedded newlines.  It is usable for simple files, not fully dummy.

The build workflow installs requests, but the application does not import or use it. The workflow’s dependency list includes it.  This is harmless unused build baggage.
