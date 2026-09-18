# POS hardening and completion plan

## Review status: single-computer POS completed; shared two-computer POS not yet built

This document was reviewed against the active desktop entry point (`index.html`) and
the native Python bridge (`app.py`). The stale observations in the previous version
have been replaced with the current implementation status.

## Delivered functionality

1. **One active application path.** The desktop application serves `index.html` and
   packages that file plus `assets/`. There is no second shipped HTML screen to
   maintain.
2. **Durable POS state.** SQLite persists menu items, inventory, recipes, orders,
   purchases, customers, tables, KDS tickets, carts, selected tables, printer
   configuration, the next order number, discounts, payment details, and unfinished
   customer/delivery fields. A watched, debounced save covers values changed directly
   in the screen, so they do not depend on a separate Save button. Reloading restores
   unfinished work and active kitchen tickets.
3. **Reliable order numbering.** The current order number is saved with the rest of
   the state, so normal application restarts do not return invoice numbering to
   `1001`.
4. **Recipe stock control.** Paid orders validate every recipe ingredient before
   completion. They are rejected when an ingredient is missing or stock is too low;
   otherwise the required quantities are deducted and persisted.
5. **Native receipt and KOT output.** The bridge renders configured receipt header
   and footer, order details, customer/table details, all line items, subtotal,
   discount, delivery fee, and total as raw thermal-printer text. Receipt printing,
   KOT printing, provisional bills, and historical reprints all use that payload.
6. **Account security and setup.** Passwords use PBKDF2 hashes, authentication is
   performed by the native bridge, and only non-sensitive user fields reach the UI.
   A new installation remains locked until its first administrator account is
   created. The last user cannot be deleted, and the last administrator cannot be
   deleted or demoted. The interface now uses the selected permission checkboxes to
   hide protected tabs/actions and rejects direct in-app attempts to use protected
   menu, inventory, table, KDS, or recipe-management actions.
7. **Safe startup and feedback.** The UI waits for the pywebview bridge before it
   reads data or unlocks the POS. Startup failures keep the application locked and
   display an error. Toast messages give users success and error feedback.
8. **Backups and restore.** Selecting a custom folder immediately creates a
   consistent SQLite backup there and stores that folder for future automatic
   backups. The Backup page also has an explicit **Create Backup Now** button and
   shows the saved file path or any backup error. Native backups include users; JSON
   export/import covers operational business state (but not user accounts). Restore
   validates a SQLite backup before replacing the live database.
9. **Payment validation.** Cash orders cannot be completed until cash received is
   at least the payable total. This prevents recording an underpaid cash sale.

## Validation completed

- Python source compilation and AST parsing succeeded.
- The inline Vue application script passed JavaScript syntax validation.
- Isolated SQLite tests verified administrator creation, password authentication,
  prevention of the final-administrator demotion/deletion, and deletion once a
  second administrator exists.
- State persistence and custom-folder backup were tested with a temporary SQLite
  database, including reopening the resulting backup and checking saved cart and
  discount data.
- Permission-gate checks verified that menu management requires `menu_manage` (not
  merely `pos`) and that protected action methods have an explicit permission guard.
- A whitespace check found no patch errors.

## Confirmed restaurant setup and requirements

The requested installation is a **two-computer shared POS** on an existing wired
Ethernet LAN. Mobile ordering is deliberately out of scope for now.

| Device | Operating system | Required use | Local receipt printer |
| --- | --- | --- | --- |
| Main counter PC | Windows 10 | Runs all day; central server, dine-in/counter POS, administration, reports | Star TSP700II / TSP743II (USB) |
| Evening laptop | Windows 11 | Takeaway and delivery POS from 6 PM to 11 PM | SRP-352 Plus (USB) |
| Kitchen printer | Network-connected | Prints KOT only after the user clicks **Kitchen KOT** | XSP-210 (LAN; reserved IP `192.168.10.220`) |

Both computers and the kitchen printer are already connected to the same router by
Ethernet. The administrator will create the laptop user's account and choose its
permissions inside the POS.

### Required shared behaviour

1. Both computers must read and write one shared set of users, menu, recipes,
   stock, customers, orders, invoices, reports, KDS tickets, and tables.
2. A table made busy on either computer must become busy on the other computer
   promptly, before it can be selected for another order.
3. A takeaway/delivery order entered on the laptop must promptly appear on the main
   counter PC, including sales, customer, inventory, and history data.
4. The main PC prints customer receipts only to its Star USB printer; the laptop
   prints customer receipts only to its SRP-352 Plus USB printer.
5. Both PCs must be able to send a KOT to the same kitchen network printer, but
   only after the operator explicitly clicks the **Kitchen KOT** button. Completing
   payment and printing a provisional bill must not create a KOT.
6. The main counter PC must stay powered on while the laptop is in use. Internet is
   not required for this local-LAN system.

## Shared two-computer feature: current progress

**Implementation progress: basic shared mode is implemented.** The main counter can
serve its own local SQLite database through an authenticated LAN HTTP gateway, and
the laptop can use that gateway instead of creating a second operational database.
Both PCs therefore use the counter PC's users, menu, stock, orders, tables, KDS
queue, reports, and customers. Receipt/KOT printer discovery and printing remain
local to each PC.

Run the main counter application with `--share-lan --server-token <long-secret>`.
Run the laptop with `--server-url http://<counter-LAN-IP>:8765 --server-token
<same-long-secret>`. Permit inbound TCP 8765 only from the restaurant LAN in the
counter PC's Windows Firewall. The token must be a long private value and must not
be reused outside this restaurant. Do not share the SQLite file through a Windows
folder or network drive: SQLite over a network share is not safe for simultaneous
POS use.

### Build plan before the laptop is connected

1. **Central server and database:** run a proper server service on the main counter
   PC and move shared operational data to PostgreSQL (recommended) or another
   supported network database. The service must bind only to the restaurant LAN and
   require authenticated requests.
2. **Desktop client mode:** make both POS installations connect to that server rather
   than opening their own local SQLite operational database. Keep each PC's printer
   selection local to that PC.
3. **Safe transactions:** make order creation, recipe deduction, invoice numbering,
   table status, KDS changes, and user edits atomic on the server so two operators
   cannot overwrite each other or sell the same stock twice.
4. **Live synchronisation:** add server-driven updates or short safe polling so the
   other screen sees table/KDS/order changes promptly. Include reconnect and offline
   messages; do not silently save an offline laptop order to a different local
   database.
5. **Kitchen printer installation:** reserve a fixed DHCP address for the XSP-210 in
   the router, install its Windows network/TCP-IP queue on both PCs, then select
   that queue as the kitchen printer on each PC. Use its confirmed reserved IP
   `192.168.10.220` and the XSP-210 driver when creating the TCP/IP queue on both PCs.
6. **End-to-end acceptance test:** use both PCs at the same time to test busy-table
   blocking, laptop delivery orders, KOT-only printing from each PC, each local
   receipt printer, stock deduction, simultaneous saves, restart/reconnect, backup,
   and recovery.

## Remaining operational considerations

These are not placeholder or dummy features, but are sensible future enhancements:

1. **CSV parser scope.** CSV import is designed for simple one-line records. It
   does not yet fully support escaped quotation marks or multiline quoted fields.
2. **Printing depends on operating-system setup.** The app lists installed Windows
   or CUPS queues. A physical printer must have an installed driver/queue before it
   can be selected, and printer hardware/driver settings determine any required
   post-receipt paper feed.
3. **JSON backups intentionally exclude accounts.** Use the native SQLite folder
   backup whenever user accounts must be moved or recovered too.
4. **Shared-POS dependency.** The two-computer feature must be built and tested
   before the laptop is used as a live second terminal. Until then, it remains a
   separate local POS installation and must not be treated as synchronized.

## Maintainer attention for future chats

Treat all single-computer functionality above as complete unless a reproducible bug
is reported. The only planned product work requiring major development is the shared
two-computer/server feature described in this document. Before starting that work,
confirm the kitchen printer's fixed LAN IP address and agree on the server database
and installation process. Do not claim that the two PCs are synchronized, and do not
use a network-shared SQLite file as a shortcut. When adding a new screen or action,
assign it to an existing permission and enforce that permission both in the visible
UI and in its action method.

## 2026-09-18 reliability work in progress

- The reported generic “Unable to save POS data” notification is being addressed by
  returning a concrete SQLite/serialization error from the bridge instead of letting
  an exception become an opaque failed webview call.
- Automatic folder backups are now rate-limited to once per minute. The previous
  implementation made a full SQLite backup after every persisted UI update, which
  could block the POS noticeably as order history grew. Explicit backup creation and
  the first backup after choosing a folder remain immediate.
- The shared two-computer feature is being implemented as an authenticated LAN API;
  it will keep receipt-printer configuration local on each Windows computer while
  operational POS data is owned by the main counter computer. A Windows network
  share of SQLite remains unsupported.
- A first usable LAN implementation is now present: start the counter application
  with `--share-lan --server-token <long-secret>` and start the laptop with
  `--server-url http://<counter-LAN-IP>:8765 --server-token <same-long-secret>`.
  The laptop reads/writes the counter's database over an authenticated HTTP bridge,
  while printer discovery and printing still occur on the laptop itself. The
  implementation serializes database writes but is not yet a replacement for
  purpose-built per-order transactional APIs; operators must not edit the same
  unfinished order simultaneously.
- Printer configuration is intentionally terminal-local: it is stored in each
  installation's settings database and excluded from the shared operational state,
  so laptop receipt/KOT choices cannot replace the counter PC's printer queues.
- Save requests are now coalesced in the UI (700 ms debounce) rather than being
  sent both by every action and by the deep state watcher. Automatic backup work
  also runs after the SQLite write on a background thread, so a large backup cannot
  hold the POS screen while it is saving an order.
- The state bridge rejects malformed payloads with a descriptive result and the UI
  displays a rejected bridge error message, making the next on-site failure
  diagnosable rather than showing only the generic save toast.
- The coalescing delay is set to 700 ms: frequent cart quantity changes and delivery
  field edits are persisted as one final snapshot after the operator pauses, while
  all normal order changes remain automatically saved.
- Startup now unlocks the POS as soon as saved data is available. Printer enumeration
  proceeds in the background because Windows can pause while probing unavailable
  network printers; a printer scan no longer keeps the entire application on its
  opening screen.
