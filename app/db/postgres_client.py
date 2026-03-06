"""
app/db/postgres_client.py
─────────────────────────────────────────────────────────
PostgreSQL Async 연결 관리 (SQLAlchemy + asyncpg).

설계 원칙:
- create_async_engine: asyncpg 드라이버 기반 커넥션 풀 생성
- AsyncSession: 각 요청마다 독립 세션 (트랜잭션 격리)
- get_session: FastAPI Depends()와 함께 쓰는 제너레이터
- init_db: 앱 시작 시 테이블 자동 생성 (개발 편의)
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── ORM Base 클래스 ────────────────────────────
# 모든 SQLAlchemy 모델이 이 클래스를 상속
class Base(DeclarativeBase):
    pass


class PostgresClient:
    """
    PostgreSQL 비동기 클라이언트.
    커넥션 풀 + 세션 팩토리를 관리한다.
    """

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._settings = get_settings()

    async def open(self) -> None:
        """
        엔진 + 커넥션 풀 + 세션 팩토리 초기화.

        pool_size: 상시 유지하는 연결 수
        max_overflow: pool_size 초과 시 추가 허용 연결 수
        pool_pre_ping: 요청 전 연결 유효성 자동 확인 (끊긴 연결 재연결)
        """
        self._engine = create_async_engine(
            self._settings.postgres_dsn,
            pool_size=self._settings.postgres_pool_size,
            max_overflow=self._settings.postgres_max_overflow,
            pool_pre_ping=True,          # 끊긴 연결 자동 감지
            echo=self._settings.app_debug,  # 개발 시 SQL 쿼리 로그 출력
        )

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,      # commit 후에도 객체 속성 접근 가능
            autoflush=False,
            autocommit=False,
        )

        # 연결 검증
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("postgres_connected", dsn=self._settings.postgres_dsn.split("@")[1])
        except Exception as e:
            logger.warning("postgres_connection_failed", error=str(e))
            raise

    async def close(self) -> None:
        """엔진 + 커넥션 풀 정리."""
        if self._engine:
            await self._engine.dispose()
            logger.info("postgres_connection_closed")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        세션 컨텍스트 매니저.
        예외 발생 시 자동 롤백, 정상 종료 시 커밋.

        Usage:
            async with postgres_client.get_session() as session:
                result = await session.execute(select(NewsArticle))
        """
        if not self._session_factory:
            raise RuntimeError("PostgreSQL engine not initialized. Call open() first.")

        session: AsyncSession = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error("postgres_session_rollback", error=str(e))
            raise
        finally:
            await session.close()

    async def init_db(self) -> None:
        """
        모든 테이블 자동 생성 (Base.metadata 기반).
        개발 환경에서 Alembic 없이 빠른 스키마 반영용.
        프로덕션에서는 Alembic 마이그레이션 사용 권장.
        """
        if not self._engine:
            raise RuntimeError("PostgreSQL engine not initialized.")

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("postgres_tables_initialized")

    async def health_check(self) -> bool:
        """연결 상태 확인. 엔진 없으면 즉시 False 반환."""
        if not self._engine:
            return False
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.warning("postgres_health_check_failed", error=str(e))
            return False


# ── 앱 전역 싱글턴 인스턴스 ──────────────────────────
postgres_client = PostgresClient()


# ── FastAPI Depends()용 제너레이터 ────────────────────
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 의존성 주입용 세션 제너레이터.

    Usage:
        @router.get("/example")
        async def example(session: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with postgres_client.get_session() as session:
        yield session
