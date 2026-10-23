# RCA addendum: follow-up actions, second drill, and what the measurements showed

Original RCA: [2026-10-19-postgres-outage-drill.md](2026-10-19-postgres-outage-drill.md). This addendum covers the follow-up work and a second drill on 2026-10-21, plus two experiments on 2026-10-22.

## Summary

Run 2 repeated the PostgreSQL outage drill after implementing most of the original action items. The new fast-burn alert fired about 90 s before the 5-minute error alert in the same run. Run 2 also exposed that the 4-second request failures during the outage are caused by DNS resolution of the stopped container's name, so the database connection timeouts added as a follow-up did not affect them. A related finding, that `/metrics` queried the database and therefore slowed to about 3.9 s during the outage, was fixed and re-measured (0.03 s).

## Status of the original action items

| # | Action | Status | Notes |
|---|---|---|---|
| 1 | Fast-burn error alert | Done | `HighErrorRateFastBurn`: 5xx ratio above 20% over 1 minute, for 30 s |
| 2 | Alertmanager receiver | Done; delivery partly verified | Webhook to a local sink container. Delivery was confirmed in smoke tests. During run 2, notification times were not captured: the drill script mis-parsed the sink's response and the sink recorded no timestamps (both fixed afterwards). Prometheus recorded about 8 notifications sent and 0 errors to Alertmanager in the 10 minutes up to the end of run 2. |
| 3 | Remove low-stock noise | Done | The thermos SKU is seeded with 40 units. `LowStockSkus` did not appear during run 2. |
| 4 | Database connection and pool timeouts | Implemented; no effect on the observed failure | See finding 2 |
| 5 | Capture latency and error counts in the drill | Partly | Peak 5xx ratio and p95 captured; see findings 3 and 4 for their limits |
| 6 | Re-run the drill and compare | Done | Run 2 |

## Run 2 measurements

Source: Prometheus's own alert-state history (`ALERTS` series, 5 s resolution), T+0 is fault injection.

| Event | T+ |
|---|---|
| `DatabaseDown` pending | 20 s |
| `DatabaseDown` firing | 50 s |
| `HighErrorRateFastBurn` pending | 70 s |
| `HighErrorRate` pending | 70 s |
| `HighLatencyP95` pending | 85 s |
| `HighErrorRateFastBurn` firing | 100 s |
| `HighErrorRate` firing | 190 s |

The drill script polled every 5 s and logged 61 s, 111 s and 202 s for the three firing events; the Prometheus record is treated as primary. Other observations: the API was ready 4 s after PostgreSQL restarted with no API restart, `DatabaseDown` and the fast-burn alert cleared 40 s and 43 s after recovery (script measurement), and all alerts were clear about 150 s after recovery.

## Comparison with run 1

- Within run 2, the fast-burn alert fired about 90 s before the 5-minute alert (100 s vs 190 s). This is the one comparison that rests on a single consistent measurement.
- For `DatabaseDown` and `HighErrorRate`, run 1 (76 s and 226 s) and run 2 (50 s and 190 s by Prometheus; 61 s and 202 s by script) are **not** claimed to differ. Run 1 was read by a script polling every 15 s with no cross-check, its Prometheus history was deleted by `docker compose down -v` before run 2, and the configuration of those two alerts did not change.

## Findings

### 1. The fast-burn alert's delay comes from its `for` clause, not its traffic guard

The rule ignores periods with less than 0.1 requests per second. During the outage, request rate stayed between 0.33 and 0.40 per second, above that floor. The 1-minute error ratio went from 0.098 at T+45 to 0.867 at T+60, the alert was pending at T+70, and firing at T+100 matches the 30 s `for` clause. The remaining delay is scrape, evaluation and window granularity.

### 2. The roughly 4 s failures are DNS resolution, so database timeouts do not apply

API logs for the drill window showed 60 `could not translate host name "postgres"` errors and 2 `connection refused` errors. In a controlled experiment, resolving `postgres` from inside the API container took about 4.0 s and then failed while PostgreSQL was stopped. A made-up hostname took 7.8 s to fail, a `.invalid` name failed in 0.03 s, and resolving a running service took under 20 ms. Real requests failed after about 3.9 s (`/inventory` returned 500 in 3.88 s, `/health/ready` returned 503 in about 3.9 to 4.0 s).

The connection, statement and pool timeouts added in the follow-up only apply after a name resolves, so they do not change this behaviour. This is specific to Docker Compose, where the embedded DNS removes a stopped container's name. In Kubernetes a Service name persists, so the failure mode would differ; that has not been tested.

### 3. The reported p95 overstates per-request latency

Prometheus reported a p95 of about 4.85 s during the outage while individual requests took about 3.9 s. That is consistent with `histogram_quantile` interpolating inside the 2.5 s to 5 s histogram bucket, so the p95 figure should be read as "in the 2.5 to 5 s bucket", not as a precise latency.

### 4. The load generator collapsed under slow failures

The traffic script issues requests sequentially. When each request began taking about 4 s to fail, offered load fell from about 6.6 requests per second to about 0.35. Absolute 5xx counts (about 61 in the 5-minute window) therefore depend on the client and are not a clean measure of impact.

### 5. `/metrics` queried the database

Measured on 2026-10-22: with PostgreSQL stopped, `/metrics` took about 3.9 s, because it ran a database query before answering. Prometheus's default scrape timeout is 10 s, so a slower resolver path could have caused scrape failures and a false `ApiDown`. The endpoint no longer touches the database: a background probe (`app/probe.py`, every 5 s) updates `db_up` and the low-stock gauge. After the change, the slowest `/metrics` response during an outage was 0.03 s, and `db_up` showed 0 about 12 s after the fault and returned to 1 within 2 s of restart (commit `e08fa23`).

## Still open

- User-facing endpoints still fail after about 4 s under Docker Compose. A circuit breaker or a shorter resolver timeout would address it; database timeouts do not.
- A concurrent load generator would make error counts comparable between runs.
- Notification delivery latency is not measured. Scraping Alertmanager's own metrics from Prometheus would provide it.

## Evidence

- `drill-2026-10-19-evidence.txt`: run 1 script output
- `drill-2026-10-21-run2-evidence.txt`: run 2 script output
- `experiment-dns-latency-2026-10-22.txt`: DNS and latency experiment
- `experiment-metrics-decoupling-2026-10-22.txt`: `/metrics` decoupling experiment