# BILL4PE Payment Proof Storage — MongoDB

New PhonePe / Paytm / GPay / UPI receipt screenshots are stored in MongoDB collection `payment_proofs`.
The application no longer writes new receipt screenshots to `backend/private_uploads/payment_proofs`.

## First deployment from an older version

Do **not** delete the old `backend/private_uploads/payment_proofs` folder before the first backend start.
On startup, BILL4PE automatically copies any legacy proof files referenced by `manual_transactions.proof_file`
into MongoDB and replaces those references with `proof_db_id`.

After you confirm the migration log shows no missing/skipped proofs and you have a MongoDB backup, the old
filesystem folder can be archived/removed. Future code deployments will not affect payment receipt images.

## MongoDB collections

- `payment_proofs`: original image bytes + filename/content type/transaction/user metadata
- `manual_transactions`: stores `proof_db_id` and proof metadata only
- `receipt_verifications`: stores `receipt_db_id` and OCR/verification fields only

The existing authenticated `/api/manual-pay/{tid}/proof-file` endpoint serves the image from MongoDB and
still enforces owner/admin authorization.
