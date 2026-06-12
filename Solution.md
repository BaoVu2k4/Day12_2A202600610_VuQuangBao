# Solution.md — Day 12 Lab Submission

**Student:** Vũ Quang Bảo  
**MSSV:** 2A202600610  
**Date:** 2026-06-12  
**Deadline:** 24h ngày 12/6/2026

---

## 🌐 Production URL

```
https://exemplary-mercy-production-080d.up.railway.app
```

| Endpoint | Method | Kết quả |
|----------|--------|---------|
| `/` | GET | Web UI (chat interface) |
| `/health` | GET | `{"status":"ok","llm_backend":"ngay09_multiagent","agents_running":4}` |
| `/ready` | GET | `{"ready":true}` |
| `/ask` | POST | Trả lời câu hỏi pháp lý (yêu cầu `X-API-Key`) |
| `/metrics` | GET | Thống kê sử dụng |

**Test nhanh:**
```bash
# Liveness
curl https://exemplary-mercy-production-080d.up.railway.app/health

# Có key → 200, real AI answer
curl -X POST https://exemplary-mercy-production-080d.up.railway.app/ask \
  -H "X-API-Key: day12-secret-bao-2026" \
  -H "Content-Type: application/json" \
  -d '{"question":"What are SEC disclosure requirements for IPO?"}'

# Không key → 401
curl -X POST https://exemplary-mercy-production-080d.up.railway.app/ask \
  -d '{"question":"test"}'
```

---

## Project Lab Assignment

**Dự án:** Legal Multi-Agent System (từ NGAY09)  
**Framework:** FastAPI + LangGraph + A2A SDK  
**Platform:** Railway (Docker multi-stage)

**Kiến trúc 5 agents trong 1 container:**
```
FastAPI (entry point, port $PORT)
  └── customer_agent (LangGraph)
        └── law_agent (port 10101) ← orchestrator
              ├── tax_agent (port 10102)
              └── compliance_agent (port 10103)
registry (port 10000) ← service discovery
```

**Middleware Day 12 đã áp dụng:**
- ✅ API Key authentication (`X-API-Key` header)
- ✅ Rate limiting: 10 req/min, sliding window → 429
- ✅ Cost guard: $10/day budget → 402
- ✅ Structured JSON logging
- ✅ `/health` + `/ready` endpoints
- ✅ Graceful shutdown (SIGTERM)
- ✅ Stateless design (UUID per request)
- ✅ Multi-stage Dockerfile (python:3.11-slim, non-root)
- ✅ CI/CD via GitHub Actions (bonus)

**GitHub repo:** https://github.com/BaoVu2k4/Day12_2A202600610_VuQuangBao  
**Source code:** `06-lab-complete/`

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns trong `develop/app.py`

Tìm được **8 vấn đề:**

1. **API key hardcode trong code**
   ```python
   OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"
   ```
   → Push lên GitHub là lộ key ngay. Fix: `os.getenv("OPENAI_API_KEY")`

2. **Database URL hardcode (lộ password)**
   ```python
   DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"
   ```
   → Password `password123` trong source code — rủi ro cao.

3. **Config hardcode thay vì đọc từ env**
   ```python
   DEBUG = True
   MAX_TOKENS = 500
   ```
   → Không thể thay đổi hành vi giữa dev/staging/prod mà không sửa code.

4. **`print()` thay vì proper logging — và log ra secret**
   ```python
   print(f"[DEBUG] Using key: {OPENAI_API_KEY}")  # ❌ lộ key trong log!
   ```
   → `print()` không có level, timestamp, không thể filter.

5. **Không có health check endpoint**
   → Platform gọi `/health` định kỳ để biết app còn sống. Thiếu → không tự restart được.

6. **Port cứng, không đọc từ `PORT` env var**
   ```python
   port=8000  # ❌ Railway inject PORT qua env
   ```

7. **Host bind `localhost` thay vì `0.0.0.0`**
   ```python
   host="localhost"  # ❌ container không nhận traffic từ ngoài
   ```

8. **`reload=True` trong production**
   ```python
   reload=True  # ❌ debug reload gây overhead, không ổn định
   ```

---

### Exercise 1.2: Chạy basic version

```bash
cd 01-localhost-vs-production/develop
PYTHONIOENCODING=utf-8 uvicorn app:app --host 127.0.0.1 --port 8001
```

**Output quan sát được:**
```
GET /  → {"message":"Hello! Agent is running on my machine :)"}
POST /ask?question=hello
  → [DEBUG] Using key: sk-hardcoded-fake-key-never-do-this   ← ❌ lộ key!
  → {"answer":"Đây là câu trả lời từ AI agent (mock)..."}
GET /health → 404 Not Found   ← ❌ không có health check!
```

---

### Exercise 1.3: So sánh develop vs production

| Feature | Develop | Production |
|---------|---------|------------|
| Config | Hardcode | `os.getenv()` + `Settings` dataclass |
| Secrets | `sk-...` trong code | Env vars, không bao giờ log |
| Health check | 404 | `/health` 200 + `/ready` 200 |
| Logging | `print()` + lộ key | Structured JSON, không log secret |
| Graceful shutdown | Tắt đột ngột | SIGTERM handler + 30s timeout |
| Host | `localhost` | `0.0.0.0` |
| Port | Cứng 8000 | `int(os.getenv("PORT", "8000"))` |
| Debug | `reload=True` luôn | Chỉ bật khi `DEBUG=true` |

### Checkpoint 1 ✅
- [x] Hardcode secrets → nguy hiểm: key lộ GitHub
- [x] Environment variables: `os.getenv("KEY", "default")`
- [x] Health check: platform biết khi nào restart
- [x] Graceful shutdown: SIGTERM để hoàn thành request

---

## Part 2: Docker

### Exercise 2.1: Phân tích Dockerfile cơ bản

1. **Base image:** `python:3.11` (~1 GB) — Python đầy đủ, có gcc, pip, toolchain
2. **Working directory:** `/app` — mọi lệnh chạy trong đây
3. **COPY requirements.txt trước:** Docker build theo layers. Nếu requirements không đổi, layer `pip install` được cache → build nhanh hơn
4. **CMD vs ENTRYPOINT:**
   - `CMD ["python", "app.py"]`: override được khi `docker run image other.py`
   - `ENTRYPOINT ["python"]`: cố định executable, chỉ override args
   - Kết hợp: linh hoạt + explicit

---

### Exercise 2.2: Build và run basic image

```bash
docker build -f 02-docker/develop/Dockerfile -t agent-develop .
docker run -d -p 8003:8000 agent-develop
```

```
REPOSITORY       SIZE
agent-develop    ~1.1 GB
```

---

### Exercise 2.3: Multi-stage build

**Stage 1 (builder):** `python:3.11-slim` + gcc + `pip install` vào venv `/opt/venv`  
**Stage 2 (runtime):** `python:3.11-slim` sạch + `COPY --from=builder /opt/venv` + non-root user

**Tại sao nhỏ hơn:** không có gcc, libpq-dev, pip cache trong runtime image.

**Kết quả đo thực tế:**
```
agent-develop      1.66 GB   ← python:3.11 full
agent-production    236 MB   ← multi-stage slim
```
→ **Nhỏ hơn 7x**

---

### Exercise 2.4: Docker Compose

Services: `agent` (FastAPI) + `redis` (Redis 7 Alpine).  
Communicate qua Docker network: `redis://redis:6379/0` (hostname = tên service).

### Checkpoint 2 ✅
- [x] Dockerfile: FROM, WORKDIR, COPY, RUN, CMD
- [x] Multi-stage: image nhỏ 7x, không có build tools trong runtime
- [x] Docker Compose: orchestrate nhiều services
- [x] Debug: `docker logs`, `docker exec -it sh`

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

```bash
cd 06-lab-complete
railway login
railway link f1590677-db6e-4d8a-bc17-0409a4d1174e
railway variables set ENVIRONMENT=production
railway variables set AGENT_API_KEY=day12-secret-bao-2026
railway variables set OPENROUTER_API_KEY=<key>
railway variables set OPENROUTER_MODEL=anthropic/claude-3-haiku
railway up --service exemplary-mercy
```

**URL live:** `https://exemplary-mercy-production-080d.up.railway.app`

**Test thực tế:**
```bash
$ curl https://exemplary-mercy-production-080d.up.railway.app/health
{"status":"ok","version":"1.0.0","environment":"production",
 "uptime_seconds":60.2,"llm_backend":"ngay09_multiagent","agents_running":4}

$ curl -X POST .../ask -H "X-API-Key: day12-secret-bao-2026" \
  -d '{"question":"What are SEC disclosure requirements for IPO?"}'
{"answer":"The key SEC disclosure requirements for a company going public include:
1. Filing a detailed registration statement (Form S-1)...
2. Preparing a comprehensive prospectus...
...","model":"anthropic/claude-3-haiku","timestamp":"2026-06-12T10:20:05Z"}

$ curl -X POST .../ask  → HTTP 401  (no key)
$ 11th request in 1 min  → HTTP 429  (rate limit)
```

---

### Exercise 3.2: `render.yaml` vs `railway.toml`

| Điểm | `railway.toml` | `render.yaml` |
|------|---------------|---------------|
| Format | TOML | YAML |
| Builder | Nixpacks / Dockerfile | Docker hoặc native |
| Health check | `healthcheckPath` | `healthCheckPath` |
| Restart | `restartPolicyType` | Tự động |
| Multi-service | 1 service/file | Nhiều services/file |

`render.yaml` linh hoạt hơn cho multi-service, `railway.toml` đơn giản hơn.

### Checkpoint 3 ✅
- [x] Deploy thành công lên Railway — URL live hoạt động
- [x] Set environment variables trên cloud
- [x] Xem logs: `railway logs --service exemplary-mercy`
- [x] Hiểu `render.yaml` vs `railway.toml`

---

## Part 4: API Security

### Exercise 4.1: API Key authentication

```python
# app/auth.py
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key
```

Rotate key: thay env var `AGENT_API_KEY` → không cần sửa code.

```bash
# Không key → 401
curl -X POST .../ask -d '{"question":"Hello"}'

# Đúng key → 200
curl -X POST .../ask -H "X-API-Key: day12-secret-bao-2026" -d '{"question":"Hello"}'
```

---

### Exercise 4.2: JWT authentication

Flow:
1. `POST /auth/token` với credentials → nhận JWT (TTL 60 phút)
2. Request sau: `Authorization: Bearer <token>`
3. Server decode + verify signature với `JWT_SECRET`
4. Stateless — không query DB mỗi request → scalable

---

### Exercise 4.3: Rate limiting

**Algorithm:** Sliding Window Counter

```python
# app/rate_limiter.py
def check_rate_limit(key: str) -> None:
    now = time.time()
    window = _windows[key]
    while window and window[0] < now - 60:
        window.popleft()           # loại bỏ timestamps cũ
    if len(window) >= settings.rate_limit_per_minute:
        raise HTTPException(429, "Rate limit exceeded")
    window.append(now)
```

Kết quả test: req 1-10 → 200, req 11 → **429**.

---

### Exercise 4.4: Cost guard

```python
# app/cost_guard.py
def check_and_record_cost(input_tokens: int, output_tokens: int) -> None:
    if _daily_cost >= settings.daily_budget_usd:
        raise HTTPException(402, "Daily budget exhausted")
    cost = (input_tokens/1000)*0.00015 + (output_tokens/1000)*0.0006
    _daily_cost += cost
```

Khi vượt `DAILY_BUDGET_USD=$10` → **HTTP 402 Payment Required**.

### Checkpoint 4 ✅
- [x] API key authentication: `X-API-Key` header, 401 khi sai
- [x] JWT: stateless, signed, có expiry
- [x] Rate limiting: sliding window 10 req/min, 429 khi vượt
- [x] Cost guard: daily budget $10, 402 khi vượt

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks

```python
@app.get("/health")   # Liveness — container còn sống?
def health():
    return {"status": "ok", "uptime_seconds": round(time.time() - START_TIME, 1)}

@app.get("/ready")    # Readiness — sẵn sàng nhận traffic?
def ready():
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    return {"ready": True}
```

`/health` fail → platform **restart container**.  
`/ready` fail → load balancer **ngừng route** (khi đang khởi động hoặc quá tải).

---

### Exercise 5.2: Graceful shutdown

```python
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))

signal.signal(signal.SIGTERM, _handle_signal)
# uvicorn timeout_graceful_shutdown=30 → hoàn thành in-flight requests trong 30s
```

---

### Exercise 5.3: Stateless design

**Anti-pattern ❌**
```python
conversation_history = {}           # state trong memory — không scale
history = conversation_history[user_id]
```

**Correct ✅**
```python
session = load_session(session_id)  # Redis — bất kỳ instance nào đọc được
save_session(session_id, session)
```

Tại sao: 3 instances → request 1 vào Instance A, request 2 vào Instance B.  
State trong memory A → Instance B không biết → bug. Redis → tất cả đều đọc được.

---

### Exercise 5.4: Load balancing

```bash
docker compose up --scale agent=3
```

Nginx round-robin phân tán. Field `served_by` trong response thay đổi theo từng request.  
1 instance die → Nginx chuyển traffic sang 2 instances còn lại tự động.

---

### Exercise 5.5: Test stateless

```bash
python 05-scaling-reliability/production/test_stateless.py
```

`session_id` giống nhau, `served_by` khác instance → history vẫn liên tục (state trong Redis).

### Checkpoint 5 ✅
- [x] `/health` và `/ready`: liveness vs readiness
- [x] Graceful shutdown: SIGTERM + 30s timeout
- [x] Stateless design: state trong Redis, không trong memory
- [x] Load balancing: Nginx round-robin, `--scale agent=3`
- [x] Test stateless thành công

---

## Tổng kết

| Phần | Checkpoint |
|------|-----------|
| Part 1: Localhost vs Production | ✅ |
| Part 2: Docker | ✅ |
| Part 3: Cloud Deployment | ✅ |
| Part 4: API Security | ✅ |
| Part 5: Scaling & Reliability | ✅ |

**Production:** `https://exemplary-mercy-production-080d.up.railway.app`  
**Source:** `06-lab-complete/` trong repo  
**CI/CD:** GitHub Actions (bonus) — auto build + deploy on push to `main`
