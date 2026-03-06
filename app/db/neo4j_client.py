"""
app/db/neo4j_client.py
─────────────────────────────────────────────────────────
Neo4j Async 드라이버 + 커넥션 풀 관리.

설계 원칙:
- AsyncGraphDatabase.driver: 공식 async 드라이버 사용
- 커넥션 풀: max_connection_pool_size로 동시 쿼리 처리 제어
- Neo4jClient 클래스: 앱 수명주기와 연동 (open/close)
- execute_query / execute_write: 읽기/쓰기 분리 (Neo4j 권장 패턴)
"""

from typing import Any
from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from neo4j.exceptions import ServiceUnavailable, AuthError

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Neo4jClient:
    """
    Neo4j 비동기 클라이언트 래퍼.
    앱 시작 시 open(), 종료 시 close() 호출.
    """

    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None
        self._settings = get_settings()

    async def open(self) -> None:
        """
        드라이버 초기화 + 연결 검증.
        연결 실패 시 예외를 올리지 않고 _driver=None 상태 유지.
        (앱 기동은 허용, API 호출 시 503 반환)
        """
        try:
            self._driver = AsyncGraphDatabase.driver(
                self._settings.neo4j_uri,
                auth=(self._settings.neo4j_user, self._settings.neo4j_password),
                max_connection_pool_size=self._settings.neo4j_max_connection_pool_size,
                connection_timeout=self._settings.neo4j_connection_timeout,
            )
            # 실제 연결 가능 여부 확인 (드라이버 생성만으로는 연결 안 됨)
            await self._driver.verify_connectivity()
            logger.info("neo4j_connected", uri=self._settings.neo4j_uri)

        except AuthError as e:
            logger.error("neo4j_auth_failed", error=str(e))
            self._driver = None
            raise
        except ServiceUnavailable as e:
            logger.warning("neo4j_unavailable", uri=self._settings.neo4j_uri, error=str(e))
            self._driver = None
            raise
        except Exception as e:
            logger.warning("neo4j_open_failed", error=str(e))
            self._driver = None
            raise

    async def close(self) -> None:
        """드라이버 + 커넥션 풀 정리."""
        if self._driver:
            await self._driver.close()
            logger.info("neo4j_connection_closed")

    @property
    def is_connected(self) -> bool:
        """Neo4j 드라이버가 초기화되어 있는지 확인."""
        return self._driver is not None

    def get_session(self, database: str = "neo4j") -> AsyncSession:
        """
        세션 컨텍스트 매니저 반환.
        드라이버가 없으면 ServiceUnavailable 발생 (→ API에서 503 처리).

        Usage:
            async with neo4j_client.get_session() as session:
                result = await session.run("MATCH (n) RETURN n LIMIT 1")
        """
        if not self._driver:
            raise ServiceUnavailable(
                "Neo4j에 연결되어 있지 않습니다. "
                "Neo4j Desktop 또는 docker-compose up으로 Neo4j를 시작한 후 다시 시도하세요."
            )
        return self._driver.session(database=database)

    async def execute_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str = "neo4j",
    ) -> list[dict[str, Any]]:
        """
        읽기 전용 쿼리 실행 (READ transaction).
        결과를 dict 리스트로 반환.

        Args:
            query: Cypher 쿼리 문자열
            parameters: 쿼리 파라미터 (SQL injection 방지용 파라미터화)
            database: 대상 Neo4j 데이터베이스 이름

        Returns:
            [{"key": value, ...}, ...] 형태의 결과 리스트
        """
        async with self.get_session(database) as session:
            result = await session.run(query, parameters or {})
            records = await result.data()   # list[dict] 변환
            logger.debug(
                "neo4j_query_executed",
                query=query[:80],           # 로그에 쿼리 앞 80자만 기록
                row_count=len(records),
            )
            return records

    async def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str = "neo4j",
    ) -> list[dict[str, Any]]:
        """
        쓰기 쿼리 실행 (WRITE transaction).
        Neo4j는 읽기/쓰기 트랜잭션을 분리하여 클러스터 환경에서 최적화.
        """
        async with self.get_session(database) as session:
            async with await session.begin_transaction() as tx:
                result = await tx.run(query, parameters or {})
                records = await result.data()
                await tx.commit()
                logger.debug(
                    "neo4j_write_executed",
                    query=query[:80],
                    row_count=len(records),
                )
                return records

    async def health_check(self) -> bool:
        """연결 상태 확인 (헬스체크 엔드포인트에서 사용)."""
        try:
            await self.execute_query("RETURN 1 AS alive")
            return True
        except Exception as e:
            logger.warning("neo4j_health_check_failed", error=str(e))
            return False


# ── 앱 전역 싱글턴 인스턴스 ──────────────────────────
# main.py의 lifespan에서 open()/close() 호출
neo4j_client = Neo4jClient()
