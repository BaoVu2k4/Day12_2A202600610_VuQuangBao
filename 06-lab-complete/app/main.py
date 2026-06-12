"""
Production AI Agent — NGAY09 Legal Multi-Agent System + Day 12 middleware

Checklist:
  ✅ Config từ environment (12-factor)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting
  ✅ Cost guard
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown
  ✅ Security headers
  ✅ CORS
  ✅ Error handling
  ✅ NGAY09 multi-agent integration (registry + law/tax/compliance)
"""
import asyncio
import os
import sys
import time
import signal
import logging
import json
import socket
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from app.auth import verify_api_key
from app.rate_limiter import check_rate_limit
from app.cost_guard import check_and_record_cost, get_daily_cost

# ─────────────────────────────────────────────────────────
# Logging — JSON structured
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0
_subprocesses: list = []

# ─────────────────────────────────────────────────────────
# LLM backend — real NGAY09 agents OR mock fallback
# ─────────────────────────────────────────────────────────
_use_real_agents = bool(os.getenv("OPENROUTER_API_KEY"))

if not _use_real_agents:
    from utils.mock_llm import ask as _mock_ask
    logger.warning(json.dumps({"event": "config", "llm": "mock", "reason": "OPENROUTER_API_KEY not set"}))


# ─────────────────────────────────────────────────────────
# Sub-agent management
# ─────────────────────────────────────────────────────────
async def _port_open(port: int, timeout: float = 30.0) -> bool:
    """Return True when 127.0.0.1:port accepts TCP connections."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            await asyncio.sleep(0.5)
    return False


async def _start_subagents() -> None:
    """Launch registry + law/tax/compliance agents as background subprocesses."""
    global _subprocesses
    python = sys.executable
    env = {**os.environ, "PYTHONPATH": str(os.getcwd())}

    # (module_name, port)
    agents = [
        ("registry", 10000),
        ("law_agent", 10101),
        ("tax_agent", 10102),
        ("compliance_agent", 10103),
    ]
    for module, port in agents:
        proc = await asyncio.create_subprocess_exec(
            python, "-m", module,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        _subprocesses.append(proc)
        logger.info(json.dumps({"event": "agent_started", "module": module, "pid": proc.pid, "port": port}))

    # Wait for registry to be reachable before marking app as ready
    if await _port_open(10000, timeout=30):
        logger.info(json.dumps({"event": "registry_ready"}))
    else:
        logger.warning(json.dumps({"event": "registry_timeout", "msg": "registry did not start in 30s"}))


def _stop_subagents() -> None:
    """Send SIGTERM to all sub-agent processes."""
    for proc in _subprocesses:
        try:
            proc.terminate()
        except Exception:
            pass
    logger.info(json.dumps({"event": "agents_stopped", "count": len(_subprocesses)}))


# ─────────────────────────────────────────────────────────
# Real-agent call via LangGraph
# ─────────────────────────────────────────────────────────
async def _call_real_agents(question: str) -> tuple[str, int, int]:
    """Invoke NGAY09 customer_agent graph and return (answer, in_tokens, out_tokens)."""
    from customer_agent.graph import build_graph
    from langchain_core.messages import HumanMessage, AIMessage

    trace_id = str(uuid4())
    context_id = str(uuid4())

    graph = build_graph(trace_id=trace_id, context_id=context_id, depth=0)
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=question)]},
        config={"configurable": {"thread_id": context_id}},
    )

    answer = ""
    in_tokens = 0
    out_tokens = 0

    for msg in reversed(result.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.content:
            answer = str(msg.content)
            usage = getattr(msg, "usage_metadata", None) or {}
            in_tokens = usage.get("input_tokens", 0)
            out_tokens = usage.get("output_tokens", 0)
            break

    if not answer:
        answer = "I was unable to process your legal question at this time."

    # Fall back to length-based estimates when usage_metadata is absent
    if not in_tokens:
        in_tokens = len(question.split()) * 2
    if not out_tokens:
        out_tokens = len(answer.split()) * 2

    return answer, in_tokens, out_tokens


# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "llm_backend": "ngay09_multiagent" if _use_real_agents else "mock",
    }))

    if _use_real_agents:
        await _start_subagents()
        await asyncio.sleep(3)  # let agents finish registering with each other

    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    _is_ready = False
    if _use_real_agents:
        _stop_subagents()
    logger.info(json.dumps({"event": "shutdown"}))


# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if "server" in response.headers:
            del response.headers["server"]
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception:
        _error_count += 1
        raise


# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000,
                          description="Your question for the legal agent")


class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    timestamp: str


# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────
@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "llm_backend": "ngay09_multiagent" if _use_real_agents else "mock",
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
            "metrics": "GET /metrics (requires X-API-Key)",
        },
    }


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """
    Send a legal question to the AI agent system.

    **Authentication:** Include header `X-API-Key: <your-key>`
    """
    check_rate_limit(_key[:8])

    # Pre-call budget check with estimated input tokens
    input_tokens = len(body.question.split()) * 2
    check_and_record_cost(input_tokens, 0)

    logger.info(json.dumps({
        "event": "agent_call",
        "q_len": len(body.question),
        "backend": "ngay09" if _use_real_agents else "mock",
        "client": str(request.client.host) if request.client else "unknown",
    }))

    if _use_real_agents:
        answer, in_tok, out_tok = await _call_real_agents(body.question)
        # Record actual output token cost (input was already recorded above)
        check_and_record_cost(0, out_tok)
        model_name = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4-5")
    else:
        answer = _mock_ask(body.question)
        output_tokens = len(answer.split()) * 2
        check_and_record_cost(0, output_tokens)
        model_name = "mock-llm"

    return AskResponse(
        question=body.question,
        answer=answer,
        model=model_name,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe. Platform restarts container if this fails."""
    backend = "ngay09_multiagent" if _use_real_agents else "mock"
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "llm_backend": backend,
        "agents_running": len(_subprocesses),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe. Load balancer stops routing here if not ready."""
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    return {"ready": True}


@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    """Basic metrics (protected)."""
    daily_cost = get_daily_cost()
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "daily_cost_usd": round(daily_cost, 4),
        "daily_budget_usd": settings.daily_budget_usd,
        "budget_used_pct": round(daily_cost / settings.daily_budget_usd * 100, 1),
        "llm_backend": "ngay09_multiagent" if _use_real_agents else "mock",
    }


# ─────────────────────────────────────────────────────────
# Graceful Shutdown
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))


signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
