# SimPars safety changes

This branch hardens the existing architecture without changing the SQLite schema.

- Wallet debits use `BEGIN IMMEDIATE` and a conditional balance update, so concurrent callbacks cannot spend the same balance.
- 5SIM inventory entries with non-positive cost or stock are discarded. The selected operator is pinned through checkout, and the purchase client refuses `any` or a provider response that changes the operator.
- Cached inventory is only a selection hint. Checkout refreshes options before charging, as already required by the purchase flow.
- ProSMM `add` requests are never retried automatically. A timeout must be reconciled by the owner/provider before another order is submitted. Read-only/status operations retain bounded retries.
- Refunds remain guarded by the existing one-way order status transition, so repeated callbacks and polling cannot refund the same order twice.

The branch was not connected to live provider credentials and no real purchase or payment was performed. Manual verification still requires a sandbox/test credential, provider balance, and a non-production Telegram account.