# BILL4PE update notes — September 2026

Implemented requested changes without changing the existing post-payment-verification workflow.

## Included
- First authenticated app access now requires a secure 4-digit Wallet PIN setup.
- Wallet PIN is bcrypt-hashed server-side and never returned by user/profile APIs.
- GPS captured in the bill-entry flow is now persisted into the generated expense receipt; Pay Now also makes a fallback GPS capture when needed.
- PDF heading defaults to `BILL4PE DIGITAL EXPENSE RECEIPT`.
- `Convenience Fee` wording changed to `Bill Generation Charges (@ X% of billed amount)` while retaining the existing server-side fee calculation.
- Added `Amount in Words` to the receipt totals section.
- Added the requested Bill4Pe disclaimer to every generated bill PDF.
- Existing payment receipt verification and the workflow after successful verification are unchanged.

## Main files changed
- `backend/routers/wallet.py`
- `backend/routers/auth.py`
- `backend/core/security.py`
- `backend/services/manual_flow_service.py`
- `backend/services/pdf.py`
- `frontend/src/App.js`
- `frontend/src/pages/app/WalletPinSetup.jsx`
- `frontend/src/pages/app/PayNow.jsx`
- billing/location display files listed in the source diff

## Validation performed
- Backend Python files compile successfully.
- Amount-in-words helper was checked with rupees + paise examples.
- A sample PDF was generated/rendered to verify the new title, GPS location, Bill Generation Charges row, Amount in Words, Grand Total and disclaimer layout.


## 08 Sep 2026 — Self Invoice + explicit bill-fee payment
- PDF header changed to `BILL4PE DIGITAL SELF INVOICE`.
- Disclaimer no longer uses the word `dispute`.
- Added more visual spacing between Subtotal and Bill Generation Charges in the PDF.
- Individual wallet fee payment now requires the user's existing 4-digit Wallet PIN before any debit/bill generation.
- Wrong/missing PIN does not debit the wallet and does not generate the bill.
- Bill Generation Charges can also be paid online through the existing Razorpay Checkout flow; successful server-side verification continues the existing bill generation flow.
- Wallet recharge remains via Razorpay and keeps quick/custom amount top-ups.
- Configure production/test credentials in `backend/.env` as `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` (plus webhook secret as already supported).
