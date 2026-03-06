"""
app/api/v1/ai_analysis.py
---------------------------------------------------------
LLM + DART 기반 공급망 자동 발견 및 뉴스 충격 분석 API.

엔드포인트:
  POST /ai/discover/{ticker}        – 공급망 발견 (한국: DART+LLM, 글로벌: LLM)
  POST /ai/news-shock               – 뉴스 → 영향 기업 + 충격 강도 추정
  GET  /ai/dart/status              – DART API 연결 상태 확인
  GET  /ai/dart/companies           – DART 전체 한국 상장사 목록 조회
  POST /ai/dart/sync-kr             – 한국 상장사 Neo4j 일괄 등록 (배치)
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.core.logging import get_logger
from app.services.supply_chain_discoverer import supply_chain_discoverer
from app.services.dart_client import dart_client
from app.db.graph_repository import upsert_company
from app.models.graph_models import CompanyCreate

logger = get_logger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Analysis"])


class NewsShockRequest(BaseModel):
    news_text: str


# ── 공급망 발견 ──────────────────────────────────────────

@router.post("/discover/{ticker}")
async def discover_supply_chain(
    ticker: str,
    save_to_db: bool = Query(
        default=True,
        description="발견된 기업·관계를 Neo4j에 자동 저장 여부",
    ),
):
    """
    임의 티커의 공급망을 자동 발견하고 Neo4j에 저장.

    - **한국 주식 (6자리 숫자)**: DART 사업보고서 원문 → LLM 구조화
      - 재무데이터(매출액/영업이익)로 실제 LiquidityBuffer 계산
      - 공시 원문에서 주요 매출처·공급업체 추출 → LLM 컨텍스트 제공
    - **글로벌 주식**: yfinance 메타데이터 + LLM 파라메트릭 지식

    Returns:
        {
          "origin":          {ticker, name, sector, country},
          "suppliers":       [...],
          "buyers":          [...],
          "relations_saved": int,
          "summary":         "...",
          "data_source":     "DART+LLM" | "DART재무+LLM" | "LLM",
          "dart_financial":  {revenue, operating_income, liquidity_score} | null
        }
    """
    logger.info("api_discover_supply_chain", ticker=ticker, save_to_db=save_to_db)
    result = await supply_chain_discoverer.discover(
        ticker=ticker,
        save_to_db=save_to_db,
    )
    return result


# ── 뉴스 충격 분석 ───────────────────────────────────────

@router.post("/news-shock")
async def analyze_news_shock(body: NewsShockRequest):
    """
    뉴스 텍스트를 분석하여 공급망을 통한 영향 기업과 충격 강도 추정.

    Returns:
        {
          "event_title":        "...",
          "event_category":     "war | sanctions | ...",
          "affected_companies": [{ticker, name, shock_intensity, direction, reason}, ...],
          "summary":            "..."
        }
    """
    logger.info("api_analyze_news_shock", text_len=len(body.news_text))
    result = await supply_chain_discoverer.analyze_news(news_text=body.news_text)
    return result


# ── DART 전용 엔드포인트 ─────────────────────────────────

@router.get("/dart/status")
async def dart_status():
    """
    DART API 연결 상태 및 설정 확인.

    Returns:
        {
          "available": true | false,
          "message":   "..."
        }
    """
    available = dart_client.is_available
    return {
        "available": available,
        "message": (
            "DART API 키가 설정되어 정상 동작 중입니다."
            if available
            else "DART_API_KEY가 .env에 설정되지 않았습니다. "
                 "https://opendart.fss.or.kr 에서 발급 후 설정하세요."
        ),
    }


@router.get("/dart/companies")
async def list_dart_companies():
    """
    DART에서 한국 전체 상장사 목록 조회 (KOSPI + KOSDAQ).

    DART corpCode.xml에서 실시간으로 가져옵니다.
    캐싱 없이 매번 DART 서버에서 조회하므로 첫 호출에 수 초 소요될 수 있습니다.

    Returns:
        {
          "count": int,
          "companies": [
            {"corp_code": ..., "name": ..., "stock_code": ..., "market": "KOSPI|KOSDAQ"},
            ...
          ]
        }
    """
    if not dart_client.is_available:
        raise HTTPException(
            status_code=503,
            detail="DART API 키가 설정되지 않았습니다. .env의 DART_API_KEY를 확인하세요.",
        )

    logger.info("api_dart_list_companies")
    companies = await dart_client.get_listed_companies()
    return {
        "count":     len(companies),
        "companies": companies,
    }


@router.post("/dart/sync-kr")
async def sync_korean_companies(
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
        description="한 번에 등록할 최대 기업 수 (기본 50, 최대 500)",
    ),
    market: str = Query(
        default="ALL",
        description="대상 시장: KOSPI | KOSDAQ | ALL",
    ),
):
    """
    DART에서 한국 상장사 목록을 가져와 Neo4j에 기업 노드를 일괄 등록.

    - DART corpCode.xml에서 상장사 목록 조회
    - 각 기업을 Neo4j Company 노드로 MERGE (이미 있으면 업데이트)
    - 공급망 관계(SUPPLY_TO)는 이 엔드포인트에서 생성하지 않음
      → /ai/discover/{ticker} 로 개별 공급망 발견 필요

    이 작업은 기업 목록 DB를 구축하는 첫 단계입니다.
    이후 시뮬레이션 시 기업 선택 드롭다운에 나타납니다.

    Returns:
        {
          "registered": int,   # 성공적으로 Neo4j에 등록된 기업 수
          "skipped":    int,   # 오류로 건너뛴 기업 수
          "total":      int,   # 조회된 전체 기업 수 (limit 적용 전)
        }
    """
    if not dart_client.is_available:
        raise HTTPException(
            status_code=503,
            detail="DART API 키가 설정되지 않았습니다.",
        )

    logger.info("api_dart_sync_kr", limit=limit, market=market)

    # 전체 목록 조회
    all_companies = await dart_client.get_listed_companies()
    total = len(all_companies)

    # 시장 필터
    if market.upper() in ("KOSPI", "KOSDAQ"):
        filtered = [c for c in all_companies if c["market"] == market.upper()]
    else:
        filtered = all_companies

    # limit 적용
    targets = filtered[:limit]

    registered = 0
    skipped    = 0

    for company in targets:
        try:
            # 섹터는 DART 업종코드(한국 SIC)라 GICS 매핑이 어려움
            # → Unknown으로 등록 후 /ai/discover/{ticker}로 보완
            await upsert_company(CompanyCreate(
                ticker=company["stock_code"],
                name=company["name"],
                sector="Unknown",
                country="South Korea",
                liquidity_score=0.55,        # 기본값 (이후 DART 재무로 갱신)
                supplier_concentration=0.50,
            ))
            registered += 1
        except Exception as e:
            logger.debug(
                "dart_sync_company_failed",
                ticker=company.get("stock_code"),
                error=str(e),
            )
            skipped += 1

    logger.info(
        "dart_sync_kr_completed",
        registered=registered,
        skipped=skipped,
        total=total,
    )

    return {
        "registered": registered,
        "skipped":    skipped,
        "total":      total,
        "message": (
            f"{registered}개 기업이 Neo4j에 등록되었습니다. "
            f"공급망 발견은 /ai/discover/{{ticker}} 로 개별 실행하세요."
        ),
    }
