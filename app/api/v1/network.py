"""
app/api/v1/network.py
---------------------------------------------------------
공급망 그래프 네트워크 CRUD + 분석 엔드포인트.

엔드포인트:
    POST   /network/companies                      - 기업 노드 생성/업데이트
    GET    /network/companies                      - 기업 목록 (섹터 필터)
    GET    /network/companies/{ticker}             - 기업 단건 조회
    DELETE /network/companies/{ticker}             - 기업 삭제
    POST   /network/relations                      - 공급 관계 생성/업데이트
    GET    /network/companies/{ticker}/suppliers   - 직접 공급사 목록
    GET    /network/companies/{ticker}/buyers      - 직접 구매사 목록
    GET    /network/companies/{ticker}/subgraph    - 서브그래프 조회
    POST   /network/systemic-risk                  - 시스템 리스크 중요도 분석

라우팅 주의:
    /network/companies, /network/systemic-risk 등
    고정 경로는 /{ticker} 보다 먼저 등록해야 path parameter 충돌 없음.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from neo4j.exceptions import ServiceUnavailable

from app.core.logging import get_logger
from app.db.graph_repository import (
    upsert_company,
    get_company,
    get_companies_by_sector,
    upsert_supply_relation,
    get_direct_suppliers,
    get_direct_buyers,
    get_subgraph,
)
from app.engine.scenario_analysis import SystemicRiskScorer
from app.models.graph_models import CompanyCreate, CompanyResponse, SupplyRelationCreate, SupplyRelationResponse
from app.services.ticker_resolver import ticker_registry
from app.api.v1.schemas import SystemicRiskRequest

logger = get_logger(__name__)

router = APIRouter(prefix="/network", tags=["Network"])


# ─────────────────────────────────────────────────────
# POST /network/companies  (고정 경로 — /{ticker} 보다 먼저)
# ─────────────────────────────────────────────────────

@router.post(
    "/companies",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="기업 노드 생성/업데이트",
    description=(
        "기업 노드를 Neo4j에 UPSERT합니다. "
        "같은 ticker가 존재하면 업데이트, 없으면 새로 생성합니다. "
        "저장 후 TickerRegistry에도 즉시 반영됩니다."
    ),
)
async def create_company(body: CompanyCreate) -> CompanyResponse:
    try:
        response = await upsert_company(body)
    except ServiceUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j에 연결할 수 없습니다. Neo4j Desktop에서 데이터베이스를 시작하세요.",
        )
    except Exception as e:
        logger.error("create_company_failed", ticker=body.ticker, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"기업 저장 실패: {e}",
        )

    # TickerRegistry 즉시 동기화 (다음 LLM 추출 시 바로 매핑 가능)
    ticker_registry.add_entry(response.ticker, response.name)
    return response


# ─────────────────────────────────────────────────────
# GET /network/companies  (고정 경로)
# ─────────────────────────────────────────────────────

@router.get(
    "/companies",
    response_model=list[CompanyResponse],
    summary="기업 목록 조회",
    description="전체 기업 또는 섹터별 기업 목록을 반환합니다.",
)
async def list_companies(
    sector: Optional[str] = Query(None, description="GICS 섹터 필터 (예: Technology)"),
) -> list[CompanyResponse]:
    if sector:
        return await get_companies_by_sector(sector)

    # 전체 목록: get_all_companies → CompanyResponse 변환
    from app.db.graph_repository import get_all_companies
    from app.models.graph_models import get_sector_sensitivity

    rows = await get_all_companies()
    # get_all_companies returns ticker, name, sector, country only
    # liquidity_score / supplier_concentration 기본값으로 채움
    return [
        CompanyResponse(
            ticker                  = r["ticker"],
            name                    = r["name"] or "",
            sector                  = r["sector"] or "Unknown",
            country                 = r["country"] or "",
            liquidity_score         = 0.5,
            supplier_concentration  = 0.5,
            sector_sensitivity      = get_sector_sensitivity(r.get("sector") or "Unknown"),
        )
        for r in rows
    ]


# ─────────────────────────────────────────────────────
# POST /network/systemic-risk  (고정 경로 — /{ticker} 보다 먼저)
# ─────────────────────────────────────────────────────

@router.post(
    "/systemic-risk",
    summary="시스템 리스크 중요도 분석",
    description=(
        "각 기업을 충격 원점으로 시뮬레이션하여 시스템 리스크 중요도를 산출합니다. "
        "점수가 높은 기업이 공급망 전체에 가장 큰 영향을 주는 핵심 기업입니다."
    ),
)
async def systemic_risk(body: SystemicRiskRequest) -> list[dict]:
    scorer = SystemicRiskScorer(
        shock_intensity = body.shock_intensity,
        max_hop         = body.max_hop,
    )
    try:
        scores = await scorer.compute_all(body.tickers)
    except Exception as e:
        logger.error("systemic_risk_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"시스템 리스크 계산 오류: {e}",
        )

    return [
        {
            "ticker":                s.ticker,
            "name":                  s.name,
            "sector":                s.sector,
            "country":               s.country,
            "systemic_score":        round(s.systemic_score, 6),
            "affected_count":        s.affected_count,
            "total_transmitted_risk": round(s.total_transmitted_risk, 6),
            "avg_risk_per_affected": round(s.avg_risk_per_affected, 6),
        }
        for s in sorted(scores, key=lambda x: x.systemic_score, reverse=True)
    ]


# ─────────────────────────────────────────────────────
# GET /network/companies/{ticker}
# ─────────────────────────────────────────────────────

@router.get(
    "/companies/{ticker}",
    response_model=CompanyResponse,
    summary="기업 단건 조회",
)
async def get_company_detail(ticker: str) -> CompanyResponse:
    company = await get_company(ticker.upper())
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ticker='{ticker.upper()}' 를 찾을 수 없습니다.",
        )
    return company


# ─────────────────────────────────────────────────────
# DELETE /network/companies/{ticker}
# ─────────────────────────────────────────────────────

@router.delete(
    "/companies/{ticker}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="기업 노드 삭제",
    description="기업 노드와 연결된 모든 SUPPLY_TO 관계를 삭제합니다.",
)
async def delete_company(ticker: str) -> None:
    from app.db.neo4j_client import neo4j_client

    ticker_upper = ticker.upper()
    cypher = "MATCH (c:Company {ticker: $ticker}) DETACH DELETE c"
    await neo4j_client.execute_write(cypher, {"ticker": ticker_upper})
    logger.info("company_deleted", ticker=ticker_upper)


# ─────────────────────────────────────────────────────
# POST /network/relations
# ─────────────────────────────────────────────────────

@router.post(
    "/relations",
    response_model=SupplyRelationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="공급 관계 생성/업데이트",
    description=(
        "두 기업 간 SUPPLY_TO 관계를 UPSERT합니다. "
        "supplier_ticker, buyer_ticker 기업이 모두 존재해야 합니다."
    ),
)
async def create_relation(body: SupplyRelationCreate) -> SupplyRelationResponse:
    try:
        return await upsert_supply_relation(body)
    except LookupError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error("create_relation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"관계 저장 실패: {e}",
        )


# ─────────────────────────────────────────────────────
# GET /network/companies/{ticker}/suppliers
# ─────────────────────────────────────────────────────

@router.get(
    "/companies/{ticker}/suppliers",
    summary="직접 공급사 목록",
    description="특정 기업의 1-hop upstream 공급사 목록을 의존도 내림차순으로 반환합니다.",
)
async def get_suppliers(ticker: str) -> list[dict]:
    return await get_direct_suppliers(ticker.upper())


# ─────────────────────────────────────────────────────
# GET /network/companies/{ticker}/buyers
# ─────────────────────────────────────────────────────

@router.get(
    "/companies/{ticker}/buyers",
    summary="직접 구매사 목록",
    description="특정 기업의 1-hop downstream 구매사 목록을 의존도 내림차순으로 반환합니다.",
)
async def get_buyers(ticker: str) -> list[dict]:
    return await get_direct_buyers(ticker.upper())


# ─────────────────────────────────────────────────────
# GET /network/companies/{ticker}/subgraph
# ─────────────────────────────────────────────────────

@router.get(
    "/companies/{ticker}/subgraph",
    summary="서브그래프 조회",
    description=(
        "특정 기업 중심의 공급망 서브그래프를 반환합니다. "
        "`max_hop` 범위 내 모든 연결 노드와 엣지를 포함합니다."
    ),
)
async def get_company_subgraph(
    ticker:  str,
    max_hop: int = Query(3, ge=1, le=6, description="최대 탐색 홉 수"),
) -> dict:
    result = await get_subgraph(ticker.upper(), max_hop=max_hop)
    if not result["nodes"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ticker='{ticker.upper()}' 또는 연결된 노드를 찾을 수 없습니다.",
        )
    return result
