"""
app/db/schema_init.py
---------------------------------------------------------
Neo4j 그래프 스키마 초기화.

역할:
- Company.ticker UNIQUE constraint  → 중복 노드 생성 방지
- sector / country INDEX            → 섹터별 집계 쿼리 성능
- SUPPLY_TO 관계 INDEX              → 엣지 속성 기반 탐색 성능

설계 포인트:
- IF NOT EXISTS 구문으로 멱등성 보장 (앱 재시작 시 중복 오류 없음)
- 앱 시작(lifespan)에서 1회 실행
"""

from app.db.neo4j_client import neo4j_client
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Constraint 정의 ────────────────────────────────────
# ticker는 전 세계에서 기업을 유일하게 식별하는 키
# UNIQUE constraint는 자동으로 내부 인덱스도 생성함
CONSTRAINTS = [
    """
    CREATE CONSTRAINT company_ticker_unique IF NOT EXISTS
    FOR (c:Company)
    REQUIRE c.ticker IS UNIQUE
    """,
]

# ── Index 정의 ─────────────────────────────────────────
# UNIQUE constraint가 이미 ticker 인덱스를 만들기 때문에
# sector, country만 추가로 인덱싱
INDEXES = [
    # 섹터별 리스크 집계 쿼리에 사용
    """
    CREATE INDEX company_sector_idx IF NOT EXISTS
    FOR (c:Company) ON (c.sector)
    """,
    # 국가별 노출 분석 쿼리에 사용
    """
    CREATE INDEX company_country_idx IF NOT EXISTS
    FOR (c:Company) ON (c.country)
    """,
    # 의존도 기반 관계 필터링에 사용
    """
    CREATE INDEX supply_dependency_idx IF NOT EXISTS
    FOR ()-[r:SUPPLY_TO]-() ON (r.dependency_score)
    """,
]


async def init_graph_schema() -> None:
    """
    모든 Constraint와 Index를 Neo4j에 적용한다.
    IF NOT EXISTS 덕분에 이미 존재하면 무시하므로 중복 실행 안전.
    """
    logger.info("neo4j_schema_init_started")

    for cypher in CONSTRAINTS:
        try:
            await neo4j_client.execute_write(cypher.strip())
            logger.debug("neo4j_constraint_applied", cypher=cypher.strip()[:60])
        except Exception as e:
            # 이미 존재하는 constraint는 에러 무시
            logger.warning("neo4j_constraint_skip", error=str(e))

    for cypher in INDEXES:
        try:
            await neo4j_client.execute_write(cypher.strip())
            logger.debug("neo4j_index_applied", cypher=cypher.strip()[:60])
        except Exception as e:
            logger.warning("neo4j_index_skip", error=str(e))

    logger.info("neo4j_schema_init_completed")
