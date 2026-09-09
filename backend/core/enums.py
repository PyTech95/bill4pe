"""Canonical status enums for the payment → bill → settlement lifecycle.

Customer payment state, bill state and merchant settlement state are kept as
THREE independent fields on a transaction so they never clobber each other.
"""


class PaymentStatus:
    CREATED = "created"
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    MANUAL_REVIEW = "manual_review"  # e.g. amount mismatch — needs a human


class BillStatus:
    PENDING = "pending"
    GENERATED = "generated"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class SettlementStatus:
    NOT_REQUIRED = "not_required"   # reimbursement model — money never in our path
    NOT_STARTED = "not_started"
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    REVERSED = "reversed"
    MANUAL_REVIEW = "manual_review"


class PayoutStatus:
    """RazorpayX payout lifecycle for the collect-and-payout (v2) model."""
    NOT_STARTED = "not_started"
    NOT_CONFIGURED = "not_configured"   # RazorpayX creds absent → deferred, never lost
    REQUESTED = "requested"             # DB claim taken, provider call in flight
    QUEUED = "queued"                   # queued_for_balance / provider queued
    PENDING = "pending"
    SCHEDULED = "scheduled"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    REVERSED = "reversed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    MANUAL_REVIEW = "manual_review"     # provider rejected beneficiary/compliance


class AuditEvent:
    TRANSACTION_CREATED = "transaction_created"
    ORDER_CREATED = "razorpay_order_created"
    ORDER_REUSED = "razorpay_order_reused"
    CALLBACK_RECEIVED = "payment_callback_received"
    SIGNATURE_FAILED = "payment_signature_failed"
    PAYMENT_VERIFIED = "payment_verified"
    PAYMENT_CAPTURED = "payment_captured"
    PAYMENT_FAILED = "payment_failed"
    AMOUNT_MISMATCH = "payment_amount_mismatch"
    WEBHOOK_RECEIVED = "webhook_received"
    WEBHOOK_INVALID_SIGNATURE = "webhook_invalid_signature"
    WEBHOOK_DUPLICATE_IGNORED = "webhook_duplicate_ignored"
    BILL_GENERATED = "bill_generated"
    BILL_REUSED = "bill_reused"
    SETTLEMENT_CREATED = "settlement_created"
    SETTLEMENT_PROCESSED = "settlement_processed"
    SETTLEMENT_FAILED = "settlement_failed"
    REFUND_PROCESSED = "refund_processed"
    RECONCILED = "transaction_reconciled"
    RECOVERED = "reconciliation_recovered_payment"
    # ---- v2 collect-and-payout ----
    QR_SCANNED = "qr_scanned"
    PAYEE_LOCKED = "payee_locked"
    BENEFICIARY_CREATED = "razorpayx_beneficiary_created"
    BENEFICIARY_REUSED = "razorpayx_beneficiary_reused"
    PAYOUT_REQUESTED = "payout_requested"
    PAYOUT_QUEUED = "payout_queued"
    PAYOUT_PROCESSING = "payout_processing"
    PAYOUT_PROCESSED = "payout_processed"
    PAYOUT_FAILED = "payout_failed"
    PAYOUT_REVERSED = "payout_reversed"
    PAYOUT_WEBHOOK_RECEIVED = "payout_webhook_received"
