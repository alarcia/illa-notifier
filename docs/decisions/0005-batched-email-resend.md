# ADR 0005: Batched Email Digest via Resend API

* **Status**: Accepted
* **Deciders**: Engineering Team
* **Date**: 2026-03

---

## Context and Problem Statement
When the cinema updates its billboard on Thursdays/Fridays, between 3 to 8 new movies or new formats may be introduced in a single scraping pass. Sending an individual transactional email for every movie would flood user inboxes and quickly consume email API quotas.

We needed a clean design for transactional email delivery.

## Decision Drivers
* High user experience: no email spamming.
* Cost & quota efficiency (Resend free tier limits: 100 emails/day, 3,000 emails/month).
* Mobile-responsive dark-mode email presentation with poster previews and ticket booking CTA buttons.
* Resilient delivery handling network hiccups.

## Considered Options
1. **Immediate Per-Movie Email**: Dispatch an email as soon as each new movie is processed in the loop.
2. **Aggregated Batching per Run Cycle**: Collect all newly detected movies during the cycle, group them by user subscription, and dispatch a single aggregated digest per recipient.

## Decision Outcome
Chosen option: **Option 2 (Aggregated Batching per Run Cycle)**.

### Technical Details
* In `src/sync_service.py`, detected movies are queued in `new_movies_for_email`.
* After looping through all movies, matching email subscribers are grouped:
  ```python
  subscriber_movies: dict[tuple[int, str], list[MovieData]] = {}
  ```
* A single digest email is compiled with responsive HTML cards and dynamic subject line:
  - Single movie: `"🎬 Nueva película: <Title>"`
  - Multiple movies: `"🎬 N nuevas películas en cartelera"`
* Up to 3 retry attempts with exponential backoff (`delay = min(1.0 * (2 ** attempt), 8.0)`).
* Failure of email delivery does not fail the Telegram alerts, and unconfigured Resend credentials log a clean warning without throwing exceptions.

### Positive Consequences
* Maximum 1 email per user per hourly run, regardless of how many movies were released.
* Drastically reduced API consumption on Resend.
* Clean visual presentation of all new titles in one place.

### Negative Consequences / Trade-offs
* If one movie fails rendering inside a batch, the whole batch could fail delivery (mitigated by pre-validating and using simple string templating rather than dynamic external templates).
