# RCA: PostgreSQL outage under load (game-day drill)

> Follow-up work and a second drill are documented in the [addendum](2026-10-19-postgres-outage-drill-addendum.md). Several action items below have since been implemented.

| | |
|---|---|
| **Type** | Planned game-day drill (fault injected deliberately; traffic is synthetic) |
| **Date** | 2026-10-19, 10:36 to 10:41 IST |
| **Duration of fault** | 226 seconds |
| **Severity (simulated)** | SEV-2: order and inventory writes failing |
| **Evidence** | `docs/rca/drill-2026-10-19-evidence.txt` (raw output of `scripts/incident_drill.ps1`) |

## Summary

PostgreSQL was stopped for 226 seconds while the fulfilment API served continuous synthetic traffic. The API process stayed up, but requests that needed the database failed with 5xx errors. `DatabaseDown` fired 76 seconds after the fault. `HighErrorRate` fired 226 seconds after the fault. Once Postgres restarted, the API recovered in 4 seconds without being restarted, and a new order was accepted immediately.

## Impact

Simulated: order creation, status updates and inventory reads failed for the duration of the outage. The 5xx ratio rose from 0% to 24.8% by the end of the fault window, measured over a 5-minute window that still contained healthy pre-fault traffic. Real customer impact is not applicable because this was a drill.

## Timeline (IST, T+ = seconds after fault injection)

| Time | T+ | Event |
|---|---|---|
| 10:36:38 | 0 | Fault injected: `docker compose stop postgres`. Baseline was db_up=1, 5xx ratio 0. |
| 10:36:54 | 16 | `db_up` still 1.0 (the API had not yet been scraped after the fault). |
| 10:37:09 | 31 | `db_up` = 0. First point where monitoring reflects the outage. |
| 10:37:24 | 46 | `DatabaseDown` pending. 5xx ratio 3.5%. |
| 10:37:54 | 76 | **`DatabaseDown` firing** (critical). 5xx ratio 5.1%. |
| 10:38:24 | 106 | `HighErrorRate` pending. `HighLatencyP95` also pending from T+91. |
| 10:40:24 | 226 | **`HighErrorRate` firing** (critical). 5xx ratio 24.8%. Alertmanager holds 3 active alerts. |
| 10:40:24 | 226 | Recovery: `docker compose start postgres`. |
| 10:40:28 | 230 | API readiness restored (4s after Postgres start). No API restart. |
| 10:40:28 | 230 | Post-recovery order accepted (order id 540). |
| 10:41:13 | 275 | `db_up` = 1. `HighErrorRate` still firing because of the 5-minute window. |

`ApiDown` never fired, which is correct: the process was alive and `/metrics` kept answering.

`LowStockSkus` also appears as firing at T+226. This is unrelated to the outage. The seed data deliberately sets SKU `WMT-1008` to 4 units (threshold is 5), so that alert was already pending before the drill started.

## Root cause

Injected fault: the PostgreSQL container was stopped. In a real incident this maps to database host failure, a failed deploy of the database, or loss of network path to it.

## Detection

- **Dependency alert (`DatabaseDown`, driven by the `db_up` gauge):** 76s. This was the early, specific signal.
- **Symptom alert (`HighErrorRate`):** 226s. Slower, but it measures actual user-visible failure.

Having both is deliberate: the dependency alert tells you *what* is wrong quickly, the symptom alert confirms *impact* and is the backstop if a failure is not covered by a dependency probe.

## What went well

- `/metrics` stayed available during the outage. An earlier version queried the database inside the metrics handler, so a database outage would have blinded monitoring and falsely fired `ApiDown`. This was found in review before the drill and fixed by adding `db_up` and making the handler tolerate database errors (covered by `tests/test_resilience.py`).
- Connection recovery was automatic (SQLAlchemy `pool_pre_ping`): 4 seconds, no restart, no manual intervention.
- The drill is repeatable and self-documenting: one script injects the fault, records alert timings and writes the evidence file.

## What went poorly

1. **`HighErrorRate` is slow.** It uses a 5-minute rate window plus a 2-minute `for` clause. Healthy pre-fault traffic dilutes the ratio, and the alert needed about 3.5 minutes after the fault to fire.
2. **Slow to resolve.** The same window kept the alert firing for 45+ seconds after recovery, when the service was already healthy.
3. **No notification path.** Alertmanager has a default receiver with no integration configured, so alerts are visible in the UI and API but nobody would be paged.
4. **Alert noise from seed data.** `LowStockSkus` is permanently pending or firing because of the deliberate low-stock SKU, which can mask real signals.
5. **Latency under failure is unmeasured.** `HighLatencyP95` reached pending, which suggests requests slowed while waiting on the unreachable database. Actual latency values were not captured.

## Action items (proposed, not yet implemented)

| # | Action | Why |
|---|---|---|
| 1 | Add a fast-burn error alert (1m rate window, short `for`) alongside the existing 5m alert | Cut time-to-detect for severe error spikes |
| 2 | Configure an Alertmanager receiver (webhook, Slack or email) | Alerts must reach a human |
| 3 | Reseed or label the low-stock SKU so `LowStockSkus` does not fire in normal operation | Reduce noise |
| 4 | Set a database connection and pool timeout so requests fail fast during an outage | Bound request latency during dependency failure |
| 5 | Capture p95 latency and 503 counts in the drill script | Complete the evidence |
| 6 | Re-run the drill after items 1 to 4 and compare timings | Prove the improvement |

## Runbooks used or referenced

- `docs/runbooks/database-down.md`
- `docs/runbooks/high-error-rate.md`
- `docs/runbooks/api-down.md`