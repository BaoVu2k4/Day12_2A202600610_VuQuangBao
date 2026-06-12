# Deployment Guide — Day 12 Lab

**Student:** Vũ Quang Bảo — MSSV 2A202600610  
**Date:** 2026-06-12

---

## Live URL

**https://exemplary-mercy-production-080d.up.railway.app**

Railway Project: `exemplary-mercy`  
Service ID: `d371d6d3-800b-42db-9fe5-21a2ec05b820`

---

## Quick Test

```bash
BASE=https://exemplary-mercy-production-080d.up.railway.app

# Liveness
curl $BASE/health

# Readiness
curl $BASE/ready

# Auth test — expect 401
curl -X POST $BASE/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'

# Authorized request — expect 200
curl -X POST $BASE/ask \
  -H "X-API-Key: day12-secret-bao-2026" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is Docker?"}'
```

---

## Architecture

```
Railway Cloud
└── exemplary-mercy (FastAPI + uvicorn)
    ├── GET  /          — app info
    ├── GET  /health    — liveness probe (Railway healthcheck)
    ├── GET  /ready     — readiness probe
    ├── POST /ask       — AI agent (requires X-API-Key)
    └── GET  /metrics   — usage stats (requires X-API-Key)
```

**Middleware stack:**
- CORS (allow all origins in production)
- Request logger (structured JSON)
- Security headers (X-Content-Type-Options, X-Frame-Options)
- API Key authentication
- Rate limiter: 10 req/min per key (sliding window)
- Cost guard: $10/day global budget

---

## Deploy Steps (Railway CLI)

```bash
cd 06-lab-complete

# One-time setup
railway login
railway link f1590677-db6e-4d8a-bc17-0409a4d1174e

# Set env vars
railway variables set ENVIRONMENT=production --service exemplary-mercy
railway variables set AGENT_API_KEY=<strong-key> --service exemplary-mercy
railway variables set JWT_SECRET=<jwt-secret> --service exemplary-mercy
railway variables set APP_NAME="Legal Multi-Agent" --service exemplary-mercy
railway variables set RATE_LIMIT_PER_MINUTE=10 --service exemplary-mercy
railway variables set DAILY_BUDGET_USD=10.0 --service exemplary-mercy

# Deploy
railway up --service exemplary-mercy

# Get URL
railway domain --service exemplary-mercy

# View logs
railway logs --service exemplary-mercy
```

---

## Dockerfile Summary

Multi-stage build (< 500 MB):
- **Stage 1 (builder):** `python:3.11-slim` + venv + pip install
- **Stage 2 (runtime):** `python:3.11-slim` + copy `/opt/venv` + non-root user `agent`

Key features:
- Non-root user (security)
- Fixed venv path (not `--user`) to avoid cross-user copy issues
- `HEALTHCHECK` every 30s
- `PYTHONUNBUFFERED=1` for real-time logs

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AGENT_API_KEY` | Yes | API key for `/ask` endpoint |
| `JWT_SECRET` | Yes | JWT signing secret |
| `ENVIRONMENT` | Yes | Set to `production` |
| `APP_NAME` | No | Display name |
| `RATE_LIMIT_PER_MINUTE` | No | Default: 20 |
| `DAILY_BUDGET_USD` | No | Default: 5.0 |
| `OPENAI_API_KEY` | No | Real LLM (mock used if missing) |
| `PORT` | Auto | Injected by Railway |

---

## Test Results (2026-06-12)

| Test | Expected | Result |
|------|----------|--------|
| `GET /health` | 200 | ✅ 200 |
| `GET /ready` | 200 | ✅ 200 |
| `POST /ask` (no key) | 401 | ✅ 401 |
| `POST /ask` (valid key) | 200 | ✅ 200 |
| Rate limit (11th req) | 429 | ✅ 429 |
