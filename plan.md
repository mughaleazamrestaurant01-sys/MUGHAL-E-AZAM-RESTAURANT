# POS hardening and completion plan

## Review status: completed

This document was reviewed against the active desktop entry point (`index.html`) and
the native Python bridge (`app.py`). The stale observations in the previous version
have been replaced with the current implementation status.

## Delivered functionality

1. **One active application path.** The desktop application serves `index.html` and
   packages that file plus `assets/`. There is no second shipped HTML screen to
   maintain.
2. **Durable POS state.** SQLite persists menu items, inventory, recipes, orders,
   purchases, customers, tables, KDS tickets, carts, selected tables, printer
   configuration, and the next order number. Reloading restores unfinished work and
   active kitchen tickets.
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
   deleted or demoted.
7. **Safe startup and feedback.** The UI waits for the pywebview bridge before it
   reads data or unlocks the POS. Startup failures keep the application locked and
   display an error. Toast messages give users success and error feedback.
8. **Backups and restore.** Native folder backup creates a consistent SQLite copy,
   including users. JSON export/import covers operational business state (but not
   user accounts); the UI now states that distinction clearly. Restore validates a
   SQLite backup before replacing the live database.
9. **Payment validation.** Cash orders cannot be completed until cash received is
   at least the payable total. This prevents recording an underpaid cash sale.

## Validation completed

- Python source compilation and AST parsing succeeded.
- The inline Vue application script passed JavaScript syntax validation.
- Isolated SQLite tests verified administrator creation, password authentication,
  prevention of the final-administrator demotion/deletion, and deletion once a
  second administrator exists.
- A whitespace check found no patch errors.

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
4. **Single-terminal design.** State is stored in one local SQLite database. A
   multi-terminal restaurant deployment would need a shared server, transactional
   concurrency controls, and role authorization enforced at that server boundary.
