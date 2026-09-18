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
| Kitchen printer | Network-connected | Prints KOT only after the user clicks **Kitchen KOT** | XSP-210 (LAN; confirmed IP `192.168.10.220`) |

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

**Implementation progress: 0% of the shared two-computer feature.** The current
application is a local desktop POS only. Each installation selects its own data
directory and opens its own `database.sqlite`, so the main PC and laptop currently
have separate data and cannot show each other's tables, orders, stock, or users.

Some existing local features can be reused later (accounts, printer selection, KOT
button, receipts, inventory, and local backups), but they do **not** provide network
sharing. In particular, the current Python bridge is exposed only to its own local
desktop window and starts an HTTP server on `127.0.0.1`; it is not a LAN API server.
Do not share the current SQLite database file through a Windows folder or network
drive: SQLite over a network share is not a safe solution for simultaneous POS use.

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
   that queue as the kitchen printer on each PC. Its confirmed address is
   `192.168.10.220`; reserve that address in the router so it does not change.
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
reserve the confirmed kitchen-printer IP address (`192.168.10.220`) and agree on the
server database and installation process. Do not claim that the two PCs are
synchronized, and do not use a network-shared SQLite file as a shortcut. When adding
a new screen or action, assign it to an existing permission and enforce that
permission both in the visible UI and in its action method.

## Printer build requirement

The Windows printer error **`No module named 'win32print'`** was caused by the
packaged EXE not including the Windows `pywin32` printer module. The Windows build
workflow now installs `pywin32` and explicitly includes `win32print` and `pywintypes`
in the EXE. A newly built EXE is required on both POS computers; the already-installed
EXE will continue to show that error until it is replaced.
