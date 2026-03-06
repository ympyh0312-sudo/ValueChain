"""
app/db/graph_repository.py
---------------------------------------------------------
Neo4j 그래프 CRUD Repository.

설계 원칙:
- MERGE 기반 멱등성: 같은 ticker로 중복 생성 불가, 있으면 업데이트
- 파라미터화 쿼리: Cypher injection 방지 + Neo4j 쿼리 플랜 캐싱
- 읽기/쓰기 분리: execute_query(읽기) vs execute_write(쓰기)
- 반환 타입 명시: 호출부에서 형변환 없이 바로 사용 가능

Cypher 패턴 설명:
- MERGE (n:Company {ticker: $ticker})  → ticker로 노드 찾고, 없으면 생성
- ON CREATE SET ...  → 최초 생성 시에만 적용
- ON MATCH SET  ...  → 이미 존재할 때 업데이트
- SET n.last_updated = datetime()  → 항상 적용 (양쪽 공통)
"""

from datetime import datetime, timezone
from typing import Any, Optional

from app.db.neo4j_client import neo4j_client
from app.models.graph_models import (
    CompanyCreate, CompanyResponse,
    SupplyRelationCreate, SupplyRelationResponse,
    get_sector_sensitivity,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


def _to_datetime(value: Any) -> Optional[datetime]:
    """neo4j.time.DateTime → Python datetime 변환.
    Neo4j 드라이버가 반환하는 neo4j.time.DateTime은 Pydantic이 직접
    파싱하지 못하므로, .to_native()로 표준 datetime으로 변환한다.
    """
    if value is None:
        return None
    if hasattr(value, "to_native"):   # neo4j.time.DateTime / Date / Time
        native = value.to_native()
        # naive datetime이면 UTC로 표시
        if native.tzinfo is None:
            native = native.replace(tzinfo=timezone.utc)
        return native
    if isinstance(value, datetime):
        return value
    return None


# ─────────────────────────────────────────────────────
# Company 노드 CRUD
# ─────────────────────────────────────────────────────

async def upsert_company(company: CompanyCreate) -> CompanyResponse:
    """
    기업 노드 생성 또는 업데이트 (UPSERT).

    MERGE on ticker: ticker가 같으면 기존 노드 업데이트,
    없으면 새 노드 생성.
    """
    cypher = """
    MERGE (c:Company {ticker: $ticker})
    ON CREATE SET
        c.name                  = $name,
        c.sector                = $sector,
        c.country               = $country,
        c.liquidity_score       = $liquidity_score,
        c.supplier_concentration = $supplier_concentration,
        c.last_updated          = datetime()
    ON MATCH SET
        c.name                  = $name,
        c.sector                = $sector,
        c.country               = $country,
        c.liquidity_score       = $liquidity_score,
        c.supplier_concentration = $supplier_concentration,
        c.last_updated          = datetime()
    RETURN
        c.ticker                  AS ticker,
        c.name                    AS name,
        c.sector                  AS sector,
        c.country                 AS country,
        c.liquidity_score         AS liquidity_score,
        c.supplier_concentration  AS supplier_concentration,
        c.last_updated            AS last_updated
    """
    params = {
        "ticker":                 company.ticker,
        "name":                   company.name,
        "sector":                 company.sector,
        "country":                company.country,
        "liquidity_score":        company.liquidity_score,
        "supplier_concentration": company.supplier_concentration,
    }
    records = await neo4j_client.execute_write(cypher, params)
    row = records[0]

    logger.info("company_upserted", ticker=company.ticker)
    return CompanyResponse(
        ticker                  = row["ticker"],
        name                    = row["name"],
        sector                  = row["sector"],
        country                 = row["country"],
        liquidity_score         = row["liquidity_score"],
        supplier_concentration  = row["supplier_concentration"],
        last_updated            = _to_datetime(row.get("last_updated")),
        sector_sensitivity      = get_sector_sensitivity(row["sector"]),
    )


async def get_company(ticker: str) -> Optional[CompanyResponse]:
    """티커로 기업 노드 단건 조회."""
    cypher = """
    MATCH (c:Company {ticker: $ticker})
    RETURN
        c.ticker                  AS ticker,
        c.name                    AS name,
        c.sector                  AS sector,
        c.country                 AS country,
        c.liquidity_score         AS liquidity_score,
        c.supplier_concentration  AS supplier_concentration,
        c.last_updated            AS last_updated
    """
    records = await neo4j_client.execute_query(cypher, {"ticker": ticker.upper()})
    if not records:
        return None
    row = records[0]
    return CompanyResponse(
        ticker                  = row["ticker"],
        name                    = row["name"],
        sector                  = row["sector"],
        country                 = row["country"],
        liquidity_score         = row["liquidity_score"],
        supplier_concentration  = row["supplier_concentration"],
        last_updated            = _to_datetime(row.get("last_updated")),
        sector_sensitivity      = get_sector_sensitivity(row["sector"]),
    )


async def get_companies_by_sector(sector: str) -> list[CompanyResponse]:
    """특정 섹터의 모든 기업 조회 (섹터 INDEX 활용)."""
    cypher = """
    MATCH (c:Company {sector: $sector})
    RETURN
        c.ticker                  AS ticker,
        c.name                    AS name,
        c.sector                  AS sector,
        c.country                 AS country,
        c.liquidity_score         AS liquidity_score,
        c.supplier_concentration  AS supplier_concentration,
        c.last_updated            AS last_updated
    ORDER BY c.ticker
    """
    records = await neo4j_client.execute_query(cypher, {"sector": sector})
    return [
        CompanyResponse(
            ticker                  = r["ticker"],
            name                    = r["name"],
            sector                  = r["sector"],
            country                 = r["country"],
            liquidity_score         = r["liquidity_score"],
            supplier_concentration  = r["supplier_concentration"],
            last_updated            = _to_datetime(r.get("last_updated")),
            sector_sensitivity      = get_sector_sensitivity(r["sector"]),
        )
        for r in records
    ]


# ─────────────────────────────────────────────────────
# SUPPLY_TO 관계 CRUD
# ─────────────────────────────────────────────────────

async def upsert_supply_relation(relation: SupplyRelationCreate) -> SupplyRelationResponse:
    """
    공급 관계(SUPPLY_TO) 생성 또는 업데이트.

    방향: (supplier)-[:SUPPLY_TO]->(buyer)
    두 노드가 모두 존재해야 관계 생성 가능.
    (없으면 LookupError 발생 → 노드 먼저 생성 필요)
    """
    cypher = """
    MATCH (s:Company {ticker: $supplier_ticker})
    MATCH (b:Company {ticker: $buyer_ticker})
    MERGE (s)-[r:SUPPLY_TO]->(b)
    ON CREATE SET
        r.revenue_share              = $revenue_share,
        r.dependency_score           = $dependency_score,
        r.geographic_exposure        = $geographic_exposure,
        r.alternative_supplier_score = $alternative_supplier_score,
        r.confidence_score           = $confidence_score,
        r.last_verified_at           = datetime()
    ON MATCH SET
        r.revenue_share              = $revenue_share,
        r.dependency_score           = $dependency_score,
        r.geographic_exposure        = $geographic_exposure,
        r.alternative_supplier_score = $alternative_supplier_score,
        r.confidence_score           = $confidence_score,
        r.last_verified_at           = datetime()
    RETURN
        s.ticker                    AS supplier_ticker,
        b.ticker                    AS buyer_ticker,
        r.revenue_share             AS revenue_share,
        r.dependency_score          AS dependency_score,
        r.geographic_exposure       AS geographic_exposure,
        r.alternative_supplier_score AS alternative_supplier_score,
        r.confidence_score          AS confidence_score,
        r.last_verified_at          AS last_verified_at
    """
    params = {
        "supplier_ticker":           relation.supplier_ticker,
        "buyer_ticker":              relation.buyer_ticker,
        "revenue_share":             relation.revenue_share,
        "dependency_score":          relation.dependency_score,
        "geographic_exposure":       relation.geographic_exposure,
        "alternative_supplier_score": relation.alternative_supplier_score,
        "confidence_score":          relation.confidence_score,
    }
    records = await neo4j_client.execute_write(cypher, params)

    if not records:
        raise LookupError(
            f"노드를 찾을 수 없음: "
            f"{relation.supplier_ticker} 또는 {relation.buyer_ticker}"
        )

    logger.info(
        "supply_relation_upserted",
        supplier=relation.supplier_ticker,
        buyer=relation.buyer_ticker,
        dependency=relation.dependency_score,
    )
    r = records[0]
    return SupplyRelationResponse(
        supplier_ticker              = r["supplier_ticker"],
        buyer_ticker                 = r["buyer_ticker"],
        revenue_share                = r["revenue_share"],
        dependency_score             = r["dependency_score"],
        geographic_exposure          = r["geographic_exposure"],
        alternative_supplier_score   = r["alternative_supplier_score"],
        confidence_score             = r["confidence_score"],
        last_verified_at             = _to_datetime(r.get("last_verified_at")),
    )


async def get_direct_suppliers(ticker: str) -> list[dict[str, Any]]:
    """
    특정 기업의 직접 공급사 목록 조회 (1-hop upstream).
    리스크 전파: 공급사에서 이 기업으로 리스크가 흘러옴.
    """
    cypher = """
    MATCH (supplier:Company)-[r:SUPPLY_TO]->(buyer:Company {ticker: $ticker})
    RETURN
        supplier.ticker               AS supplier_ticker,
        supplier.name                 AS supplier_name,
        supplier.sector               AS sector,
        supplier.country              AS country,
        supplier.liquidity_score      AS liquidity_score,
        r.dependency_score            AS dependency_score,
        r.revenue_share               AS revenue_share,
        r.geographic_exposure         AS geographic_exposure,
        r.alternative_supplier_score  AS alternative_supplier_score,
        r.confidence_score            AS confidence_score
    ORDER BY r.dependency_score DESC
    """
    return await neo4j_client.execute_query(cypher, {"ticker": ticker.upper()})


async def get_direct_buyers(ticker: str) -> list[dict[str, Any]]:
    """
    특정 기업의 직접 구매사 목록 조회 (1-hop downstream).
    리스크 전파: 이 기업에서 구매사로 리스크가 흘러감.
    """
    cypher = """
    MATCH (supplier:Company {ticker: $ticker})-[r:SUPPLY_TO]->(buyer:Company)
    RETURN
        buyer.ticker                  AS buyer_ticker,
        buyer.name                    AS buyer_name,
        buyer.sector                  AS sector,
        buyer.country                 AS country,
        buyer.liquidity_score         AS liquidity_score,
        r.dependency_score            AS dependency_score,
        r.revenue_share               AS revenue_share,
        r.geographic_exposure         AS geographic_exposure,
        r.alternative_supplier_score  AS alternative_supplier_score,
        r.confidence_score            AS confidence_score
    ORDER BY r.dependency_score DESC
    """
    return await neo4j_client.execute_query(cypher, {"ticker": ticker.upper()})


async def get_all_companies() -> list[dict[str, Any]]:
    """
    전체 기업 목록 조회 (ticker, name, sector, country).
    TickerRegistry 초기화 / 티커 리졸버용.
    """
    cypher = """
    MATCH (c:Company)
    RETURN
        c.ticker  AS ticker,
        c.name    AS name,
        c.sector  AS sector,
        c.country AS country
    ORDER BY c.ticker
    """
    return await neo4j_client.execute_query(cypher, {})


async def get_supply_relation(
    supplier_ticker: str,
    buyer_ticker: str,
) -> Optional[dict[str, Any]]:
    """
    두 기업 간 SUPPLY_TO 관계 단건 조회.
    버전 이력 저장 전 기존 상태(previous_state) 확인에 사용.
    """
    cypher = """
    MATCH (s:Company {ticker: $supplier_ticker})-[r:SUPPLY_TO]->(b:Company {ticker: $buyer_ticker})
    RETURN
        r.revenue_share              AS revenue_share,
        r.dependency_score           AS dependency_score,
        r.geographic_exposure        AS geographic_exposure,
        r.alternative_supplier_score AS alternative_supplier_score,
        r.confidence_score           AS confidence_score,
        r.last_verified_at           AS last_verified_at
    """
    records = await neo4j_client.execute_query(
        cypher,
        {
            "supplier_ticker": supplier_ticker.upper(),
            "buyer_ticker":    buyer_ticker.upper(),
        },
    )
    return records[0] if records else None


async def get_subgraph(ticker: str, max_hop: int = 3) -> dict[str, Any]:
    """
    특정 기업 중심의 서브그래프 조회 (다중 홉).

    Neo4j 가변 길이 패턴: [*1..{max_hop}] 으로 최대 홉 제한.
    방향: 공급사 → 대상 기업 방향(upstream)과
          대상 기업 → 구매사 방향(downstream) 모두 포함.

    반환:
        {
            "nodes": [{"ticker": ..., "name": ..., ...}],
            "edges": [{"source": ..., "target": ..., "dependency_score": ...}]
        }
    """
    cypher = f"""
    MATCH path = (n:Company)-[:SUPPLY_TO*1..{max_hop}]-(center:Company {{ticker: $ticker}})
    WITH collect(DISTINCT n) + [center] AS all_nodes,
         collect(DISTINCT relationships(path)) AS all_rels_lists
    UNWIND all_nodes AS node
    WITH
        collect(DISTINCT {{
            ticker:                  node.ticker,
            name:                    node.name,
            sector:                  node.sector,
            country:                 node.country,
            liquidity_score:         node.liquidity_score,
            supplier_concentration:  node.supplier_concentration
        }}) AS nodes,
        all_rels_lists
    UNWIND all_rels_lists AS rels
    UNWIND rels AS r
    WITH nodes,
         collect(DISTINCT {{
             source:             startNode(r).ticker,
             target:             endNode(r).ticker,
             dependency_score:   r.dependency_score,
             revenue_share:      r.revenue_share,
             confidence_score:   r.confidence_score
         }}) AS edges
    RETURN nodes, edges
    """
    records = await neo4j_client.execute_query(cypher, {"ticker": ticker.upper()})
    if not records:
        return {"nodes": [], "edges": []}
    return records[0]
