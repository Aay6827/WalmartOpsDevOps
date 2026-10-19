# Runbook: ApiDown

**Alert:** `ApiDown` (critical), fires when Prometheus cannot scrape the API for 1 minute.
**Meaning:** the API process or container is not reachable. This is different from `DatabaseDown`, where the API is up but cannot reach its database.

## 1. Confirm

```powershell
docker compose ps api
Invoke-RestMethod http://localhost:30000/health/live
```

## 2. Diagnose

```powershell
docker compose logs --tail 100 api
docker compose ps -a api                         # Exited? Restarting?
Get-NetTCPConnection -LocalPort 30000 -State Listen -ErrorAction SilentlyContinue   # something else holding the port?
```

Common causes: container crashed on startup (bad config or import error), port 30000 taken by another process, Docker engine not running.

## 3. Mitigate

```powershell
docker compose up -d api
```

If it crashes again, read the logs from step 2. If a recent change is responsible, roll back with `git revert` and rebuild:

```powershell
docker compose up -d --build api
```

## 4. Verify

```powershell
Invoke-RestMethod http://localhost:30000/health/ready
Invoke-RestMethod http://localhost:30001/api/v1/targets | Select-Object -ExpandProperty data | Select-Object -ExpandProperty activeTargets | Select-Object @{n='job';e={$_.labels.job}}, health
```

The `fulfilment-api` target should be `up`.

## 5. Follow-up

Record what happened and write an RCA in `docs/rca/` if the outage was more than a brief blip.