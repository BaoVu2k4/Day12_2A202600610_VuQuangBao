# Day 12 Lab — Mission Answers

**Student:** Vũ Quang Bảo  
**MSSV:** 2A202600610  
**Date:** 2026-06-12

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`

Đếm được **8 vấn đề** trong file:

1. **API key hardcode trong code**
   ```python
   OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"
   ```
   → Nếu push lên GitHub, key bị lộ ngay lập tức. Hacker có thể lạm dụng để tốn tiền.

2. **Database URL hardcode (lộ password)**
   ```python
   DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"
   ```
   → Password database `password123` nằm trực tiếp trong source code — rủi ro rất cao.

3. **Config hardcode thay vì đọc từ env**
   ```python
   DEBUG = True
   MAX_TOKENS = 500
   ```
   → Không thể thay đổi hành vi khi deploy sang môi trường khác mà không sửa code.

4. **Dùng `print()` thay vì proper logging — và log ra secret**
   ```python
   print(f"[DEBUG] Using key: {OPENAI_API_KEY}")  # ❌ log ra secret!
   ```
   → `print()` không có level, không có timestamp, không thể filter. Và còn in ra API key trong log.

5. **Không có health check endpoint**
   → Platform (Railway, Render, Kubernetes) gọi `/health` định kỳ để biết app còn sống không.
   Nếu không có, platform không thể tự restart khi agent crash.

6. **Port cứng định, không đọc từ `PORT` env var**
   ```python
   port=8000  # ❌ cứng port
   ```
   → Railway/Render inject `PORT` tự động qua env var. Port cứng 8000 sẽ không khớp.

7. **Host bind `localhost` thay vì `0.0.0.0`**
   ```python
   host="localhost"  # ❌ chỉ chạy được trên local
   ```
   → Trong Docker container, `localhost` chỉ là loopback nội bộ container.
   Cần `0.0.0.0` để nhận kết nối từ bên ngoài.

8. **`reload=True` trong production**
   ```python
   reload=True  # ❌ debug reload trong production
   ```
   → Auto-reload theo dõi file system liên tục, gây overhead và không ổn định trong production.

---

### Exercise 1.2: Chạy basic version

```bash
cd 01-localhost-vs-production/develop
pip install -r requirements.txt
PYTHONIOENCODING=utf-8 uvicorn app:app --host 127.0.0.1 --port 8001
```

**Output thực tế:**
```
# GET /
{"message":"Hello! Agent is running on my machine :)"}

# POST /ask?question=hello
[DEBUG] Got question: hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this   ← ❌ lộ key trong log!
[DEBUG] Response: Đây là câu trả lời từ AI agent (mock)...
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}

# GET /health  → 404 Not Found   ← ❌ không có health check!
```

**Quan sát thực tế:**
- Console in ra `[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this` — lộ secret ngay khi có request
- `/health` trả về 404 — platform không thể tự restart
- Trên Windows: `UnicodeEncodeError` khi `print()` tiếng Việt (thêm 1 anti-pattern của `print()`)
- Nếu chạy trong Docker: bind `localhost` → không nhận được request từ ngoài container

---

### Exercise 1.3: So sánh develop vs production

**Output production thực tế khi chạy:**
```
# GET /
{"app":"AI Agent","version":"1.0.0","environment":"development","status":"running"}

# POST /ask  -d '{"question":"hello"}'
{"question":"hello","answer":"Tôi là AI agent được deploy lên cloud...","model":"gpt-4o-mini"}

# GET /health → 200
{"status":"ok","uptime_seconds":1.6,"version":"1.0.0","timestamp":"2026-06-12T08:13:17+00:00"}

# GET /ready → 200
{"ready":true}

# GET /metrics → 200
{"uptime_seconds":2.3,"environment":"development","version":"1.0.0"}
```

| Feature | Develop (Basic) | Production (Advanced) | Tại sao quan trọng? |
|---------|----------------|----------------------|---------------------|
| **Config** | Hardcode trong code | Đọc từ env vars qua `Settings` dataclass | Bảo mật, dễ thay đổi giữa dev/staging/prod |
| **Secrets** | `OPENAI_API_KEY = "sk-..."` trong code | `os.getenv("OPENAI_API_KEY", "")` | Không bao giờ commit secret lên git |
| **Health check** | Không có | `/health` (liveness) + `/ready` (readiness) + `/metrics` | Platform tự restart khi crash; LB dừng route khi chưa ready |
| **Logging** | `print()` + in ra secret | Structured JSON logging — không log secret | Dễ parse bởi Datadog/Loki; an toàn |
| **Graceful shutdown** | Tắt đột ngột | SIGTERM handler + lifespan context | Hoàn thành request hiện tại trước khi tắt |
| **Host binding** | `host="localhost"` | `host="0.0.0.0"` (từ `settings.host`) | Container cần `0.0.0.0` để nhận traffic từ ngoài |
| **Port** | Cứng `8000` | `int(os.getenv("PORT", "8000"))` | Railway/Render inject `PORT` tự động |
| **Debug mode** | `reload=True` luôn | `reload=settings.debug` (chỉ bật khi `DEBUG=true`) | Production không được bật auto-reload |
| **CORS** | Không có | Chỉ cho phép origins trong `ALLOWED_ORIGINS` | Bảo mật trình duyệt, kiểm soát ai được gọi API |
| **Validate config** | Không | `Settings.validate()` — fail fast nếu thiếu | Phát hiện lỗi config ngay lúc start, không phải lúc runtime |

---

### Checkpoint 1 ✅

- [x] Hiểu tại sao hardcode secrets là nguy hiểm: key lộ trên GitHub, bất kỳ ai có thể lạm dụng
- [x] Biết cách dùng environment variables: `os.getenv("KEY", "default")`
- [x] Hiểu vai trò của health check: platform biết khi nào restart container
- [x] Biết graceful shutdown: xử lý SIGTERM để hoàn thành request trước khi tắt

---

## Part 2: Docker

### Exercise 2.1: Dockerfile cơ bản (`02-docker/develop/Dockerfile`)

1. **Base image là gì?**
   `python:3.11` — Python đầy đủ (~1 GB). Chứa pip, gcc, và toàn bộ toolchain.

2. **Working directory là gì?**
   `/app` — được set bởi `WORKDIR /app`. Mọi lệnh tiếp theo chạy trong thư mục này.

3. **Tại sao COPY requirements.txt trước khi COPY code?**
   Docker build theo layers. Nếu `requirements.txt` không thay đổi, layer `pip install` được cache lại.
   Chỉ khi `requirements.txt` thay đổi thì pip mới cài lại → build nhanh hơn nhiều.

4. **CMD vs ENTRYPOINT khác nhau thế nào?**
   - `CMD ["python", "app.py"]`: lệnh mặc định, có thể override khi chạy: `docker run image python other.py`
   - `ENTRYPOINT ["python"]`: cố định executable, chỉ override được args: `docker run image app.py`
   - Kết hợp: `ENTRYPOINT ["python"]` + `CMD ["app.py"]` → linh hoạt và explicit

---

### Exercise 2.2: Build và run basic image

```bash
docker build -f 02-docker/develop/Dockerfile -t agent-develop .
docker run -d -p 8003:8000 agent-develop
```

**Output thực tế khi chạy container:**
```
# GET /
{"message":"Agent is running in a Docker container!"}

# POST /ask?question=docker
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}

# GET /health → 200
{"status":"ok","uptime_seconds":2.1,"container":true}
```

Image size quan sát được:
```
REPOSITORY       SIZE
agent-develop    ~1.1 GB   ← python:3.11 full base image
```

---

### Exercise 2.3: Multi-stage build (`02-docker/production/Dockerfile`)

**Stage 1 (builder) làm gì?**
- Dùng `python:3.11-slim` + cài gcc, libpq-dev (build tools)
- Chạy `pip install --user -r requirements.txt`
- Kết quả: packages nằm trong `/root/.local`

**Stage 2 (runtime) làm gì?**
- Dùng `python:3.11-slim` sạch (không có gcc, không có build tools)
- `COPY --from=builder /root/.local /home/appuser/.local` — chỉ lấy packages đã build
- Chạy với non-root user `appuser` (bảo mật)
- Thêm `HEALTHCHECK` cho Docker tự restart

**Tại sao image nhỏ hơn?**
- Không có gcc, libpq-dev (chỉ cần để build, không cần để run)
- Không có pip cache (`--no-cache-dir`)
- Base slim không có docs, test files

**So sánh thực tế (đã build và đo):**
```
REPOSITORY         DISK USAGE
agent-develop      1.66 GB   ← python:3.11 full
agent-production    236 MB   ← python:3.11-slim + multi-stage
```
→ **Nhỏ hơn 7x** (giảm từ 1.66 GB xuống 236 MB)

**Output production container thực tế:**
```
# GET /  → {"app":"AI Agent","version":"2.0.0","environment":"production"}
# POST /ask → {"answer":"Container là cách đóng gói app..."}
# GET /health → {"status":"ok","uptime_seconds":0.6,...}
# GET /ready → {"ready":true}
```

---

### Exercise 2.4: Docker Compose stack

Services trong `docker-compose.yml`:
- **agent**: FastAPI app, build từ Dockerfile, expose port 8000
- **redis**: Redis 7 Alpine, dùng cho session storage

Cách communicate: qua Docker network nội bộ. Agent kết nối Redis qua `redis://redis:6379/0` (hostname `redis` = tên service trong compose).

---

### Checkpoint 2 ✅

- [x] Hiểu cấu trúc Dockerfile (FROM, WORKDIR, COPY, RUN, CMD)
- [x] Biết lợi ích multi-stage: image nhỏ hơn ~5x, an toàn hơn
- [x] Hiểu Docker Compose orchestration: nhiều service, chung network
- [x] Biết debug: `docker logs <id>`, `docker exec -it <id> /bin/sh`

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

**Steps thực hiện:**

```bash
cd 06-lab-complete
railway login
railway init
railway variables set ENVIRONMENT=production
railway variables set AGENT_API_KEY=<strong-key>
railway variables set OPENROUTER_API_KEY=<key>
# Thêm Redis plugin trong Railway dashboard → copy REDIS_URL
railway up
railway domain
```

- **URL:** https://exemplary-mercy-production-080d.up.railway.app
- **Project:** exemplary-mercy (ID: f1590677-db6e-4d8a-bc17-0409a4d1174e)
- **Service:** d371d6d3-800b-42db-9fe5-21a2ec05b820

**Kết quả test thực tế:**
```bash
# GET /health → 200
curl https://exemplary-mercy-production-080d.up.railway.app/health
# {"status":"ok","version":"1.0.0","environment":"production","uptime_seconds":34.3,...}

# POST /ask without key → 401
curl -X POST https://exemplary-mercy-production-080d.up.railway.app/ask \
  -H "Content-Type: application/json" -d '{"question":"Hello"}'
# {"detail":"Invalid or missing API key. Include header: X-API-Key: <key>"}

# POST /ask with key → 200
curl -X POST https://exemplary-mercy-production-080d.up.railway.app/ask \
  -H "X-API-Key: day12-secret-bao-2026" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is Docker?"}'
# {"question":"What is Docker?","answer":"Container là cách đóng gói app...","model":"gpt-4o-mini",...}

# Rate limit → 429 on request 10+ (RATE_LIMIT_PER_MINUTE=10)
# Request 10: HTTP 429
```

---

### Exercise 3.2: So sánh `render.yaml` vs `railway.toml`

| Điểm | `railway.toml` | `render.yaml` |
|------|---------------|---------------|
| Format | TOML | YAML |
| Builder | Nixpacks (auto-detect) | Docker hoặc native |
| Health check | `healthcheckPath` | `healthCheckPath` |
| Env vars | Qua CLI/dashboard | Trong file hoặc dashboard |
| Services | 1 service/file | Nhiều services/file |
| Restart | `restartPolicyType` | Tự động |

Render phức tạp hơn nhưng linh hoạt hơn, phù hợp cho multi-service.

---

### Checkpoint 3 ✅

- [x] Deploy thành công lên Railway
- [x] Có public URL hoạt động
- [x] Hiểu cách set environment variables trên cloud
- [x] Biết cách xem logs: `railway logs`

---

## Part 4: API Security

### Exercise 4.1: API Key authentication

API key được check trong `verify_api_key` dependency — gắn vào endpoint qua `Depends(verify_api_key)`.

Nếu sai key → trả về `401 Unauthorized`.

Để rotate key: thay env var `AGENT_API_KEY` trên platform → deploy lại. Không cần sửa code.

Test:
```bash
# Không có key → 401
curl http://localhost:8000/ask -X POST -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'

# Có key → 200
curl http://localhost:8000/ask -X POST \
  -H "X-API-Key: dev-key-change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'
```

---

### Exercise 4.2: JWT authentication

JWT flow:
1. `POST /auth/token` với username/password → nhận JWT (hết hạn 60 phút)
2. Các request sau: gửi `Authorization: Bearer <token>`
3. Server decode JWT, verify signature với `JWT_SECRET` → extract user info
4. Không cần query database mỗi request (stateless auth)

Ưu điểm: scalable — bất kỳ instance nào cũng verify được mà không cần shared session DB.

---

### Exercise 4.3: Rate limiting

**Algorithm:** Sliding Window Counter
- Mỗi user có 1 bucket chứa timestamps các request
- Mỗi request: loại bỏ timestamps cũ (ngoài 60s), đếm còn lại
- Nếu >= limit → 429 Too Many Requests

**Limit:** User: 10 req/phút; Admin: 100 req/phút

**Bypass cho admin:** role-based — kiểm tra JWT role, dùng `rate_limiter_admin` (100/phút) thay vì `rate_limiter_user` (10/phút).

---

### Exercise 4.4: Cost guard implementation

**Logic đã implement trong `04-api-gateway/production/cost_guard.py`:**
- Track token usage per user per day
- Global budget $10/ngày cho toàn service
- Per-user budget $1/ngày
- Warning khi dùng 80%
- Block khi vượt → 402 Payment Required / 503 Service Unavailable

```python
# Trước khi gọi LLM:
cost_guard.check_budget(user_id)

# Sau khi gọi LLM:
cost_guard.record_usage(user_id, input_tokens, output_tokens)
```

---

### Checkpoint 4 ✅

- [x] Implement API key authentication
- [x] Hiểu JWT flow: stateless, signed, có expiry
- [x] Implement rate limiting: sliding window, per-user
- [x] Implement cost guard: daily budget, per-user + global

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks

```python
@app.get("/health")
def health():
    """Liveness probe — container còn sống không?"""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "version": settings.app_version,
    }

@app.get("/ready")
def ready():
    """Readiness probe — sẵn sàng nhận traffic chưa?"""
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    return {"ready": True}
```

**Sự khác biệt:**
- `/health`: "Process có còn sống không?" → platform restart nếu fail
- `/ready`: "Có sẵn sàng nhận request không?" → LB ngừng route nếu fail (khi khởi động hoặc quá tải)

---

### Exercise 5.2: Graceful shutdown

```python
import signal

def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))
    # uvicorn tự hoàn thành in-flight requests trước khi thoát

signal.signal(signal.SIGTERM, _handle_signal)
```

Uvicorn có `timeout_graceful_shutdown=30` — cho 30 giây để hoàn thành requests trước khi force exit.

---

### Exercise 5.3: Stateless design

**Anti-pattern (❌ không scale được):**
```python
conversation_history = {}  # state trong memory

@app.post("/chat")
def chat(user_id: str, question: str):
    history = conversation_history.get(user_id, [])  # chỉ có ở instance này
```

**Correct (✅ stateless, scale được):**
```python
@app.post("/chat")
def chat(body: ChatRequest):
    session = load_session(body.session_id)   # load từ Redis
    history = session.get("history", [])
    # ... xử lý ...
    save_session(body.session_id, session)    # save về Redis
```

**Tại sao:** Khi có 3 instances, request lần 1 có thể vào Instance A, request lần 2 vào Instance B. Nếu state trong memory Instance A, Instance B không biết → bug. Lưu Redis → bất kỳ instance nào cũng đọc được.

---

### Exercise 5.4: Load balancing

```bash
docker compose up --scale agent=3
```

- Nginx phân tán requests theo round-robin
- Quan sát field `served_by` trong response — mỗi request được xử lý bởi instance khác nhau
- Nếu 1 instance die, Nginx tự chuyển traffic sang 2 instances còn lại

---

### Exercise 5.5: Test stateless

```bash
python 05-scaling-reliability/production/test_stateless.py
```

Kết quả: session_id giống nhau, nhưng `served_by` có thể khác instance → conversation history vẫn liên tục vì state trong Redis.

---

### Checkpoint 5 ✅

- [x] Implement `/health` và `/ready` checks
- [x] Implement graceful shutdown (SIGTERM handler)
- [x] Hiểu và implement stateless design (state trong Redis)
- [x] Hiểu load balancing với Nginx
- [x] Test stateless design thành công
