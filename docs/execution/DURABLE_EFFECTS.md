# Durable kernel effects

EFFECT-220 adds a local SQLite outbox around the kernel's existing
`EffectIntent` and `EffectReceipt` contracts. It is a safety boundary, not a
provider or network gateway.

## Protocol

1. The capability token is checked against the intent's authority digest,
   action, normalized target, and token digest.
2. The complete intent is inserted into `effect_outbox` before an adapter is
   called. Reusing an idempotency key with a different intent fails closed.
3. Delivery changes `pending` to `executing`. A successful adapter result is
   converted to an `EffectReceipt` and inserted into the append-only
   `effect_receipts` table.
4. A retry after `receipt_recorded` returns the prior logical receipt and does
   not call the adapter again.
5. An adapter error, interrupted execution, or receipt-write failure becomes
   `reconciliation_required`. Recovery never blindly retries a possibly
   completed physical effect.
6. An authorized repair process may call `reconcile` with an explicit receipt
   witness. Reconciliation adopts that receipt without invoking the adapter.

The outbox stores parameter digests and receipt digests, not effect parameters
or secrets. It grants no network, credential, Git, merge, deploy, or spending
authority. Any adapter capability must still be supplied by the caller's
existing authority envelope.

## Recovery and rollback

Call `DurableEffectOutbox.recover()` after reopening a store. Any entry left in
`executing` is marked `reconciliation_required`. Inspect the append-only
reconciliation records, establish the external outcome through an independently
authorized capability token and witness, and either adopt a receipt with `reconcile` or preserve the
unresolved obligation for a separately authorized repair. Reverting the node
commit removes the new integration while preserving prior event and receipt
evidence.

The guarantee is local crash safety and duplicate logical adoption. It does not
claim exactly-once physical execution for an external system that cannot prove
its own idempotency.
