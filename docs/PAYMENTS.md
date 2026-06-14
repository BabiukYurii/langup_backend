# Payments architecture

Provider-agnostic billing built around a small domain core and an async, idempotent
webhook pipeline. Adding a provider = implementing one interface; the rest is unchanged.

## Components

- **`PaymentProvider` protocol** (`services/payments/providers/base.py`)
  `create_checkout` · `capture` · `refund` · `parse_webhook` · `verify_signature`.
  Concrete: `stripe_provider`, `paypal_provider`, `google_pay_provider`, `blik_provider`.
- **BillingService** — selects a provider, starts checkout, records `payments`.
- **SubscriptionService** + **state machine** — owns subscription lifecycle.
- **InvoiceService** — generates invoices/receipts (PDF in object storage, emailed).
- **PromoCodeService** — validation + redemption limits.
- **WebhookService** — verifies signatures, deduplicates, emits internal events.
- **UsageLimitService** — enforces plan quotas (free vs premium).

## Subscription state machine

```
            create
   none ─────────────► TRIALING ──(trial ends, paid)──► ACTIVE
                          │                               │  │
              (trial ends,│ no payment)        (renewal   │  │ (cancel at period end)
                          ▼                      fails)    │  ▼
                       EXPIRED ◄───────────────  PAST_DUE ─┘  CANCELED
                                  (retries exhausted)
```

- Allowed transitions are validated centrally; illegal jumps raise
  `InvalidSubscriptionTransition`.
- `PAST_DUE` triggers the failed-payment retry / dunning schedule (Celery).
- `cancel_at_period_end` keeps access until `current_period_end`, then → `CANCELED`.

## Webhook processing (idempotent)

```
provider ──► POST /webhooks/{provider}
                 │ 1. verify signature (provider secret)
                 │ 2. upsert into webhook_events (provider, event_id) UNIQUE
                 │    └─ duplicate? → 200 OK, do nothing  (idempotency)
                 │ 3. emit internal domain event (payment.succeeded, ...)
                 ▼
        event consumer / handler  → update subscription, issue invoice, adjust usage
                 │ 4. mark webhook_events.processed_at, status=PROCESSED
                 ▼
        failure → status=FAILED + error, safe to replay
```

Why this shape:
- **Idempotency** — the `UNIQUE(provider, event_id)` guard plus payment `idempotency_key`
  make retries and duplicate deliveries safe.
- **Async** — the HTTP handler only verifies + stores + emits; heavy work happens in the
  consumer, so providers get a fast 2xx and we avoid timeouts.
- **Auditable** — every raw event is persisted before processing.

## Plans & limits

`plans.limits` (JSONB) snapshots quotas per plan (e.g. `captures/day`, `ai_calls/month`).
`UsageLimit` rows track consumption per user/metric/period; `UsageLimitService` checks them
before expensive actions and raises `UsageLimitExceeded` when over the free-tier cap.
