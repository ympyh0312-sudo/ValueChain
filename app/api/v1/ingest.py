"""
app/api/v1/ingest.py
---------------------------------------------------------
뉴스 기사 수집·처리 엔드포인트.

엔드포인트:
    POST /ingest/articles          - 기사 저장 (PENDING)
    POST /ingest/articles/{id}/process - 기사 LLM 처리 (PENDING→COMPLETED)

설계:
- ingest 만 하고 나중에 process 할 수 있어 두 엔드포인트로 분리
- auto_process=True이면 ingest 즉시 process까지 수행
- 404: 기사 미존재 / 409: 이미 처리된 기사
"""

from fastapi import APIRouter, HTTPException, status

from app.core.logging import get_logger
from app.models.db_models import ArticleStatus
from app.db.postgres_client import postgres_client
from app.models.db_models import NewsArticle
from app.services.ingestion_pipeline import ingestion_pipeline
from app.api.v1.schemas import (
    IngestArticleRequest,
    IngestArticleResponse,
    ProcessArticleResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/ingest", tags=["Ingest"])


# ─────────────────────────────────────────────────────
# POST /ingest/articles
# ─────────────────────────────────────────────────────

@router.post(
    "/articles",
    response_model=IngestArticleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="뉴스 기사 수집",
    description=(
        "뉴스 기사를 PostgreSQL에 저장합니다. "
        "`auto_process=true`이면 저장 직후 LLM 추출 파이프라인도 실행됩니다."
    ),
)
async def ingest_article(body: IngestArticleRequest) -> IngestArticleResponse:
    try:
        article_id = await ingestion_pipeline.ingest_article(
            title        = body.title,
            content      = body.content,
            source_url   = body.source_url,
            source_name  = body.source_name,
            published_at = body.published_at,
            language     = body.language,
        )
    except Exception as e:
        logger.error("ingest_article_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"기사 저장 실패: {e}",
        )

    if body.auto_process:
        try:
            proc = await ingestion_pipeline.process_article(article_id)
            return IngestArticleResponse(
                article_id=article_id,
                status="processed",
                message=(
                    f"relations_found={proc.relations_found}, "
                    f"applied={proc.relations_applied}, "
                    f"rejected={proc.relations_rejected}"
                ),
            )
        except Exception as e:
            logger.error("auto_process_failed", article_id=article_id, error=str(e))
            return IngestArticleResponse(
                article_id=article_id,
                status="ingested",
                message=f"저장 완료, 처리 실패: {e}",
            )

    return IngestArticleResponse(
        article_id=article_id,
        status="ingested",
        message="저장 완료. POST /ingest/articles/{id}/process 로 처리하세요.",
    )


# ─────────────────────────────────────────────────────
# POST /ingest/articles/{article_id}/process
# ─────────────────────────────────────────────────────

@router.post(
    "/articles/{article_id}/process",
    response_model=ProcessArticleResponse,
    summary="기사 LLM 처리",
    description=(
        "저장된 기사를 LLM으로 분석하여 공급망 관계를 추출하고 Neo4j 그래프에 반영합니다. "
        "이미 COMPLETED/FAILED 상태인 기사도 재처리 가능합니다."
    ),
)
async def process_article(article_id: int) -> ProcessArticleResponse:
    # 기사 존재 확인
    async with postgres_client.get_session() as session:
        article = await session.get(NewsArticle, article_id)
        if article is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"article_id={article_id} 를 찾을 수 없습니다.",
            )

    try:
        result = await ingestion_pipeline.process_article(article_id)
    except Exception as e:
        logger.error("process_article_endpoint_failed", article_id=article_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"처리 실패: {e}",
        )

    details_dicts = [
        {
            "supplier_name":       d.supplier_name,
            "buyer_name":          d.buyer_name,
            "supplier_ticker":     d.supplier_ticker,
            "buyer_ticker":        d.buyer_ticker,
            "llm_confidence":      d.llm_confidence,
            "name_confidence":     d.name_confidence,
            "combined_confidence": d.combined_confidence,
            "is_applied":          d.is_applied,
            "rejection_reason":    d.rejection_reason,
        }
        for d in result.details
    ]

    return ProcessArticleResponse(
        article_id         = result.article_id,
        status             = result.status.value,
        relations_found    = result.relations_found,
        relations_applied  = result.relations_applied,
        relations_rejected = result.relations_rejected,
        details            = details_dicts,
        error              = result.error,
    )
