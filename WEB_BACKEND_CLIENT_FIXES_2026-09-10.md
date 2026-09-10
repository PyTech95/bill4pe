# BILL4PE Web + Backend — Client Feedback Fixes (2026-09-10)

This package is the WEB/BACKEND release baseline. Android/iOS native-layer changes are intentionally not part of this release; create the app copy from this exact baseline when requested.

## Client issues fixed
- Voice expense capture: browser speech recognition runs alongside recorded audio; transcript is preserved as a fallback and parsed server-side.
- Product/photo identification: phone images are EXIF-rotated/resized; category detection has a second general-product pass; products may be identified even when price is not visible (price starts at 0 for review).
- Payment/UTR recovery: verified merchant payments and paid Bill Generation Charges are protected. Generation failures become retryable and do not tell the user to discard/pay again.
- Discard/cancel hardening: verified/fee-paid/generated transactions cannot be cancelled through legacy cancel/discard endpoints.
- Corporate employee access: unique 6-digit employee code + 6-digit PIN, both numeric; PIN remains hashed.
- Real OTP path: live OTP provider support remains available through OTP_MODE=live; demo OTP is for explicit development mode only.
- Receipt images: new payment proof files remain MongoDB-backed.

## Configurable Bill Generation Charges
Super Admin > Settings now exposes separate percentages for:
- Individual users
- Corporate users / employees

Corporate administrators and employees use the corporate percentage. For a non-zero corporate rate, the charge is deducted from the central company wallet. A 0% setting waives the charge. The percentage is snapshotted when a billing attempt starts, so later admin changes do not mutate an in-progress transaction.

## Company wallet
Company administrators can recharge the company wallet through Razorpay using the existing payment reconciliation engine. Employees cannot recharge it directly.

## Deployment
After pushing this project to GitHub, pull it on the server, install backend requirements/frontend packages, build the frontend, then restart the running backend process and reload the web server. Keep the production `.env` files on the server; do not commit secrets.

## Additional production hardening
Authenticated Razorpay verification endpoints now confirm the current BILL4PE user owns the internal payment order before reconciliation. This prevents one signed-in user from attempting to reconcile another user's known order ID.
