# Runbook: HighErrorRate

**Alert:** `HighErrorRate` (critical), fires when more than 5% of requests return 5xx over 5 minutes, sustained for 2 minutes.
**Meaning:** users are seeing server errors. Check whether `DatabaseDown` is also firing first, since that is the most common cause.

## 1. Triage

Open the dashboard: http://localhost:30002/d/walmartops-overview and look at "Requests by status code" and "Requests by endpoint".

Find which endpoints are failing (run in Prometheus at http://localhost:30001):

```
sum by (path, status) (rate(http_requests_total{status=~"5.."}[5m]))
```

## 2. Decide the cause

| Signal | Likely cause | Go to |
|---|---|---|
| `DatabaseDown` firing, `db_up` is 0 | Database unreachable | `database-down.md` |
| One endpoint failing, others fine | Bug in that code path | Step 3 |
| Started right after a deploy | Bad release | Step 4 |
| Latency also high | Resource exhaustion or slow dependency | Step 3 |

## 3. Inspect

```powershell
docker compose logs --tail 100 api
docker compose ps
```

## 4. Mitigate

If a recent change caused it, roll back:

```powershell
git log --oneline -5
git revert <bad-commit>
docker compose up -d --build api
```

If the API is unhealthy but the database is fine:

```powershell
docker compose restart api
```

## 5. Verify

- 5xx ratio on the dashboard returns toward 0.
- `Invoke-RestMethod http://localhost:30000/health/ready` returns `ready`.
- The alert clears. This can lag recovery by a few minutes (5-minute window).

## 6. Follow-up

Write an RCA in `docs/rca/` if impact lasted more than a few minutes.