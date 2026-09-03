# bill4pe — PRD

## Original Problem Statement
Deploy/harden "bill4pe", a billing/invoicing web app for Indian small businesses (UPI/PhonePe-style payments). Plan assumed an existing zip to validate — **no zip was provided**, so the app was built from scratch per the spec: invoices, customer records (PII/GST), payments, auth + role separation, hardened config (secrets in env, locked CORS).

## Decisions (user skipped clarification → best judgment)
- Payments: manual recording + UPI deep-link/QR (no live gateway → no payment secrets at risk). Stripe/Razorpay gateway is a backlog item.
- DB: MongoDB. Auth: JWT httpOnly cookies (custom email/password) with roles.
- Admin/owner account: meland@mhem.in (see /app/memory/test_credentials.md).

## User Personas
- Admin/Owner (meland@mhem.in): full access to own business workspace.
- Staff (role=staff): registered users managing their own billing workspace.

## Architecture
- Backend: /app/backend/server.py (FastAPI, single module) — /api/auth (register/login/logout/me/refresh/forgot/reset, bcrypt, JWT cookies, 5-attempt/15-min lockout, admin seed), /api/settings, /api/customers CRUD (with outstanding aggregation), /api/invoices CRUD + /send + /payments (idempotent on reference → 409), /api/dashboard/stats. Server-side GST totals (CGST/SGST vs IGST). CORS locked to FRONTEND_URL + localhost.
- Frontend: /app/frontend/src — pages: Login, Register, Dashboard (KPIs, 6-mo recharts area chart, recent invoices, top customers), Invoices (search + status tabs), InvoiceBuilder (line items, GST slabs, discount, live totals, UPI QR preview), InvoiceDetail (print sheet, UPI QR/copy-link, payment modal, WhatsApp share), Customers (cards + modal CRUD), Settings. Context: AuthContext; lib: api.js (axios + 401 refresh interceptor), format.js (INR en-IN, UPI link, GST totals). Design per /app/design_guidelines.json (Outfit/Plus Jakarta Sans/JetBrains Mono, #5E35B1 brand, dark slate sidebar).

## Implemented (2026-09-03)
- Full auth (admin seeded, lockout, refresh tokens, forgot/reset via console-logged link)
- Customers with outstanding balances; Invoices with GST math, statuses (draft/pending/paid/overdue auto), auto numbering (INV-0001…)
- Payment recording (partial/full, modes, duplicate-reference idempotency), UPI QR + payment links
- Dashboard stats; Settings (business profile, UPI ID, bank, prefix, terms); print-ready invoice
- Testing: 16/16 backend pytest + full Playwright pass (/app/test_reports/iteration_1.json)
- Sample data present: customer "Sharma Textiles", INV-0001 (overdue, ₹5,610 due), INV-0002 (paid ₹7,610)

## Backlog
- P0 (before real money): payment gateway (Stripe/Razorpay) with webhook signature verification + reconciliation; go-live deploy to production URL
- P1: invoice PDF export (server-side), email/WhatsApp invoice send, password-reset email delivery (Resend), admin view across users
- P2: CSV export, recurring invoices, inventory/items catalog, e-invoicing (IRN) compliance

## Next Tasks
1. Deploy to preview → smoke test → promote (payment gateway integration when keys chosen)
2. Split server.py into routers as features grow
