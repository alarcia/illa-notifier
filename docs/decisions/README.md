# Architecture Decision Records (ADRs)

This directory contains records of significant architectural and design decisions made for **Illa Notifier**. They follow the [MADR (Markdown Any Decision Records)](https://adr.github.io/madr/) format.

---

## 📋 Decision Log

| ID | Title | Status | Date |
|---|---|---|---|
| [ADR-0001](0001-single-process-multithreading.md) | Single-Process Multi-Threading vs Multi-Container Architecture | **Accepted** | 2026-03 |
| [ADR-0002](0002-sqlite-wal-for-edge-persistence.md) | SQLite with WAL Mode vs Client-Server DBMS (Postgres) | **Accepted** | 2026-03 |
| [ADR-0003](0003-scraping-vue-hydration-json.md) | Extracting Vue SSR Attributes vs Headless Browser Automation | **Accepted** | 2026-03 |
| [ADR-0004](0004-composite-deduplication-keys.md) | Multi-Channel Notification Idempotency via Composite Keys | **Accepted** | 2026-03 |
| [ADR-0005](0005-batched-email-resend.md) | Batched Email Digest via Resend API | **Accepted** | 2026-03 |

---

## Structure of an ADR
Each ADR documents:
- **Context & Problem Statement**: What was the challenge or need?
- **Decision Drivers**: What constraints or requirements influenced the choice?
- **Considered Options**: What alternatives were evaluated?
- **Decision Outcome**: What was chosen, why, and what are the positive and negative consequences?
