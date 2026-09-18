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
