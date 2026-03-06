"""
app/main.py
---------------------------------------------------------
FastAPI 애플리케이션 진입점.

설계 원칙:
- lifespan: 앱 수명주기 관리 (DB open/close, 스키마 초기화)
- 미들웨어: CORS, 요청 로깅
- 라우터: 버전별 prefix (/api/v1/...)
- /health: 외부 헬스체크 (Docker, k8s probe 등)
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from neo4j.exceptions import ServiceUnavailable as Neo4jServiceUnavailable

from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger
from app.db.neo4j_client import neo4j_client
from app.db.postgres_client import postgres_client
from app.db.schema_init import init_graph_schema
from app.services.ticker_resolver import ticker_registry
from app.api.v1 import ingest, risk, network, ai_analysis
from app.services.dart_client import dart_client

# 로깅 설정은 임포트 시점에 즉시 적용
setup_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    앱 수명주기 관리.
    yield 전: 시작 로직 (DB 연결 → 스키마 초기화 → 티커 레지스트리 로드)
    yield 후: 종료 로직 (DB 연결 해제)

    초기화 순서:
    1. Neo4j 연결
    2. PostgreSQL 연결
    3. PostgreSQL 테이블 생성 (ORM 기반)
    4. Neo4j Constraint/Index 적용
    5. TickerRegistry 로드 (LLM 추출 파이프라인용)
    """
    logger.info("application_starting", env=settings.app_env)

    # 1. Neo4j 연결 (실패해도 앱은 기동 — Neo4j 없이 개발 가능)
    try:
        await neo4j_client.open()
    except Exception as e:
        logger.warning(
            "neo4j_startup_skipped",
            error=str(e),
            hint="Neo4j Desktop 또는 docker-compose up으로 Neo4j를 먼저 시작하세요.",
        )

    # 2. PostgreSQL 연결 + 테이블 초기화
    try:
        await postgres_client.open()
        await postgres_client.init_db()
    except Exception as e:
        logger.warning(
            "postgres_startup_skipped",
            error=str(e),
            hint="PostgreSQL이 실행 중이지 않습니다.",
        )

    # 3. Neo4j Constraint & Index 적용 (연결된 경우에만)
    try:
        await init_graph_schema()
    except Exception as e:
        logger.warning("graph_schema_init_skipped", error=str(e))

    # 4. TickerRegistry 로드 (Neo4j 기업 목록 → 인메모리 인덱스)
    try:
        company_count = await ticker_registry.refresh()
        logger.info("ticker_registry_loaded", companies=company_count)
    except Exception as e:
        logger.warning("ticker_registry_load_failed", error=str(e))

    logger.info("application_ready", version="1.0.0")

    yield  # 앱 실행 중

    # 종료: DB + HTTP 클라이언트 정리
    logger.info("application_shutting_down")
    await neo4j_client.close()
    await postgres_client.close()
    await dart_client.close()
    logger.info("application_stopped")


# FastAPI 앱 인스턴스
app = FastAPI(
    title="Financial Supply Chain Systemic Risk Engine",
    description=(
        "공급망 네트워크에서 금융 리스크가 전파되는 과정을 "
        "동적(time-aware)으로 시뮬레이션하는 엔진."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS 미들웨어
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_debug else ["https://your-frontend.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록 (/api/v1 prefix)
app.include_router(ingest.router,      prefix="/api/v1")
app.include_router(risk.router,        prefix="/api/v1")
app.include_router(network.router,     prefix="/api/v1")
app.include_router(ai_analysis.router, prefix="/api/v1")


# ── 전역 예외 핸들러 ──────────────────────────────────────
# Neo4j 미연결 시 503 반환 (드라이버가 None 상태)

@app.exception_handler(Neo4jServiceUnavailable)
async def neo4j_unavailable_handler(request: Request, exc: Neo4jServiceUnavailable) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Neo4j 데이터베이스에 연결할 수 없습니다. "
                "Neo4j Desktop에서 데이터베이스를 시작한 후 다시 시도하세요. "
                f"(Neo4j URI: {get_settings().neo4j_uri})"
            )
        },
    )


# 헬스체크 엔드포인트
@app.get("/health", tags=["System"])
async def health_check() -> JSONResponse:
    """인프라 연결 상태 확인. Docker healthcheck / k8s probe에서 호출."""
    neo4j_ok    = await neo4j_client.health_check()
    postgres_ok = await postgres_client.health_check()

    status      = "healthy" if (neo4j_ok and postgres_ok) else "degraded"
    http_status = 200 if status == "healthy" else 503

    return JSONResponse(
        status_code=http_status,
        content={
            "status": status,
            "services": {
                "neo4j":    "ok" if neo4j_ok    else "error",
                "postgres": "ok" if postgres_ok else "error",
            },
        },
    )


@app.get("/", tags=["System"])
async def root() -> dict:
    return {
        "name": "Risk Engine API",
        "version": "1.0.0",
        "docs": "/docs",
    }
