# ADR 0001: Single-Process Multi-Threading vs Multi-Container Architecture

* **Status**: Accepted
* **Deciders**: Engineering Team
* **Date**: 2026-03

---

## Context and Problem Statement
Illa Notifier requires two ongoing workloads:
1. An hourly cron-like task to scrape the cinema website and run the catalog reconciliation and notification pipeline.
2. A persistent, long-polling interactive Telegram bot to serve user commands (`/start`, `/alerts`, `/email`) and inline keyboard callbacks in real time.

We need to decide whether to split these components into distinct Docker containers (or separate processes managed by Celery/Redis) or keep them united within a single process.

## Decision Drivers
* Target host is a low-power, resource-constrained edge device (Raspberry Pi).
* Operational simplicity: single `docker-compose.yml` service, single image, single deploy pipeline.
* Low traffic volume: scraping happens once per hour; bot interactions occur occasionally.
* Shared database access: both workloads interact with SQLite.

## Considered Options
1. **Single-Process Multi-Threading**: Main thread handles the scraper loop; daemon worker thread runs the Telegram bot async polling loop.
2. **Multi-Container / Multi-Process (Microservices)**: Separate scraper and bot containers communicating over a shared volume or message broker (Redis + Celery).

## Decision Outcome
Chosen option: **Option 1 (Single-Process Multi-Threading)**.

### Positive Consequences
* **Minimal Resource Footprint**: Entire system consumes ~60-80 MB of RAM on the Raspberry Pi.
* **Trivial Deployment**: Deployed with a single `docker compose up -d --build`.
* **Zero Infrastructure Overhead**: No Redis, RabbitMQ, or Celery worker setups required.

### Negative Consequences / Trade-offs
* **Thread Signal Workaround**: `python-telegram-bot` requires bypassing default signal registration (`_run_bot_async`) because signals only work on the main interpreter thread.
* **Process Coupling**: A catastrophic unhandled crash in the main thread could terminate the entire container (mitigated by `restart: unless-stopped` in Docker Compose and comprehensive exception handlers around `run_cycle()`).
