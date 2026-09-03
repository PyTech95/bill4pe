# BILL4PE — PRD & Working Log

## Product
BILL4PE turns UPI payments into corporate reimbursement invoices. User pays a merchant
directly in their own UPI app, uploads the payment receipt, the system auto-reads and
verifies it, and generates a GST-style bill. Revenue = configurable per-bill fee.

## Stack
- Frontend: React (CRA + craco, Tailwind, shadcn/ui) — /app/frontend
- Backend: FastAPI (routers/ + core/ + services/) — /app/backend, entry server.py
- DB: MongoDB (MONGO_URL/DB_NAME from backend/.env)
- AI: Gemini via EMERGENT_LLM_KEY proxy (models pinned to gemini-2.5-flash in .env —
  the "-latest" aliases are NOT supported by the Emergent proxy); GEMINI_API_KEY direct
  on VPS.
- Payments: Razorpay DISABLED on staging (no keys). PAYMENT_FLOW_MODE=manual_upi_double_scan,
  ALLOW_MOCK_RECHARGE=true. Super admin: meland@mhem.in (see test_credentials.md).

## Deployed environment
- Code from founder's bill4pe-main.zip installed into /app (2026-09-03), replacing the
  placeholder scaffold (scaffold preserved in git commit "scaffold billing app…").
- Preview URL: https://invoice-staging-2.preview.emergentagent.com

## Implemented (2026-09-03) — Receipt-first payment verification overhaul
- REMOVED merchant-QR payment flow from UI: PayNow step 1 is now a payee form
  (name + UPI ID [+ amount when no draft]); QrScanner/jsQR/manual-UPI-entry deleted.
  Landing/Terms/TravelSubCategory merchant-QR copy updated. Bill-authenticity QR
  (Verify.jsx) intentionally untouched.
- REMOVED manual UTR / last-4 entry: proof endpoint accepts ONLY a receipt screenshot
  (screenshot File required; extra form fields ignored → 422 without file).
- NEW services/receipt_verify.py: image validation (type/size/PIL corruption/EXIF
  orientation/downscale), Gemini full-receipt extraction (status, amount, UTR, txn id,
  date/time, payee/payer names+UPIs, bank, provider, extra ref) → structured record.
- Server-side verification: success-status check, Decimal-paise exact amount match vs
  frozen bill amount, normalized+masked-aware receiver UPI match, duplicate UTR/txn-id
  (unique partial indexes on receipt_verifications + cross-check manual_transactions).
- Approval rule: verified ONLY when status=success AND amount matched AND receiver not
  mismatched AND reference present AND not duplicate → else rejected / review_required.
  generate_receipt gated on verified|admin_reviewed. Bill amount never overwritten.
- PayNow.jsx: read-only verification result card (per-check ✅/❌ + final banner),
  re-upload on failure, corporate auto-generate only after verified.
- DB: receipt_verifications collection stores all fields + ocr_raw_data + timestamps.
- Verified via live curl suite T1–T7 (clean/mismatch/failed/wrong-payee/duplicate/
  manual-UTR-422/generate-gating) — all pass; Gemini reads PhonePe/Paytm/GPay formats.

## Backlog
- P0: production deploy (user confirmed-free deployment pending), Razorpay keys → live fee
- P1: email delivery (Resend), superadmin review queue UI for review_required receipts
- P2: payout (RazorpayX) collect-and-settle model, mobile builds (capacitor dirs excluded)
