# ADR 0004: Multi-Channel Notification Idempotency via Composite Keys

* **Status**: Accepted
* **Deciders**: Engineering Team
* **Date**: 2026-03

---

## Context and Problem Statement
Illa Notifier delivers notifications across two independent channels:
1. **Telegram Direct Messages (DMs)**.
2. **Email Digests (Resend)**.

Users may configure email alerts at a later time than their initial Telegram registration. In the original schema, `notification_log` had a simple unique constraint: `UNIQUE(telegram_id, movie_id)`. This meant that once a user received a Telegram DM, any future attempt to send an email for that same movie was blocked, or vice-versa.

## Decision Drivers
* Strict idempotency: A user must never receive duplicate DMs or duplicate emails for the same movie across multiple hourly scraper runs.
* Channel independence: Sending an alert on Telegram should not prevent sending an alert via Email if the user enables email later or if email delivery was delayed.
* Self-healing migration without downtime.

## Considered Options
1. **Separate Log Tables**: Create `telegram_notification_log` and `email_notification_log`.
2. **Composite Key in Single Table**: Add a `channel` column (`'telegram'` | `'email'`) and enforce `UNIQUE(telegram_id, movie_id, channel)`.

## Decision Outcome
Chosen option: **Option 2 (Composite Key in Single Table)**.

### Schema Implementation
```sql
CREATE TABLE notification_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    movie_id    INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    channel     TEXT NOT NULL DEFAULT 'telegram',
    sent_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (telegram_id, movie_id, channel)
);
```

### Positive Consequences
* Single table simplifies analytics and cascading cleanup when a user is removed.
* Clean distinction between Telegram and Email delivery logs.
* Backward-compatible programmatic migration in `Database._run_migrations()`.

### Negative Consequences / Trade-offs
* Query filters in `sync_service.py` must explicitly specify `nl.channel = 'telegram'` or `nl.channel = 'email'` when checking delivery status.
