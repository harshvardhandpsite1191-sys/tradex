# AI-QROS
## Artificial Intelligence — Quantitative Research & Options Intelligence System

AI-QROS is an Autonomous Quantitative Research Scientist specialized for NIFTY & SENSEX Options.

---

## Architecture

```
backend/    → FastAPI + Python (Render)
frontend/   → Next.js + TypeScript (Vercel)
monitoring/ → Prometheus + Grafana
kubernetes/ → K8s manifests (prod deployment)
.github/    → CI/CD pipelines
```

## Data Providers
- **Indian Markets** — Upstox API (NIFTY, SENSEX, BANKNIFTY, Option Chain, FII/DII)
- **Global Markets** — yfinance (S&P 500, Nasdaq, Nikkei, Brent Crude, USD/INR etc.)
- **News/LLM** — OpenRouter free tier

## Hosting (Free Tier)
- Backend → Render
- Frontend → Vercel
- PostgreSQL → Neon
- Redis → Upstash

## Getting Started

### 1. Configure Environment
```bash
cp .env.example .env
# Fill in your Neon DB URL, Upstash Redis URL, Upstox API keys, OpenRouter API key
```

### 2. Run Locally with Docker Compose
```bash
docker-compose up --build
```

### 3. Services
| Service | URL |
|---|---|
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Frontend | http://localhost:3000 |
| MLflow | http://localhost:5000 |
| Grafana | http://localhost:3001 |
| Prometheus | http://localhost:9090 |

## Build Status
- Phase 0 — Project Foundation ✅
- Phase 1 — Institutional Research Library ✅
- Phase 2 — Data Infrastructure ✅
- Phase 3 — Data Quality & Governance ✅
- Phase 4 — Feature Engineering ✅
- Phase 5 — Behaviour Extraction ✅
- Phase 6-9 — Quantitative Research Pipeline ✅
- Phase 10 — Regime Classification ✅
- Phase 11 — Opening Intelligence ✅
- Phase 12 — Expiry Intelligence ✅
- Phase 13 — Scenario Library ✅
- Phase 14 — Historical Similarity ✅
- Phase 15 — Signal Generation ✅
- Phase 16 — AI Decision Engine (ML Models) ✅
- Phase 17 — Options Strategy Engine ✅
- Phase 18 — Trade Filter ✅
- Phase 19 — Trade Recommendation ✅
- Phase 20 — Live Engine ✅
- Phase 21 — Performance Tracking ✅
- Phase 22 — Continuous Learning ✅

