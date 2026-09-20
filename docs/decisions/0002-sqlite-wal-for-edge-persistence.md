# ADR 0002: SQLite with WAL Mode vs Client-Server DBMS (PostgreSQL)

* **Status**: Accepted
* **Deciders**: Engineering Team
* **Date**: 2026-03

---

## Context and Problem Statement
The application requires persistent storage for movies, sessions, users, subscription preferences, and notification delivery history. The production environment is a Raspberry Pi running Docker.

## Decision Drivers
* Minimal memory and CPU consumption.
* Zero external service maintenance (no Postgres database management, credentials, or network socket overhead).
* Concurrent reads and writes between the background bot thread and the hourly scraper.
* Flash/SD storage longevity (minimizing aggressive fsync operations).

## Considered Options
1. **SQLite (WAL Mode)**: Embedded database stored in a single file mounted via Docker volume.
2. **PostgreSQL**: Running a Postgres container alongside the notifier via Docker Compose.

## Decision Outcome
Chosen option: **Option 1 (SQLite in WAL Mode with connection-per-call pattern)**.

### Configuration Details
* **WAL Mode (`PRAGMA journal_mode = WAL`)**: Allows concurrent reading while writing. Writers do not block readers; readers do not block writers.
* **`PRAGMA synchronous = NORMAL`**: Synchronizes WAL file at critical checkpoints rather than every transaction, drastically reducing wear on Raspberry Pi SD/SSD storage.
* **`PRAGMA busy_timeout = 5000`**: Handles transient lock contention gracefully by sleeping up to 5 seconds before failing.
* **Connection Lifecycle**: Every database method opens and closes its own connection, avoiding cross-thread connection sharing.

### Positive Consequences
* Zero maintenance overhead; backups are as simple as copying `notifier.db` (or using `VACUUM INTO`).
* Memory footprint negligible (< 5MB RAM).
* Fast sub-millisecond local queries.

### Negative Consequences / Trade-offs
* Concurrency limit: Only one thread can write at any single instant. (For an hourly scraper and occasional bot user inputs, write contention is virtually zero).
* Not suitable if the bot and scraper were scaled horizontally across multiple servers.
