# Runbook: DatabaseDown

**Alert:** `DatabaseDown` (critical), fires when `db_up == 0` for 30 seconds.
**Meaning:** the fulfilment API is running but cannot reach PostgreSQL. Order and inventory requests fail with 5xx. `ApiDown` will *not* fire in this case.

## 1. Confirm

```powershell
Invoke-RestMethod http://localhost:30000/health/ready      # expect failure (503) while the DB is down
(Invoke-WebRequest http://localhost:30000/metrics -UseBasicParsing).Content -split "`n" | Select-String "^db_up"
docker compose ps postgres
```

## 2. Diagnose

```powershell
docker compose logs --tail 50 postgres
docker compose ps -a postgres          # Exited? Unhealthy? Restarting?
docker system df                       # disk pressure on the Docker volume
```

Common causes: container stopped or crashed, out of disk, bad credentials or config change, network path broken.

## 3. Mitigate

```powershell
docker compose start postgres
docker compose ps postgres             # wait for (healthy)
```

## 4. Verify recovery

```powershell
Invoke-RestMethod http://localhost:30000/health/ready      # expect status: ready
(Invoke-WebRequest http://localhost:30000/metrics -UseBasicParsing).Content -split "`n" | Select-String "^db_up"   # expect 1.0
```

The API reconnects on its own (pool pre-ping). If readiness is still failing after Postgres is healthy:

```powershell
docker compose restart api
```

Note: `HighErrorRate` may keep firing for several minutes after recovery because of its 5-minute window. That is expected.

## 5. Follow-up

- Record the timeline and write an RCA in `docs/rca/`.
- If data loss is suspected, check recent orders for gaps before closing.